"""Resident Agno agents, one per user, with their campus MCP subprocesses.

This is what replaced the per-user container. An entry here owns a live
``Agent`` and the MCP subprocesses its toolkits spawned, so the same questions
the container runtime answered — when does a user's agent come up, when does it
go away, what happens when their toolset changes — are answered here instead.

Two things make this cheaper than the containers were. Building an entry costs
one process spawn per connected campus server rather than a container start, so
a cold user is seconds rather than tens of seconds. And nothing is lost by
evicting one: conversation history lives in the database (see
:mod:`app.agents.store`), not on a volume, so eviction is invisible to the
student beyond the next turn being slightly slower.

Concurrency: entries are created under a per-user lock, so two simultaneous
first turns build one agent rather than two sets of subprocesses. The lock is
*not* held across a model turn — that is the database turn lock's job
(:func:`app.agents.manager.acquire_turn_lock`), which also works across
replicas, as this pool does not.
"""

import asyncio
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from agno.agent import Agent
from agno.models.base import Model
from agno.models.openrouter import OpenRouter
from agno.tools.mcp import MCPTools

from app.agents.store import get_agno_db
from app.agents.toolset import build_toolkits, close_toolkits, connect_toolkits
from app.campus.mcp_config import CampusServerSpec
from app.config import get_settings
from app.logging import get_logger

logger = get_logger(__name__)

_PERSONA_PATH = Path(__file__).with_name("persona.md")


def load_persona() -> str:
    return _PERSONA_PATH.read_text(encoding="utf-8")


def build_model() -> Model:
    settings = get_settings()
    if settings.agent_runtime == "fake":
        from app.agents.echo_model import EchoModel

        return EchoModel()
    return OpenRouter(
        id=settings.agent_model,
        api_key=settings.agent_openai_api_key,
        base_url=settings.agent_openai_base_url,
        max_tokens=settings.agent_max_tokens,
    )


@dataclass
class ResidentAgent:
    """One user's live agent, and the subprocesses it is holding open."""

    user_id: UUID
    agent: Agent
    toolkits: list[MCPTools] = field(default_factory=list)
    # Which campus tools this agent was actually built with. Compared against
    # the student's current selection to notice a toolset that went stale
    # while the agent was resident.
    tool_ids: tuple[str, ...] = ()
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_used_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def touch(self) -> None:
        self.last_used_at = datetime.now(UTC)


class AgentPool:
    def __init__(self) -> None:
        # Ordered by least-recently-used first, so eviction is a popitem.
        self._entries: OrderedDict[UUID, ResidentAgent] = OrderedDict()
        self._locks: dict[UUID, asyncio.Lock] = {}
        self._registry_lock = asyncio.Lock()

    async def _lock_for(self, user_id: UUID) -> asyncio.Lock:
        async with self._registry_lock:
            return self._locks.setdefault(user_id, asyncio.Lock())

    async def acquire(self, user_id: UUID, specs: list[CampusServerSpec]) -> ResidentAgent:
        """The user's live agent, building it if it isn't resident or is stale."""
        wanted = tuple(spec.tool_id for spec in specs)
        lock = await self._lock_for(user_id)
        async with lock:
            entry = self._entries.get(user_id)
            if entry is not None and entry.tool_ids == wanted:
                entry.touch()
                self._entries.move_to_end(user_id)
                return entry

            if entry is not None:
                # Resident but built with a different toolset: the student
                # changed their campus connection since this agent came up.
                logger.info("agent_toolset_changed", user_id=str(user_id), was=entry.tool_ids, now=wanted)
                await self._discard(user_id)

            entry = await self._build(user_id, specs, wanted)
            self._entries[user_id] = entry
            self._entries.move_to_end(user_id)

        await self._enforce_capacity()
        return entry

    async def _build(self, user_id: UUID, specs: list[CampusServerSpec], wanted: tuple[str, ...]) -> ResidentAgent:
        settings = get_settings()
        toolkits = build_toolkits(specs, timeout_seconds=settings.campus_mcp_timeout_seconds)
        connected = await connect_toolkits(toolkits)

        agent = Agent(
            # Stable across rebuilds so Agno's stored sessions keep resolving
            # to the same agent after an eviction.
            id=f"devrimo-campus-{user_id}",
            name="Devrimo Campus Agent",
            model=build_model(),
            db=get_agno_db(),
            tools=list(connected),
            instructions=load_persona(),
            add_history_to_context=True,
            num_history_runs=settings.agent_history_runs,
            add_datetime_to_context=True,
            markdown=True,
            # Agno posts run telemetry to os-api.agno.com by default. This
            # agent's runs are a student's campus conversations, so that is
            # switched off here rather than left to an env var a deployment
            # might forget. AGNO_TELEMETRY=false is set in the compose file too.
            telemetry=False,
        )
        logger.info(
            "agent_built",
            user_id=str(user_id),
            requested_tools=wanted,
            connected_tools=tuple(t.name for t in connected),
        )
        return ResidentAgent(user_id=user_id, agent=agent, toolkits=connected, tool_ids=wanted)

    async def _discard(self, user_id: UUID) -> None:
        """Drop an entry and close its subprocesses. Caller holds the user's lock."""
        entry = self._entries.pop(user_id, None)
        if entry is None:
            return
        await close_toolkits(entry.toolkits)

    async def _enforce_capacity(self) -> None:
        settings = get_settings()
        while len(self._entries) > settings.agent_pool_max_size:
            user_id, _ = next(iter(self._entries.items()))
            logger.info("agent_evicted_for_capacity", user_id=str(user_id))
            lock = await self._lock_for(user_id)
            async with lock:
                await self._discard(user_id)

    async def invalidate(self, user_id: UUID) -> bool:
        """Drop this user's agent so the next turn rebuilds it.

        Called when a campus connection changes. Returns whether anything was
        actually resident — a student whose agent had already been evicted
        needs no work here, their next turn builds from current credentials.
        """
        lock = await self._lock_for(user_id)
        async with lock:
            if user_id not in self._entries:
                return False
            await self._discard(user_id)
            return True

    async def evict_idle(self, cutoff: datetime) -> list[UUID]:
        stale = [uid for uid, entry in self._entries.items() if entry.last_used_at < cutoff]
        for user_id in stale:
            lock = await self._lock_for(user_id)
            async with lock:
                await self._discard(user_id)
        return stale

    async def close_all(self) -> None:
        for user_id in list(self._entries):
            await self._discard(user_id)

    def is_resident(self, user_id: UUID) -> bool:
        return user_id in self._entries

    def get(self, user_id: UUID) -> ResidentAgent | None:
        return self._entries.get(user_id)

    def size(self) -> int:
        return len(self._entries)


_pool: AgentPool | None = None


def get_pool() -> AgentPool:
    global _pool
    if _pool is None:
        _pool = AgentPool()
    return _pool


async def reset_pool() -> None:
    """Tear the pool down. Used by app shutdown and between tests."""
    global _pool
    if _pool is not None:
        await _pool.close_all()
    _pool = None
