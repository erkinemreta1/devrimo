"""Campus connection + onboarding endpoints, and the MCP config they render.

Credential verification is stubbed throughout: these tests assert what the
broker does with a verification result, never that METU's SSO behaves a
particular way.
"""

import json

import pytest

from app.agents import manager
from app.api.v1 import campus as campus_routes
from app.campus.verify import VerificationResult
from tests.conftest import auth_header, new_user_id


@pytest.fixture
def accept_credentials(monkeypatch):
    async def _ok(username: str, password: str, timeout: float = 20.0) -> VerificationResult:
        return VerificationResult(ok=True)

    monkeypatch.setattr(campus_routes, "verify_metu_credentials", _ok)


@pytest.fixture
def reject_credentials(monkeypatch):
    async def _no(username: str, password: str, timeout: float = 20.0) -> VerificationResult:
        return VerificationResult(ok=False, detail="METU rejected the sign-in.")

    monkeypatch.setattr(campus_routes, "verify_metu_credentials", _no)


async def test_connection_starts_empty_but_lists_the_catalog(client):
    user_id = new_user_id()
    response = await client.get("/api/v1/campus/connection", headers=auth_header(user_id))

    assert response.status_code == 200
    body = response.json()
    assert body["connected"] is False
    assert {tool["id"] for tool in body["tools"]} == {"sais", "course_info", "odtuclass", "webmail"}
    assert all(tool["active"] is False for tool in body["tools"])


async def test_connect_stores_credentials_and_never_returns_them(client, accept_credentials):
    user_id = new_user_id()
    response = await client.put(
        "/api/v1/campus/connection",
        headers=auth_header(user_id),
        json={
            "metu_username": "E123456@metu.edu.tr",
            "metu_password": "hunter2",
            "locale": "en",
            "enabled_tools": ["sais", "odtuclass"],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["connected"] is True
    # Normalized: the domain is stripped and the case folded.
    assert body["metu_username"] == "e123456"
    assert body["has_password"] is True
    assert body["verified_at"] is not None
    assert body["enabled_tools"] == ["sais", "odtuclass"]
    assert "hunter2" not in response.text


async def test_rejected_credentials_are_not_stored(client, reject_credentials):
    user_id = new_user_id()
    response = await client.put(
        "/api/v1/campus/connection",
        headers=auth_header(user_id),
        json={"metu_username": "e123456", "metu_password": "wrong"},
    )
    assert response.status_code == 400

    after = await client.get("/api/v1/campus/connection", headers=auth_header(user_id))
    assert after.json()["connected"] is False


async def test_unreachable_sso_saves_unverified_rather_than_blocking(client, monkeypatch):
    async def _down(username: str, password: str, timeout: float = 20.0) -> VerificationResult:
        return VerificationResult(ok=False, unreachable=True, detail="Could not reach METU sign-in right now.")

    monkeypatch.setattr(campus_routes, "verify_metu_credentials", _down)

    user_id = new_user_id()
    response = await client.put(
        "/api/v1/campus/connection",
        headers=auth_header(user_id),
        json={"metu_username": "e123456", "metu_password": "hunter2"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["connected"] is True
    assert body["verified_at"] is None
    assert body["verification_error"]


async def test_password_may_be_omitted_when_only_toggling_tools(client, accept_credentials):
    user_id = new_user_id()
    headers = auth_header(user_id)
    await client.put(
        "/api/v1/campus/connection",
        headers=headers,
        json={"metu_username": "e123456", "metu_password": "hunter2", "enabled_tools": ["sais"]},
    )

    response = await client.put(
        "/api/v1/campus/connection",
        headers=headers,
        json={"metu_username": "e123456", "enabled_tools": ["sais", "webmail"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["enabled_tools"] == ["sais", "webmail"]
    assert body["has_password"] is True
    # The earlier verification carries forward rather than being reset.
    assert body["verified_at"] is not None


async def test_first_connect_requires_a_password(client, accept_credentials):
    response = await client.put(
        "/api/v1/campus/connection",
        headers=auth_header(new_user_id()),
        json={"metu_username": "e123456"},
    )
    assert response.status_code == 422


async def test_disconnect_forgets_the_credentials(client, accept_credentials):
    user_id = new_user_id()
    headers = auth_header(user_id)
    await client.put(
        "/api/v1/campus/connection",
        headers=headers,
        json={"metu_username": "e123456", "metu_password": "hunter2"},
    )

    response = await client.delete("/api/v1/campus/connection", headers=headers)
    assert response.status_code == 200
    assert response.json()["connected"] is False


async def test_agent_container_is_built_with_the_students_mcp_config(client, accept_credentials):
    user_id = new_user_id()
    headers = auth_header(user_id)
    await client.put(
        "/api/v1/campus/connection",
        headers=headers,
        json={
            "metu_username": "e123456",
            "metu_password": "hunter2",
            "enabled_tools": ["sais", "webmail"],
        },
    )

    provision = await client.post("/api/v1/agents/provision", headers=headers)
    assert provision.status_code == 201
    # Provisioning finishes on a background task; poll the status the same way
    # the frontend does.
    for _ in range(40):
        agent = (await client.get("/api/v1/agents/me", headers=headers)).json()
        if agent["status"] != "provisioning":
            break

    runtime = manager.get_runtime()
    container = runtime.containers[f"hermes-{user_id}"]
    servers = json.loads(container.mcp_config)

    assert set(servers) == {"sais", "webmail"}
    assert servers["sais"]["env"]["SAIS_USERNAME"] == "e123456"
    assert servers["sais"]["env"]["SAIS_PASSWORD"] == "hunter2"
    assert servers["webmail"]["env"]["METU_PASSWORD"] == "hunter2"


async def test_agent_without_a_connection_gets_an_empty_config(client):
    user_id = new_user_id()
    headers = auth_header(user_id)
    await client.post("/api/v1/agents/provision", headers=headers)
    for _ in range(40):
        agent = (await client.get("/api/v1/agents/me", headers=headers)).json()
        if agent["status"] != "provisioning":
            break

    container = manager.get_runtime().containers[f"hermes-{user_id}"]
    assert json.loads(container.mcp_config) == {}


async def test_changing_the_connection_rebuilds_a_running_agent(client, accept_credentials):
    user_id = new_user_id()
    headers = auth_header(user_id)
    await client.post("/api/v1/agents/provision", headers=headers)
    for _ in range(40):
        agent = (await client.get("/api/v1/agents/me", headers=headers)).json()
        if agent["status"] == "running":
            break
    assert agent["status"] == "running"

    response = await client.put(
        "/api/v1/campus/connection",
        headers=headers,
        json={"metu_username": "e123456", "metu_password": "hunter2", "enabled_tools": ["sais"]},
    )
    assert response.status_code == 200
    # Applied eagerly, so the student doesn't have to restart anything.
    assert response.json()["needs_restart"] is False

    container = manager.get_runtime().containers[f"hermes-{user_id}"]
    assert set(json.loads(container.mcp_config)) == {"sais"}


async def test_connections_are_isolated_per_user(client, accept_credentials):
    first, second = new_user_id(), new_user_id()
    await client.put(
        "/api/v1/campus/connection",
        headers=auth_header(first),
        json={"metu_username": "e111111", "metu_password": "one"},
    )

    response = await client.get("/api/v1/campus/connection", headers=auth_header(second))
    assert response.json()["connected"] is False


async def test_campus_endpoints_require_auth(client):
    assert (await client.get("/api/v1/campus/connection")).status_code == 401
    assert (await client.get("/api/v1/profile")).status_code == 401


async def test_a_change_made_while_stopped_is_pushed_on_restart(client, accept_credentials):
    """The stale-toolset case: the container outlives the config it was built with."""
    user_id = new_user_id()
    headers = auth_header(user_id)
    await client.post("/api/v1/agents/provision", headers=headers)
    for _ in range(40):
        agent = (await client.get("/api/v1/agents/me", headers=headers)).json()
        if agent["status"] == "running":
            break

    stopped = await client.post("/api/v1/agents/stop", headers=headers)
    assert stopped.json()["status"] == "stopped"

    # Saved while stopped, so there is no running container to push it into.
    saved = await client.put(
        "/api/v1/campus/connection",
        headers=headers,
        json={"metu_username": "e123456", "metu_password": "hunter2", "enabled_tools": ["sais"]},
    )
    assert saved.json()["needs_restart"] is True

    started = await client.post("/api/v1/agents/start", headers=headers)
    assert started.json()["status"] == "running"

    container = manager.get_runtime().containers[f"hermes-{user_id}"]
    assert set(json.loads(container.mcp_config)) == {"sais"}

    after = await client.get("/api/v1/campus/connection", headers=headers)
    assert after.json()["needs_restart"] is False
