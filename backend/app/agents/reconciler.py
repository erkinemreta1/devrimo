"""Background loop that drives desired state toward actual state.

Runs once per ``RECONCILE_INTERVAL_SECONDS`` for the lifetime of the app:
stops agents that have been idle too long, and notices containers that
died or got stuck outside of a normal request so a user isn't left
staring at a spinner for an agent nobody is watching.
"""

import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.agents.manager import get_runtime, spec_for, spec_with_campus, wait_for_health
from app.config import get_settings
from app.db.models import Agent, AgentStatus
from app.db.session import SessionLocal
from app.logging import get_logger

logger = get_logger(__name__)


async def _reap_idle(now: datetime) -> None:
    settings = get_settings()
    cutoff = now - timedelta(seconds=settings.agent_idle_timeout_seconds)

    async with SessionLocal() as db:
        result = await db.execute(
            select(Agent).where(
                Agent.status == AgentStatus.running,
                Agent.last_active_at.is_not(None),
                Agent.last_active_at < cutoff,
            )
        )
        idle_agents = result.scalars().all()
        for agent in idle_agents:
            logger.info("reaping_idle_agent", user_id=str(agent.user_id))
            try:
                await get_runtime().stop(spec_for(agent))
                agent.status = AgentStatus.stopped
            except Exception as exc:
                logger.warning("reap_failed", user_id=str(agent.user_id), error=str(exc))
        if idle_agents:
            await db.commit()


async def _heal_crashed(now: datetime) -> None:
    settings = get_settings()
    runtime = get_runtime()

    async with SessionLocal() as db:
        result = await db.execute(select(Agent).where(Agent.status == AgentStatus.running))
        running_agents = result.scalars().all()
        for agent in running_agents:
            spec = spec_for(agent)
            state = await runtime.state(spec)
            if state.running:
                continue

            logger.warning("agent_crashed_restarting", user_id=str(agent.user_id))
            try:
                # A crash can also mean the container is gone entirely, in
                # which case ``start`` recreates it — with the campus config,
                # or the student silently loses their tools on a heal.
                spec = await spec_with_campus(db, agent)
                await runtime.start(spec)
                healthy = await wait_for_health(spec, settings.agent_start_timeout_seconds)
                if not healthy:
                    raise RuntimeError("did not become healthy after restart")
            except Exception as exc:
                agent.status = AgentStatus.error
                agent.error_detail = f"Container stopped unexpectedly and restart failed: {exc}"
                logger.error("agent_heal_failed", user_id=str(agent.user_id), error=str(exc))

        await db.commit()

    async with SessionLocal() as db:
        stuck_cutoff = now - timedelta(seconds=settings.agent_start_timeout_seconds * 2)
        result = await db.execute(
            select(Agent).where(Agent.status == AgentStatus.provisioning, Agent.created_at < stuck_cutoff)
        )
        stuck_agents = result.scalars().all()
        for agent in stuck_agents:
            agent.status = AgentStatus.error
            agent.error_detail = "Provisioning did not complete; retry by deleting and re-provisioning"
        if stuck_agents:
            await db.commit()


async def reconcile_once() -> None:
    now = datetime.now(UTC)
    await _reap_idle(now)
    await _heal_crashed(now)


async def run_reconciler_loop(stop_event: asyncio.Event) -> None:
    settings = get_settings()
    while not stop_event.is_set():
        try:
            await reconcile_once()
        except Exception as exc:
            logger.error("reconcile_iteration_failed", error=str(exc))
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=settings.reconcile_interval_seconds)
        except TimeoutError:
            pass
