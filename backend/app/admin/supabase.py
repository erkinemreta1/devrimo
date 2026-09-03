import asyncio
from datetime import datetime
from functools import lru_cache
from typing import Any
from uuid import UUID

from supabase import Client, create_client
from supabase.client import ClientOptions
from supabase_auth.errors import AuthApiError

from app.config import get_settings


@lru_cache
def _client() -> Client:
    settings = get_settings()
    if not settings.supabase_url.startswith("http") or not settings.supabase_secret_key:
        raise RuntimeError("Supabase Auth Admin is not configured")
    return create_client(
        settings.supabase_url,
        settings.supabase_secret_key,
        options=ClientOptions(auto_refresh_token=False, persist_session=False),
    )


def _serialized(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_serialized(item) for item in value]
    return value


class SupabaseAdmin:
    @property
    def auth(self):
        return _client().auth.admin

    async def invite(self, email: str) -> dict:
        response = await asyncio.to_thread(self.auth.invite_user_by_email, email)
        return _serialized(response)

    async def update_user(self, user_id: UUID, **values: Any) -> dict:
        response = await asyncio.to_thread(self.auth.update_user_by_id, str(user_id), values)
        return _serialized(response)

    async def delete_user(self, user_id: UUID) -> None:
        try:
            await asyncio.to_thread(self.auth.delete_user, str(user_id))
        except AuthApiError as exc:
            # A prior deletion attempt may have completed remotely before a
            # local cleanup failed. Treating 404 as success makes retry safe.
            if str(getattr(exc, "status", getattr(exc, "code", ""))) != "404":
                raise

    async def list_users(self, page: int = 1, per_page: int = 1000) -> list[dict]:
        response = await asyncio.to_thread(self.auth.list_users, page=page, per_page=per_page)
        payload = _serialized(response)
        if isinstance(payload, dict):
            return payload.get("users", [])
        return payload if isinstance(payload, list) else []


def parse_auth_time(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
