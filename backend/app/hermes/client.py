"""A typed client for exactly one user's Hermes container.

Chat completions are proxied as raw bytes — Hermes already speaks
OpenAI-compatible SSE (``chat.completion.chunk`` objects with
``choices[0].delta.content``), which is exactly what
``frontend/lib/api/chat.ts``'s ``streamChatCompletions`` parses. Re-parsing
and re-serializing that stream here would just be a chance to get it wrong.
"""

from collections.abc import AsyncIterator
from typing import Any

import httpx


class HermesError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class HermesClient:
    def __init__(self, base_url: str, api_key: str, model: str = "hermes"):
        self._base_url = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._model = model

    async def stream_chat_completions(
        self,
        messages: list[dict[str, str]],
        hermes_session_id: str,
    ) -> AsyncIterator[bytes]:
        payload = {"model": self._model, "messages": messages, "stream": True}
        headers = {
            **self._headers,
            "Accept": "text/event-stream",
            "Content-Type": "application/json",
            "X-Hermes-Session-Id": hermes_session_id,
        }

        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, read=120.0)) as client:
            async with client.stream(
                "POST", f"{self._base_url}/v1/chat/completions", json=payload, headers=headers
            ) as response:
                if response.status_code != 200:
                    body = await response.aread()
                    raise HermesError(response.status_code, body.decode("utf-8", errors="replace"))
                async for chunk in response.aiter_bytes():
                    yield chunk

    async def list_messages(self, hermes_session_id: str) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{self._base_url}/api/sessions/{hermes_session_id}/messages", headers=self._headers
            )
        if response.status_code == 404:
            return []
        if response.status_code != 200:
            raise HermesError(response.status_code, response.text)

        data = response.json()
        raw_messages = data if isinstance(data, list) else data.get("messages", [])
        return [_normalize_message(item) for item in raw_messages]

    async def delete_session(self, hermes_session_id: str) -> None:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.delete(
                f"{self._base_url}/api/sessions/{hermes_session_id}", headers=self._headers
            )
        if response.status_code not in (200, 204, 404):
            raise HermesError(response.status_code, response.text)


def _normalize_message(item: dict[str, Any]) -> dict[str, Any]:
    role = item.get("role", "assistant")
    return {
        "role": role,
        "content": item.get("content") or item.get("text") or "",
        "created_at": item.get("created_at") or item.get("timestamp"),
    }
