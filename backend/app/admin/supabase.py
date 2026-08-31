from datetime import datetime
from typing import Any
from uuid import UUID

import httpx

from app.config import get_settings


class SupabaseAdmin:
    def __init__(self) -> None:
        settings = get_settings()
        self.base_url = f"{settings.supabase_url.rstrip('/')}/auth/v1/admin"
        self.key = settings.supabase_secret_key

    def _headers(self) -> dict[str, str]:
        if not self.base_url.startswith("http") or not self.key:
            raise RuntimeError("Supabase Auth Admin is not configured")
        return {"apikey": self.key, "Authorization": f"Bearer {self.key}"}

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.request(method, f"{self.base_url}{path}", headers=self._headers(), **kwargs)
        response.raise_for_status()
        return response.json() if response.content else None

    async def invite(self, email: str) -> dict:
        return await self._request("POST", "/invite", json={"email": email})

    async def update_user(self, user_id: UUID, **values: Any) -> dict:
        return await self._request("PUT", f"/users/{user_id}", json=values)

    async def delete_user(self, user_id: UUID) -> None:
        try:
            await self._request("DELETE", f"/users/{user_id}")
        except httpx.HTTPStatusError as exc:
            # A prior deletion attempt may have completed remotely before a
            # local cleanup failed. Treating 404 as success makes retry safe.
            if exc.response.status_code != 404:
                raise

    async def list_users(self, page: int = 1, per_page: int = 1000) -> list[dict]:
        payload = await self._request("GET", "/users", params={"page": page, "per_page": per_page})
        return payload.get("users", payload if isinstance(payload, list) else [])


def parse_auth_time(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
