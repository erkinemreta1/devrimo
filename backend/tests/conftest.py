import os
import tempfile
import time
import uuid
from pathlib import Path

os.environ.setdefault("AGENT_RUNTIME", "fake")
os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-secret-not-for-production")
os.environ.setdefault("SECRET_ENCRYPTION_KEY", "test-encryption-key")
os.environ.setdefault("AGENT_START_TIMEOUT_SECONDS", "2")
os.environ.setdefault("AGENT_IDLE_TIMEOUT_SECONDS", "3600")

_tmp_db = Path(tempfile.gettempdir()) / f"devrimo-test-{uuid.uuid4().hex}.db"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmp_db}"

import httpx
import jwt as pyjwt
import pytest

from app.agents import manager
from app.db.base import Base
from app.db.session import engine
from app.main import app


@pytest.fixture(autouse=True)
async def _fresh_schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    manager.get_runtime.cache_clear()
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def new_user_id() -> uuid.UUID:
    return uuid.uuid4()


def auth_header(user_id: uuid.UUID) -> dict[str, str]:
    token = pyjwt.encode(
        {
            "sub": str(user_id),
            "aud": "authenticated",
            "exp": int(time.time()) + 3600,
            "email": f"{user_id}@example.edu",
        },
        os.environ["SUPABASE_JWT_SECRET"],
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}
