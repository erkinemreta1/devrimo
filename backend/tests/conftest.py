import os
import tempfile
import time
import uuid
from pathlib import Path

os.environ["AGENT_RUNTIME"] = "fake"
# Belt and braces: the Agent is constructed with telemetry=False, but a test
# must never be able to reach os-api.agno.com even if that regresses.
os.environ["AGNO_TELEMETRY"] = "false"
os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-secret-not-for-production")
os.environ.setdefault("SECRET_ENCRYPTION_KEY", "test-encryption-key")
os.environ.setdefault("AGENT_IDLE_TIMEOUT_SECONDS", "3600")

_tmp_root = Path(tempfile.gettempdir()) / f"devrimo-test-{uuid.uuid4().hex}"
_tmp_root.mkdir(parents=True, exist_ok=True)
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmp_root / 'devrimo.db'}"
# Campus servers are never actually launched under AGENT_RUNTIME=fake, but the
# spec renderer still builds paths from these and the toolset builder still
# creates working directories — both of which must stay inside the sandbox.
os.environ["CAMPUS_MCP_ROOT"] = str(_tmp_root / "mcp")
os.environ["CAMPUS_STATE_ROOT"] = str(_tmp_root / "state")

import httpx
import jwt as pyjwt
import pytest
from sqlalchemy import text

from app.agents.pool import reset_pool
from app.agents.store import get_agno_db
from app.db.base import Base
from app.db.session import engine
from app.main import app

CAMPUS_MCP_ROOT = os.environ["CAMPUS_MCP_ROOT"]
CAMPUS_STATE_ROOT = os.environ["CAMPUS_STATE_ROOT"]


async def _drop_agno_tables(conn) -> None:
    """Agno creates its own tables, so ``Base.metadata`` cannot drop them.

    Without this they outlive the fixture and a session id reused by a later
    test resolves to the previous test's user — which looks exactly like a
    cross-user history leak, and would mask a real one.
    """
    result = await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'agno_%'"))
    for (table,) in result.fetchall():
        await conn.execute(text(f'DROP TABLE IF EXISTS "{table}"'))


@pytest.fixture(autouse=True)
async def _fresh_schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await reset_pool()
    # The Agno db caches which of its tables it has already created, so it must
    # be rebuilt alongside the schema or it will write to tables the previous
    # test's teardown dropped.
    get_agno_db.cache_clear()
    yield
    # Resident agents hold MCP subprocesses; a test that leaves one behind
    # leaks it into the next test's pool.
    await reset_pool()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await _drop_agno_tables(conn)


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
