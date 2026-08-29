import asyncio

import app.api.v1.chat as chat_module
import app.api.v1.sessions as sessions_module
from tests.conftest import auth_header, new_user_id


class _StubHermesClient:
    """Replaces the real HTTP client so tests never need a live Hermes container."""

    calls: list[tuple[str, str]] = []

    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url
        self.api_key = api_key

    async def stream_chat_completions(self, messages, hermes_session_id):
        _StubHermesClient.calls.append(("chat", hermes_session_id))
        chunk = {"choices": [{"delta": {"content": "Hello from Hermes"}}]}
        yield f"data: {chunk}\n\n".encode()
        yield b"data: [DONE]\n\n"

    async def list_messages(self, hermes_session_id):
        _StubHermesClient.calls.append(("messages", hermes_session_id))
        return [
            {"role": "user", "content": "hi", "created_at": None},
            {"role": "assistant", "content": "hello", "created_at": None},
        ]

    async def delete_session(self, hermes_session_id):
        _StubHermesClient.calls.append(("delete", hermes_session_id))


async def _provision_and_wait(client, headers):
    await client.post("/api/v1/agents/provision", headers=headers)
    for _ in range(50):
        response = await client.get("/api/v1/agents/me", headers=headers)
        if response.json()["status"] == "running":
            return
        await asyncio.sleep(0.02)
    raise AssertionError("agent never became running")


async def test_chat_completions_streams_sse(client, monkeypatch):
    monkeypatch.setattr(chat_module, "HermesClient", _StubHermesClient)
    headers = auth_header(new_user_id())
    await _provision_and_wait(client, headers)

    response = await client.post(
        "/api/v1/chat/completions",
        headers=headers,
        json={"messages": [{"role": "user", "content": "hi"}], "session_id": "thread-1"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert b"Hello from Hermes" in response.content
    assert b"[DONE]" in response.content


async def test_chat_completions_without_agent_is_404(client, monkeypatch):
    monkeypatch.setattr(chat_module, "HermesClient", _StubHermesClient)
    headers = auth_header(new_user_id())

    response = await client.post(
        "/api/v1/chat/completions",
        headers=headers,
        json={"messages": [{"role": "user", "content": "hi"}], "session_id": "thread-1"},
    )
    assert response.status_code == 404


async def test_chat_creates_and_lists_session(client, monkeypatch):
    monkeypatch.setattr(chat_module, "HermesClient", _StubHermesClient)
    monkeypatch.setattr(sessions_module, "HermesClient", _StubHermesClient)
    headers = auth_header(new_user_id())
    await _provision_and_wait(client, headers)

    await client.post(
        "/api/v1/chat/completions",
        headers=headers,
        json={"messages": [{"role": "user", "content": "hi"}], "session_id": "thread-1"},
    )

    listing = await client.get("/api/v1/chat/sessions", headers=headers)
    assert listing.status_code == 200
    sessions = listing.json()["sessions"]
    assert len(sessions) == 1
    assert sessions[0]["id"] == "thread-1"
    assert sessions[0]["title"] == "hi"

    detail = await client.get("/api/v1/chat/sessions/thread-1", headers=headers)
    assert detail.status_code == 200
    body = detail.json()
    assert body["id"] == "thread-1"
    assert [m["content"] for m in body["messages"]] == ["hi", "hello"]


async def test_delete_session_soft_deletes(client, monkeypatch):
    monkeypatch.setattr(chat_module, "HermesClient", _StubHermesClient)
    monkeypatch.setattr(sessions_module, "HermesClient", _StubHermesClient)
    headers = auth_header(new_user_id())
    await _provision_and_wait(client, headers)

    await client.post(
        "/api/v1/chat/completions",
        headers=headers,
        json={"messages": [{"role": "user", "content": "hi"}], "session_id": "thread-1"},
    )

    deleted = await client.delete("/api/v1/chat/sessions/thread-1", headers=headers)
    assert deleted.status_code == 200
    assert deleted.json() == {"ok": True}

    listing = await client.get("/api/v1/chat/sessions", headers=headers)
    assert listing.json()["sessions"] == []

    missing = await client.get("/api/v1/chat/sessions/thread-1", headers=headers)
    assert missing.status_code == 404


async def test_sessions_are_isolated_per_user(client, monkeypatch):
    monkeypatch.setattr(chat_module, "HermesClient", _StubHermesClient)
    monkeypatch.setattr(sessions_module, "HermesClient", _StubHermesClient)
    headers_a = auth_header(new_user_id())
    headers_b = auth_header(new_user_id())
    await _provision_and_wait(client, headers_a)

    await client.post(
        "/api/v1/chat/completions",
        headers=headers_a,
        json={"messages": [{"role": "user", "content": "hi"}], "session_id": "thread-1"},
    )

    response = await client.get("/api/v1/chat/sessions/thread-1", headers=headers_b)
    assert response.status_code == 404
