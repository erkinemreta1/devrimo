import asyncio

from tests.conftest import auth_header, new_user_id


async def _wait_until(client, headers, status_value, attempts=50):
    for _ in range(attempts):
        response = await client.get("/api/v1/agents/me", headers=headers)
        if response.json()["status"] == status_value:
            return response
        await asyncio.sleep(0.02)
    raise AssertionError(f"agent never reached status={status_value}")


async def test_get_agent_before_provision_is_404(client):
    headers = auth_header(new_user_id())
    response = await client.get("/api/v1/agents/me", headers=headers)
    assert response.status_code == 404


async def test_missing_bearer_is_401(client):
    response = await client.get("/api/v1/agents/me")
    assert response.status_code == 401


async def test_provision_then_reaches_running(client):
    headers = auth_header(new_user_id())

    response = await client.post("/api/v1/agents/provision", headers=headers)
    assert response.status_code == 201
    assert response.json()["status"] == "provisioning"

    final = await _wait_until(client, headers, "running")
    body = final.json()
    assert body["status"] == "running"
    assert body["hermes_image_tag"]
    assert body["user_id"]


async def test_double_provision_is_409(client):
    headers = auth_header(new_user_id())
    await client.post("/api/v1/agents/provision", headers=headers)

    response = await client.post("/api/v1/agents/provision", headers=headers)
    assert response.status_code == 409


async def test_start_stop_destroy_cycle(client):
    headers = auth_header(new_user_id())
    await client.post("/api/v1/agents/provision", headers=headers)
    await _wait_until(client, headers, "running")

    stopped = await client.post("/api/v1/agents/stop", headers=headers)
    assert stopped.json()["status"] == "stopped"

    started = await client.post("/api/v1/agents/start", headers=headers)
    assert started.json()["status"] == "running"

    deleted = await client.delete("/api/v1/agents", headers=headers)
    assert deleted.status_code == 204

    gone = await client.get("/api/v1/agents/me", headers=headers)
    assert gone.status_code == 404


async def test_agents_are_isolated_per_user(client):
    headers_a = auth_header(new_user_id())
    headers_b = auth_header(new_user_id())

    await client.post("/api/v1/agents/provision", headers=headers_a)
    response = await client.get("/api/v1/agents/me", headers=headers_b)
    assert response.status_code == 404
