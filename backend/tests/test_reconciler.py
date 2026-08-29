import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.agents import manager
from app.agents.reconciler import reconcile_once
from app.db.models import Agent, AgentStatus
from app.db.session import SessionLocal
from tests.conftest import auth_header, new_user_id


async def _provision_and_wait(client, headers):
    await client.post("/api/v1/agents/provision", headers=headers)
    for _ in range(50):
        response = await client.get("/api/v1/agents/me", headers=headers)
        if response.json()["status"] == "running":
            return
        await asyncio.sleep(0.02)
    raise AssertionError("agent never became running")


async def test_reconciler_reaps_idle_agents(client):
    headers = auth_header(new_user_id())
    await _provision_and_wait(client, headers)

    async with SessionLocal() as db:
        result = await db.execute(select(Agent))
        agent = result.scalar_one()
        agent.last_active_at = datetime.now(UTC) - timedelta(hours=1)
        await db.commit()

    await reconcile_once()

    response = await client.get("/api/v1/agents/me", headers=headers)
    assert response.json()["status"] == "stopped"


async def test_reconciler_heals_crashed_container(client):
    headers = auth_header(new_user_id())
    await _provision_and_wait(client, headers)

    async with SessionLocal() as db:
        result = await db.execute(select(Agent))
        agent = result.scalar_one()
        spec = manager.spec_for(agent)

    runtime = manager.get_runtime()
    runtime.containers[spec.container_name].running = False

    await reconcile_once()

    response = await client.get("/api/v1/agents/me", headers=headers)
    assert response.json()["status"] == "running"


async def test_reconciler_marks_stuck_provisioning_as_error(client):
    headers = auth_header(new_user_id())
    # Provision and let the (fake, instant) background job finish first, then force the
    # row back into `provisioning` with a stale `created_at` — simulating a broker crash
    # mid-provision, which the reconciler must notice and fail out of.
    await _provision_and_wait(client, headers)

    async with SessionLocal() as db:
        result = await db.execute(select(Agent))
        agent = result.scalar_one()
        agent.status = AgentStatus.provisioning
        agent.created_at = datetime.now(UTC) - timedelta(hours=1)
        await db.commit()

    await reconcile_once()

    response = await client.get("/api/v1/agents/me", headers=headers)
    body = response.json()
    assert body["status"] == "error"
