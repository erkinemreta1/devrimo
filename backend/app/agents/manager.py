import asyncio
import secrets
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.docker_runtime import DockerAgentRuntime
from app.agents.fake_runtime import FakeAgentRuntime
from app.agents.runtime import AgentRuntime, AgentSpec
from app.config import get_settings
from app.core.crypto import decrypt_secret, encrypt_secret
from app.db.models import Agent, AgentStatus
from app.db.session import SessionLocal
from app.logging import get_logger

logger = get_logger(__name__)

TURN_LOCK_LEASE_SECONDS = 90


@lru_cache
def get_runtime() -> AgentRuntime:
    settings = get_settings()
    if settings.agent_runtime == "fake":
        return FakeAgentRuntime()
    return DockerAgentRuntime()


def spec_for(agent: Agent) -> AgentSpec:
    settings = get_settings()
    return AgentSpec(
        user_id=agent.user_id,
        container_name=agent.container_name,
        volume_name=agent.volume_name,
        image=agent.hermes_image_tag,
        api_key=decrypt_secret(agent.api_key_enc),
        port=settings.agent_api_server_port,
    )


def endpoint_for(agent: Agent) -> str:
    return get_runtime().endpoint_url(spec_for(agent))


def api_key_for(agent: Agent) -> str:
    return decrypt_secret(agent.api_key_enc)


async def get_agent(db: AsyncSession, user_id: UUID) -> Agent | None:
    result = await db.execute(select(Agent).where(Agent.user_id == user_id))
    return result.scalar_one_or_none()


async def get_agent_or_404(db: AsyncSession, user_id: UUID) -> Agent:
    agent = await get_agent(db, user_id)
    if agent is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No agent for this user")
    return agent


async def provision(db: AsyncSession, user_id: UUID) -> Agent:
    existing = await get_agent(db, user_id)
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Agent already exists")

    settings = get_settings()
    agent = Agent(
        user_id=user_id,
        status=AgentStatus.provisioning,
        hermes_image_tag=settings.hermes_image,
        container_name=f"hermes-{user_id}",
        volume_name=f"hermes-data-{user_id}",
        api_key_enc=encrypt_secret(secrets.token_urlsafe(32)),
    )
    db.add(agent)
    try:
        await db.commit()
    except Exception as exc:  # unique constraint race between concurrent requests
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Agent already exists") from exc
    await db.refresh(agent)

    asyncio.create_task(_finish_provisioning(agent.id))
    return agent


async def _finish_provisioning(agent_id: UUID) -> None:
    settings = get_settings()
    async with SessionLocal() as db:
        result = await db.execute(select(Agent).where(Agent.id == agent_id))
        agent = result.scalar_one_or_none()
        if agent is None:
            return

        spec = spec_for(agent)
        try:
            await get_runtime().create(spec)
            healthy = await wait_for_health(spec, settings.agent_start_timeout_seconds)
            agent.status = AgentStatus.running if healthy else AgentStatus.error
            agent.error_detail = None if healthy else "Agent did not become healthy in time"
            agent.last_active_at = datetime.now(UTC)
        except Exception as exc:  # runtime failures land the agent in `error`, never crash the loop
            logger.error("provision_failed", user_id=str(agent.user_id), error=str(exc))
            agent.status = AgentStatus.error
            agent.error_detail = str(exc)
        await db.commit()


async def wait_for_health(spec: AgentSpec, timeout_seconds: int) -> bool:
    runtime = get_runtime()
    deadline = asyncio.get_event_loop().time() + timeout_seconds
    delay = 0.5
    while asyncio.get_event_loop().time() < deadline:
        if await runtime.healthy(spec):
            return True
        await asyncio.sleep(delay)
        delay = min(delay * 1.5, 3.0)
    return await runtime.healthy(spec)


async def ensure_running(db: AsyncSession, agent: Agent) -> Agent:
    """Called on the hot chat path: brings a stopped agent back up, in place."""
    if agent.status == AgentStatus.running:
        return agent
    if agent.status == AgentStatus.provisioning:
        raise HTTPException(status.HTTP_409_CONFLICT, "Agent is still provisioning")
    if agent.status == AgentStatus.destroying:
        raise HTTPException(status.HTTP_409_CONFLICT, "Agent is being destroyed")
    if agent.status == AgentStatus.error:
        raise HTTPException(status.HTTP_409_CONFLICT, agent.error_detail or "Agent is in an error state")

    return await start(db, agent)


async def start(db: AsyncSession, agent: Agent) -> Agent:
    settings = get_settings()
    spec = spec_for(agent)
    runtime = get_runtime()
    try:
        await runtime.start(spec)
        healthy = await wait_for_health(spec, settings.agent_start_timeout_seconds)
    except Exception as exc:
        agent.status = AgentStatus.error
        agent.error_detail = str(exc)
        await db.commit()
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Could not start agent: {exc}") from exc

    if not healthy:
        agent.status = AgentStatus.error
        agent.error_detail = "Agent did not become healthy in time"
        await db.commit()
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, agent.error_detail)

    agent.status = AgentStatus.running
    agent.error_detail = None
    agent.last_active_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(agent)
    return agent


async def stop(db: AsyncSession, agent: Agent) -> Agent:
    if agent.status == AgentStatus.stopped:
        return agent
    spec = spec_for(agent)
    await get_runtime().stop(spec)
    agent.status = AgentStatus.stopped
    await db.commit()
    await db.refresh(agent)
    return agent


async def destroy(db: AsyncSession, agent: Agent) -> None:
    agent.status = AgentStatus.destroying
    await db.commit()

    spec = spec_for(agent)
    await get_runtime().destroy(spec)

    await db.delete(agent)
    await db.commit()


async def acquire_turn_lock(db: AsyncSession, agent: Agent, owner: str) -> bool:
    now = datetime.now(UTC)
    lease_until = now + timedelta(seconds=TURN_LOCK_LEASE_SECONDS)

    result = await db.execute(
        update(Agent)
        .where(
            Agent.id == agent.id,
            (Agent.turn_lock_until.is_(None)) | (Agent.turn_lock_until < now),
        )
        .values(turn_lock_until=lease_until, turn_lock_owner=owner)
        .execution_options(synchronize_session=False)
    )
    await db.commit()
    return result.rowcount > 0


async def release_turn_lock(db: AsyncSession, agent: Agent, owner: str) -> None:
    await db.execute(
        update(Agent)
        .where(Agent.id == agent.id, Agent.turn_lock_owner == owner)
        .values(turn_lock_until=None, turn_lock_owner=None)
        .execution_options(synchronize_session=False)
    )
    await db.commit()


async def touch_last_active(db: AsyncSession, agent: Agent) -> None:
    agent.last_active_at = datetime.now(UTC)
    await db.commit()
