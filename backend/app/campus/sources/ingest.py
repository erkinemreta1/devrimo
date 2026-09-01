"""Running sources: on a schedule, on demand, and as a dry run.

Modelled on :mod:`app.agents.reconciler`, including the part that matters most:
the loop survives a bad iteration, and *says so*. A crawler that silently
returns nothing looks exactly like a quiet week on the site it crawls, which is
why every attempt writes a :class:`~app.db.models.CampusSourceRun` row and why
an empty result from a source that has produced items before is treated as a
failure rather than as success.

:func:`preview_source` is the same pipeline with the writes removed. It is what
makes adding a site a configuration task instead of a deploy: an admin pastes a
listing path and an item pattern, runs a preview, and sees the parsed items
before anything is embedded or stored.
"""

import asyncio
import time
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.campus.sources.adapters import AdapterContext, get_adapter
from app.campus.sources.documents import CampusDocument, to_documents
from app.campus.sources.fetch import CampusFetcher
from app.campus.sources.models import IngestStats, SourceError, SourceItem, SourceSpec
from app.campus.sources.registry import due_sources, spec_from_row
from app.config import get_settings
from app.db.models import CampusSource, CampusSourceRun
from app.db.session import SessionLocal
from app.knowledge import store as knowledge_store
from app.logging import get_logger
from app.observability import capture, capture_exception

logger = get_logger(__name__)

# Adapters for which parsing nothing is an ordinary state rather than a failure.
# For a scraped site an empty result means the page changed shape and the source
# has silently stopped working — that is the whole reason runs are recorded. The
# curated adapter is different: it reads a table an admin fills in, and "no
# entries yet" is exactly what a fresh deployment looks like. Reporting that as
# a broken source trains operators to ignore the one signal this module exists
# to give them.
EMPTY_IS_NORMAL = frozenset({"curated"})


class IngestResult:
    """What one source's run produced, whether or not it succeeded."""

    def __init__(self, spec: SourceSpec) -> None:
        self.spec = spec
        self.stats = IngestStats()
        self.status = "ok"
        self.error: str | None = None
        self.error_code: str | None = None
        self.duration_ms = 0
        self.items: list[SourceItem] = []
        self.documents: list[CampusDocument] = []

    def as_dict(self) -> dict:
        return {
            "source": self.spec.slug,
            "status": self.status,
            "items_seen": self.stats.items_seen,
            "items_written": self.stats.items_written,
            "items_unchanged": self.stats.items_unchanged,
            "requests_made": self.stats.requests_made,
            "bytes_fetched": self.stats.bytes_fetched,
            "duration_ms": self.duration_ms,
            "error": self.error,
            "error_code": self.error_code,
        }


async def collect_items(spec: SourceSpec, *, db: AsyncSession | None = None) -> tuple[list[SourceItem], IngestStats]:
    """Fetch and parse one source. No database writes, no embedding."""
    stats = IngestStats()
    adapter = get_adapter(spec.adapter)
    timeout = float(spec.config.get("timeout_seconds") or get_settings().campus_ingest_source_timeout_seconds)

    async with CampusFetcher() as fetcher:
        try:
            items = await asyncio.wait_for(
                adapter(AdapterContext(spec=spec, fetcher=fetcher, db=db)),
                timeout=timeout,
            )
        except TimeoutError as exc:
            stats.merge_fetch(fetcher.requests_made, fetcher.bytes_fetched)
            raise SourceError("timeout", f"{spec.slug} exceeded {timeout:g}s") from exc
        finally:
            stats.merge_fetch(fetcher.requests_made, fetcher.bytes_fetched)

    stats.items_seen = len(items)
    return items, stats


async def preview_source(spec: SourceSpec, *, db: AsyncSession | None = None, limit: int = 10) -> dict:
    """Parse a source without writing anything.

    The acceptance test for configurability: a non-conforming department site
    should become answerable by filling in this form, and this is where an
    admin finds out whether it did — before the corpus is touched.
    """
    started = time.monotonic()
    try:
        items, stats = await collect_items(spec, db=db)
    except SourceError as exc:
        return {
            "ok": False,
            "error": exc.message,
            "error_code": exc.code,
            "items": [],
            "items_seen": 0,
            "duration_ms": round((time.monotonic() - started) * 1000),
        }

    documents = to_documents(spec, items)
    # An adapter that parsed nothing is the failure this whole module is built
    # to make visible, so a preview says so rather than showing an innocuous
    # empty list — except where empty is legitimate (see EMPTY_IS_NORMAL).
    empty_is_failure = not items and spec.adapter not in EMPTY_IS_NORMAL
    return {
        "ok": not empty_is_failure,
        "error": "The adapter parsed no items from this source" if empty_is_failure else None,
        "error_code": "empty_result" if empty_is_failure else None,
        "items_seen": len(items),
        "documents": len(documents),
        "duration_ms": round((time.monotonic() - started) * 1000),
        "requests_made": stats.requests_made,
        "bytes_fetched": stats.bytes_fetched,
        "items": [
            {
                "title": item.title,
                "url": item.url,
                "language": item.language,
                "published_at": item.published_at.isoformat() if item.published_at else None,
                "body_preview": item.body[:400],
                "extra": item.extra,
            }
            for item in items[:limit]
        ],
    }


def _write_documents(spec: SourceSpec, documents: list[CampusDocument], stats: IngestStats) -> None:
    """Embed and store what actually changed.

    Runs in a worker thread because Agno's vector layer is synchronous and this
    is the one genuinely slow step — embedding a hundred documents would
    otherwise block the event loop, and with it every student's chat turn.
    """
    known = knowledge_store.existing_hashes(spec.slug)
    changed = [doc for doc in documents if known.get(doc.doc_id) != doc.content_hash]
    stats.items_unchanged = len(documents) - len(changed)
    if changed:
        stats.items_written = knowledge_store.upsert_documents(changed, source_slug=spec.slug)


async def run_source(db: AsyncSession, row: CampusSource) -> IngestResult:
    """Ingest one source and record the attempt."""
    spec = spec_from_row(row)
    result = IngestResult(spec)
    started = time.monotonic()

    try:
        items, stats = await collect_items(spec, db=db)
        result.stats = stats
        result.items = items
        if not items and spec.adapter not in EMPTY_IS_NORMAL:
            raise SourceError("empty_result", "The adapter parsed no items from this source")

        result.documents = to_documents(spec, items)
        if knowledge_store.knowledge_available():
            knowledge_store.ensure_schema()
            await asyncio.to_thread(_write_documents, spec, result.documents, result.stats)
        else:
            # Nothing to write to, but the parse still happened and its item
            # count is the useful signal on a deployment without embeddings.
            result.status = "parsed_only"
    except SourceError as exc:
        result.status = "failed"
        result.error = exc.message
        result.error_code = exc.code
        logger.warning("campus_source_failed", source=spec.slug, code=exc.code, error=exc.message)
        capture_exception(
            exc,
            source=spec.slug,
            # Grouped per source, the same choice app.agents.toolset makes per
            # campus server: every one of these is "this site stopped working",
            # and one issue per site is the shape an operator can act on.
            **{"$exception_fingerprint": ["campus_source_failed", spec.slug]},
        )
    except Exception as exc:  # an adapter bug must not take the loop down
        result.status = "failed"
        result.error = f"{exc.__class__.__name__}: {exc}"
        result.error_code = "adapter_error"
        logger.error("campus_source_crashed", source=spec.slug, error=str(exc))
        capture_exception(exc, source=spec.slug, **{"$exception_fingerprint": ["campus_source_crashed", spec.slug]})

    result.duration_ms = round((time.monotonic() - started) * 1000)
    await _record_run(db, row, result)
    capture("campus_source_ingested", **result.as_dict())
    logger.info("campus_source_ingested", **result.as_dict())
    return result


async def _record_run(db: AsyncSession, row: CampusSource, result: IngestResult) -> None:
    now = datetime.now(UTC)
    db.add(
        CampusSourceRun(
            source_id=row.id,
            status=result.status,
            items_seen=result.stats.items_seen,
            items_written=result.stats.items_written,
            items_unchanged=result.stats.items_unchanged,
            requests_made=result.stats.requests_made,
            bytes_fetched=result.stats.bytes_fetched,
            duration_ms=result.duration_ms,
            error=result.error,
        )
    )
    row.last_run_at = now
    row.last_status = result.status
    row.last_error = result.error[:1000] if result.error else None
    # A failing source backs off to a quarter of its interval rather than
    # retrying on every tick: a site that is down stays down for a while, and
    # hammering it is both rude and pointless.
    delay = row.refresh_seconds if result.status != "failed" else max(300, row.refresh_seconds // 4)
    row.next_run_at = now + timedelta(seconds=delay)
    await db.commit()


async def run_due_sources(db: AsyncSession, *, limit: int = 3) -> list[IngestResult]:
    """Ingest whatever is due, most urgent first."""
    rows = await due_sources(db, limit=limit)
    return [await run_source(db, row) for row in rows]


async def run_ingest_loop(stop_event: asyncio.Event) -> None:
    """The background loop, wired into the app lifespan.

    Sources are seeded once on the first tick rather than at import, so a fresh
    database gets a working corpus without anyone running a script, and an
    admin's later edits are never re-applied over.
    """
    settings = get_settings()
    if not settings.campus_knowledge_enabled:
        logger.info("campus_ingest_disabled")
        return

    from app.campus.sources.registry import ensure_seeded

    seeded = False
    while not stop_event.is_set():
        try:
            async with SessionLocal() as db:
                if not seeded:
                    await ensure_seeded(db)
                    seeded = True
                await run_due_sources(db)
        except Exception as exc:
            # Same reasoning as the reconciler: the loop deliberately survives a
            # bad iteration, which is exactly why nothing would otherwise notice
            # it failing every tick.
            logger.error("campus_ingest_iteration_failed", error=str(exc))
            capture_exception(exc, **{"$exception_fingerprint": ["campus_ingest_iteration_failed"]})
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=settings.campus_ingest_interval_seconds)
        except TimeoutError:
            pass


async def run_source_by_id(db: AsyncSession, source_id: UUID) -> IngestResult | None:
    row = await db.get(CampusSource, source_id)
    return await run_source(db, row) if row is not None else None
