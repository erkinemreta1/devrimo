"""The pgvector-backed corpus: construction, upsert, and search.

Unavailable is a first-class state here, not an error. Three ordinary
situations leave this service with no corpus — the operator turned it off, the
database is SQLite (the whole test suite, and most local development), or no
embedding key is configured — and in every one of them Scholar has to come up
exactly as it does today, with its campus MCP tools and no campus search. So
every entry point returns ``None`` rather than raising, and
:func:`knowledge_available` is what callers branch on.

Embeddings are bought from an OpenAI-compatible endpoint. That choice has one
consequence worth stating where it will be read: **changing the model or the
dimension invalidates every stored vector**, because the existing rows were
embedded in a different space and their distances to a new query mean nothing.
The admin surface offers a reindex for exactly that reason, and the schema
records which model wrote each row so the mismatch is detectable rather than
mysterious.
"""

from dataclasses import dataclass
from typing import Any

from app.config import get_settings
from app.logging import get_logger
from app.observability import capture_exception

logger = get_logger(__name__)

_vector_db: Any | None = None
_vector_db_signature: tuple | None = None


@dataclass(frozen=True)
class SearchHit:
    """One retrieved document, with what a citation needs."""

    content: str
    meta_data: dict[str, Any]
    score: float | None = None


def knowledge_available() -> bool:
    return get_settings().knowledge_configured


def _sync_db_url() -> str:
    """The async ``DATABASE_URL`` as the sync URL PgVector builds its engine from.

    Agno's vector layer is synchronous and makes its own engine, which is why
    ``psycopg[binary]`` is already a dependency alongside ``asyncpg`` — see the
    note in ``requirements.txt``.
    """
    url = get_settings().database_url
    return url.replace("+asyncpg", "").replace("postgresql://", "postgresql+psycopg://", 1)


def _build_embedder():
    settings = get_settings()
    from agno.knowledge.embedder.openai import OpenAIEmbedder

    return OpenAIEmbedder(
        id=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
        api_key=settings.embedding_api_key,
        base_url=settings.embedding_base_url or None,
    )


def campus_vector_db():
    """The shared :class:`PgVector` for the campus corpus, or ``None``.

    Cached on the settings that define the vector space. If any of them change
    the cache is rebuilt rather than silently reused, because a client pointed
    at a table whose rows were embedded by a different model returns confident
    nonsense instead of an error.
    """
    global _vector_db, _vector_db_signature
    if not knowledge_available():
        return None

    settings = get_settings()
    signature = (
        settings.database_url,
        settings.campus_knowledge_table,
        settings.campus_knowledge_schema,
        settings.embedding_model,
        settings.embedding_dimensions,
    )
    if _vector_db is not None and _vector_db_signature == signature:
        return _vector_db

    try:
        from agno.vectordb.pgvector import PgVector
        from agno.vectordb.search import SearchType

        _vector_db = PgVector(
            table_name=settings.campus_knowledge_table,
            schema=settings.campus_knowledge_schema,
            db_url=_sync_db_url(),
            embedder=_build_embedder(),
            # Hybrid rather than pure vector: campus questions are full of
            # exact tokens a nearest-neighbour search dilutes — course codes
            # ("CENG315"), building names, and "meturoam". The lexical half
            # catches those, the vector half carries the Turkish/English
            # paraphrases that a keyword index alone would miss.
            search_type=SearchType.hybrid,
        )
        _vector_db_signature = signature
    except Exception as exc:
        logger.error("campus_vector_db_unavailable", error=str(exc))
        capture_exception(exc, **{"$exception_fingerprint": ["campus_vector_db_unavailable"]})
        _vector_db = None
        _vector_db_signature = None
    return _vector_db


def reset_knowledge() -> None:
    """Drop the cached client. Used by tests and after a settings change."""
    global _vector_db, _vector_db_signature
    _vector_db = None
    _vector_db_signature = None


def ensure_schema() -> bool:
    """Create the table and index if they are not there yet."""
    vector_db = campus_vector_db()
    if vector_db is None:
        return False
    try:
        if not vector_db.exists():
            vector_db.create()
        return True
    except Exception as exc:
        logger.error("campus_vector_schema_failed", error=str(exc))
        capture_exception(exc, **{"$exception_fingerprint": ["campus_vector_schema_failed"]})
        return False


def existing_hashes(source_slug: str) -> dict[str, str]:
    """``{doc_id: content_hash}`` already stored for one source.

    This is the query that keeps the embedding bill flat: an item whose hash
    is unchanged is never sent to the embedding API again.
    """
    vector_db = campus_vector_db()
    if vector_db is None:
        return {}
    try:
        from sqlalchemy import select

        table = vector_db.table
        statement = select(table.c.id, table.c.meta_data).where(
            table.c.meta_data["source_slug"].astext == source_slug
        )
        with vector_db.Session() as session:
            rows = session.execute(statement).fetchall()
        return {row[0]: (row[1] or {}).get("content_hash", "") for row in rows}
    except Exception as exc:
        # Losing this only costs money, never correctness: an empty mapping
        # means everything looks new and gets re-embedded.
        logger.warning("campus_vector_hashes_failed", source=source_slug, error=str(exc))
        return {}


def upsert_documents(documents: list, *, source_slug: str) -> int:
    """Write documents to the corpus, returning how many were written."""
    vector_db = campus_vector_db()
    if vector_db is None or not documents:
        return 0
    from agno.knowledge.document import Document

    payload = [
        Document(id=doc.doc_id, name=doc.name, content=doc.content, meta_data=dict(doc.meta_data))
        for doc in documents
    ]
    vector_db.upsert(content_hash=source_slug, documents=payload)
    return len(payload)


def delete_source(source_slug: str) -> int:
    """Remove every document a source contributed.

    Called when a source is deleted or reconfigured beyond recognition. Without
    it, disabling a source leaves its documents answering questions forever.
    """
    vector_db = campus_vector_db()
    if vector_db is None:
        return 0
    try:
        from sqlalchemy import delete

        table = vector_db.table
        statement = delete(table).where(table.c.meta_data["source_slug"].astext == source_slug)
        with vector_db.Session() as session, session.begin():
            result = session.execute(statement)
        return int(result.rowcount or 0)
    except Exception as exc:
        logger.error("campus_vector_delete_failed", source=source_slug, error=str(exc))
        capture_exception(exc, source=source_slug, **{"$exception_fingerprint": ["campus_vector_delete_failed"]})
        return 0


def document_counts() -> dict[str, int]:
    """Documents per source, for the admin knowledge view."""
    vector_db = campus_vector_db()
    if vector_db is None:
        return {}
    try:
        from sqlalchemy import func, select

        table = vector_db.table
        slug = table.c.meta_data["source_slug"].astext
        statement = select(slug, func.count()).group_by(slug)
        with vector_db.Session() as session:
            return {row[0] or "(unknown)": int(row[1]) for row in session.execute(statement).fetchall()}
    except Exception as exc:
        logger.warning("campus_vector_counts_failed", error=str(exc))
        return {}


async def search(query: str, *, limit: int) -> list[SearchHit]:
    """Nearest documents for a query, before any per-student filtering.

    Filtering is deliberately not done here. Agno's PgVector filter DSL compares
    a metadata key to a scalar, and this corpus scopes documents by *lists* —
    a document can be for several departments, or for none in particular. So
    the store returns candidates and :mod:`app.knowledge.retrieval` applies the
    audience rules in Python, where list semantics are expressible.
    """
    vector_db = campus_vector_db()
    if vector_db is None:
        return []
    documents = await vector_db.async_search(query=query, limit=limit)
    return [
        SearchHit(
            content=document.content or "",
            meta_data=dict(document.meta_data or {}),
            score=getattr(document, "score", None),
        )
        for document in documents
    ]
