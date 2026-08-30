"""The Agno database: where conversation history actually lives now.

Under Hermes each turn was stored inside the student's container, on its
volume, reachable only while that container was running — so reading last
week's conversation meant booting a 2 GB container, and losing the volume lost
the history. Agno stores runs in the same database the broker already uses, so
history is queryable, backed up with everything else, and readable whether or
not the student's agent is currently resident.

Agno's database layer is synchronous and manages its own engine, so it gets its
own URL derived from ``DATABASE_URL`` rather than sharing the app's async
engine. Same database, same tables namespace, separate pool.
"""

from functools import lru_cache

from agno.db.base import BaseDb

from app.config import get_settings
from app.logging import get_logger

logger = get_logger(__name__)

# Prefixed so Agno's tables are obviously not hand-written app tables when
# someone opens the schema, and so they can't collide with `chat_sessions`.
_SESSION_TABLE = "agno_sessions"
_RUNS_TABLE = "agno_runs"
_MEMORY_TABLE = "agno_memories"
_METRICS_TABLE = "agno_metrics"


def _sqlite_file(url: str) -> str:
    """``sqlite+aiosqlite:///./devrimo.db`` -> ``./devrimo.db``."""
    _, _, tail = url.partition(":///")
    return tail or "devrimo.db"


def _sync_postgres_url(url: str) -> str:
    """Swap an async driver for the sync one Agno's engine needs."""
    for async_driver in ("+asyncpg", "+psycopg_async"):
        url = url.replace(async_driver, "+psycopg")
    if "+psycopg" not in url:
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


@lru_cache
def get_agno_db() -> BaseDb:
    url = get_settings().database_url
    tables = {
        "session_table": _SESSION_TABLE,
        "runs_table": _RUNS_TABLE,
        "memory_table": _MEMORY_TABLE,
        "metrics_table": _METRICS_TABLE,
    }

    if url.startswith("sqlite"):
        from agno.db.sqlite import SqliteDb

        return SqliteDb(db_file=_sqlite_file(url), **tables)

    from agno.db.postgres import PostgresDb

    return PostgresDb(db_url=_sync_postgres_url(url), **tables)
