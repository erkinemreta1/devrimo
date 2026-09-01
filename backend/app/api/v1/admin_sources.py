"""Admin control of the campus knowledge layer.

This module is where "configurability is a requirement" becomes an interface.
Everything the corpus is built from is editable here — which sites, how they
are parsed, how often, who they apply to, what curated entries exist, and the
grading rules the semester planner uses — with the same audit trail as every
other admin action.

The route worth pointing at is ``POST /sources/preview``. It runs the whole
pipeline and writes nothing, so adding a department that does not follow the
common Drupal shape is an admin filling in a form and pressing a button until
the parsed items look right. That is the difference between a registry and a
folder full of scrapers.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.audit import record_event
from app.admin.auth import AdminPermission, AdminPrincipal, require
from app.admin.schemas import CampusSourceIn, CampusSourcePreviewIn, CuratedEntryIn, GradePolicyIn, ReasonIn
from app.campus.policy import POLICY_ID, ensure_policy_seeded, load_grade_policy, policy_as_dict, policy_from_row
from app.campus.sources import ingest
from app.campus.sources.models import ADAPTER_IDS, SOURCE_KINDS, SourceSpec
from app.campus.sources.registry import ensure_seeded
from app.config import get_settings
from app.db.models import CampusCuratedEntry, CampusGradePolicy, CampusSource, CampusSourceRun
from app.db.session import get_db
from app.knowledge import store as knowledge_store
from app.logging import get_logger

router = APIRouter()
logger = get_logger(__name__)


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def _source_dict(row: CampusSource) -> dict:
    return {
        "id": str(row.id),
        "slug": row.slug,
        "name": row.name,
        "enabled": row.enabled,
        "adapter": row.adapter,
        "kind": row.kind,
        "base_url": row.base_url,
        "config": row.config or {},
        "encoding": row.encoding,
        "languages": row.languages or [],
        "departments": row.departments or [],
        "degree_levels": row.degree_levels or [],
        "audience_rules": row.audience_rules or {},
        "refresh_seconds": row.refresh_seconds,
        "max_pages": row.max_pages,
        "max_items": row.max_items,
        "priority": row.priority,
        "next_run_at": _iso(row.next_run_at),
        "last_run_at": _iso(row.last_run_at),
        "last_status": row.last_status,
        "last_error": row.last_error,
        "revision": row.revision,
        "updated_at": _iso(row.updated_at),
    }


def _curated_dict(row: CampusCuratedEntry) -> dict:
    return {
        "id": str(row.id),
        "kind": row.kind,
        "entry_key": row.entry_key,
        "title": row.title,
        "body": row.body,
        "url": row.url,
        "language": row.language,
        "departments": row.departments or [],
        "degree_levels": row.degree_levels or [],
        "tags": row.tags or [],
        "valid_from": _iso(row.valid_from),
        "valid_until": _iso(row.valid_until),
        "enabled": row.enabled,
        "updated_at": _iso(row.updated_at),
    }


def _apply(row: CampusSource, body: CampusSourceIn) -> None:
    row.slug = body.slug
    row.name = body.name
    row.adapter = body.adapter
    row.kind = body.kind
    row.base_url = body.base_url
    row.config = dict(body.config)
    row.encoding = body.encoding
    row.languages = list(body.languages)
    row.departments = list(body.departments)
    row.degree_levels = list(body.degree_levels)
    row.audience_rules = dict(body.audience_rules)
    row.refresh_seconds = body.refresh_seconds
    row.max_pages = body.max_pages
    row.max_items = body.max_items
    row.priority = body.priority
    row.enabled = body.enabled


async def _get_source(db: AsyncSession, source_id: UUID) -> CampusSource:
    row = await db.get(CampusSource, source_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Source not found")
    return row


@router.get("/sources")
async def list_sources(
    principal: AdminPrincipal = Depends(require(AdminPermission.sources_read)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    # Seeded lazily on first view as well as on the ingest loop's first tick, so
    # a fresh deployment shows a working registry rather than an empty page.
    await ensure_seeded(db)
    rows = (await db.execute(select(CampusSource).order_by(CampusSource.priority, CampusSource.slug))).scalars().all()
    counts = knowledge_store.document_counts()
    return {
        "sources": [{**_source_dict(row), "documents": counts.get(row.slug, 0)} for row in rows],
        "adapters": list(ADAPTER_IDS),
        "kinds": list(SOURCE_KINDS),
        "editable": AdminPermission.sources_write in principal.permissions,
        "runnable": AdminPermission.sources_run in principal.permissions,
        "knowledge_configured": knowledge_store.knowledge_available(),
    }


@router.post("/sources", status_code=status.HTTP_201_CREATED)
async def create_source(
    body: CampusSourceIn,
    principal: AdminPrincipal = Depends(require(AdminPermission.sources_write)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    existing = await db.scalar(select(CampusSource).where(CampusSource.slug == body.slug))
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"A source with slug {body.slug!r} already exists")
    row = CampusSource(revision=1)
    _apply(row, body)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    await record_event(
        db,
        actor_user_id=principal.user.id,
        action="campus_source.create",
        result="success",
        reason=body.reason,
        after=_source_dict(row),
    )
    return _source_dict(row)


@router.put("/sources/{source_id}")
async def update_source(
    source_id: UUID,
    body: CampusSourceIn,
    principal: AdminPrincipal = Depends(require(AdminPermission.sources_write)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    row = await _get_source(db, source_id)
    before = _source_dict(row)
    clashing = await db.scalar(
        select(CampusSource).where(CampusSource.slug == body.slug, CampusSource.id != source_id)
    )
    if clashing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"A source with slug {body.slug!r} already exists")

    previous_slug = row.slug
    _apply(row, body)
    row.revision = (row.revision or 0) + 1
    row.updated_by = principal.user.id
    # An edit is a reason to re-crawl now rather than at the next interval: the
    # admin just changed how this site is parsed and wants to see the effect.
    row.next_run_at = None
    await db.commit()
    await db.refresh(row)

    if previous_slug != row.slug:
        # Documents carry the slug in their metadata, so a rename would
        # otherwise orphan every document the old slug wrote — invisible in
        # the admin view, still answering questions.
        removed = knowledge_store.delete_source(previous_slug)
        logger.info("campus_source_renamed", was=previous_slug, now=row.slug, documents_removed=removed)

    await record_event(
        db,
        actor_user_id=principal.user.id,
        action="campus_source.update",
        result="success",
        reason=body.reason,
        before=before,
        after=_source_dict(row),
    )
    return _source_dict(row)


@router.delete("/sources/{source_id}")
async def delete_source(
    source_id: UUID,
    body: ReasonIn,
    principal: AdminPrincipal = Depends(require(AdminPermission.sources_write)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    row = await _get_source(db, source_id)
    before = _source_dict(row)
    removed = knowledge_store.delete_source(row.slug)
    await db.delete(row)
    await db.commit()
    await record_event(
        db,
        actor_user_id=principal.user.id,
        action="campus_source.delete",
        result="success",
        reason=body.reason,
        before=before,
        after={"documents_removed": removed},
    )
    return {"deleted": True, "documents_removed": removed}


@router.post("/sources/preview")
async def preview_source(
    body: CampusSourcePreviewIn,
    principal: AdminPrincipal = Depends(require(AdminPermission.sources_write)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Run a source configuration without storing anything.

    Not audit-logged: it changes nothing, and an admin iterating on a selector
    would otherwise fill the audit trail with attempts.
    """
    spec = SourceSpec(
        slug=body.slug,
        name=body.name,
        adapter=body.adapter,
        kind=body.kind,
        base_url=body.base_url,
        config=dict(body.config),
        encoding=body.encoding,
        languages=tuple(body.languages),
        departments=tuple(body.departments),
        degree_levels=tuple(body.degree_levels),
        audience_rules=dict(body.audience_rules),
        refresh_seconds=body.refresh_seconds,
        max_pages=body.max_pages,
        max_items=body.max_items,
        priority=body.priority,
    )
    return await ingest.preview_source(spec, db=db, limit=body.limit)


@router.post("/sources/{source_id}/run")
async def run_source(
    source_id: UUID,
    principal: AdminPrincipal = Depends(require(AdminPermission.sources_run)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    row = await _get_source(db, source_id)
    result = await ingest.run_source(db, row)
    await record_event(
        db,
        actor_user_id=principal.user.id,
        action="campus_source.run",
        result="success" if result.status != "failed" else "failure",
        reason=f"Manual ingest of {row.slug}",
        after=result.as_dict(),
    )
    return {**result.as_dict(), "source_id": str(row.id)}


@router.get("/sources/{source_id}/runs")
async def source_runs(
    source_id: UUID,
    limit: int = Query(default=20, ge=1, le=100),
    principal: AdminPrincipal = Depends(require(AdminPermission.sources_read)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _get_source(db, source_id)
    rows = (
        (
            await db.execute(
                select(CampusSourceRun)
                .where(CampusSourceRun.source_id == source_id)
                .order_by(desc(CampusSourceRun.started_at))
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return {
        "runs": [
            {
                "id": str(run.id),
                "status": run.status,
                "items_seen": run.items_seen,
                "items_written": run.items_written,
                "items_unchanged": run.items_unchanged,
                "requests_made": run.requests_made,
                "bytes_fetched": run.bytes_fetched,
                "duration_ms": run.duration_ms,
                "error": run.error,
                "started_at": _iso(run.started_at),
            }
            for run in rows
        ]
    }


@router.get("/knowledge")
async def knowledge_overview(
    principal: AdminPrincipal = Depends(require(AdminPermission.sources_read)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    settings = get_settings()
    counts = knowledge_store.document_counts()
    return {
        "configured": knowledge_store.knowledge_available(),
        "embedding_model": settings.embedding_model,
        "embedding_dimensions": settings.embedding_dimensions,
        "table": f"{settings.campus_knowledge_schema}.{settings.campus_knowledge_table}",
        "documents_by_source": counts,
        "documents_total": sum(counts.values()),
        # Stated because it is the trap of a hosted-embedding corpus: the
        # stored vectors belong to whichever model wrote them, and changing the
        # model without a reindex leaves confident nonsense behind.
        "reindex_required_after_model_change": True,
        "can_manage": AdminPermission.knowledge_manage in principal.permissions,
    }


@router.post("/knowledge/reindex")
async def reindex_knowledge(
    body: ReasonIn,
    principal: AdminPrincipal = Depends(require(AdminPermission.knowledge_manage)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Drop every document and schedule every enabled source to re-crawl.

    The operation to run after changing the embedding model or dimension, when
    the stored vectors were written in a space the new queries do not share.
    """
    rows = (await db.execute(select(CampusSource))).scalars().all()
    removed = sum(knowledge_store.delete_source(row.slug) for row in rows)
    for row in rows:
        row.next_run_at = None
    await db.commit()
    await record_event(
        db,
        actor_user_id=principal.user.id,
        action="campus_knowledge.reindex",
        result="success",
        reason=body.reason,
        after={"documents_removed": removed, "sources_scheduled": len(rows)},
    )
    return {"documents_removed": removed, "sources_scheduled": len(rows)}


@router.get("/curated")
async def list_curated(
    principal: AdminPrincipal = Depends(require(AdminPermission.sources_read)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    rows = (
        (await db.execute(select(CampusCuratedEntry).order_by(CampusCuratedEntry.kind, CampusCuratedEntry.title)))
        .scalars()
        .all()
    )
    return {
        "entries": [_curated_dict(row) for row in rows],
        "editable": AdminPermission.curated_write in principal.permissions,
    }


@router.post("/curated", status_code=status.HTTP_201_CREATED)
async def create_curated(
    body: CuratedEntryIn,
    principal: AdminPrincipal = Depends(require(AdminPermission.curated_write)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    row = CampusCuratedEntry(
        kind=body.kind,
        entry_key=body.entry_key,
        title=body.title,
        body=body.body,
        url=body.url,
        language=body.language,
        departments=list(body.departments),
        degree_levels=list(body.degree_levels),
        tags=list(body.tags),
        valid_from=body.valid_from,
        valid_until=body.valid_until,
        enabled=body.enabled,
        updated_by=principal.user.id,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    await record_event(
        db,
        actor_user_id=principal.user.id,
        action="curated_entry.create",
        result="success",
        reason=body.reason,
        after=_curated_dict(row),
    )
    return _curated_dict(row)


@router.put("/curated/{entry_id}")
async def update_curated(
    entry_id: UUID,
    body: CuratedEntryIn,
    principal: AdminPrincipal = Depends(require(AdminPermission.curated_write)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    row = await db.get(CampusCuratedEntry, entry_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Entry not found")
    before = _curated_dict(row)
    row.kind = body.kind
    row.entry_key = body.entry_key
    row.title = body.title
    row.body = body.body
    row.url = body.url
    row.language = body.language
    row.departments = list(body.departments)
    row.degree_levels = list(body.degree_levels)
    row.tags = list(body.tags)
    row.valid_from = body.valid_from
    row.valid_until = body.valid_until
    row.enabled = body.enabled
    row.updated_by = principal.user.id
    await db.commit()
    await db.refresh(row)
    await record_event(
        db,
        actor_user_id=principal.user.id,
        action="curated_entry.update",
        result="success",
        reason=body.reason,
        before=before,
        after=_curated_dict(row),
    )
    return _curated_dict(row)


@router.delete("/curated/{entry_id}")
async def delete_curated(
    entry_id: UUID,
    body: ReasonIn,
    principal: AdminPrincipal = Depends(require(AdminPermission.curated_write)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    row = await db.get(CampusCuratedEntry, entry_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Entry not found")
    before = _curated_dict(row)
    await db.delete(row)
    await db.commit()
    await record_event(
        db,
        actor_user_id=principal.user.id,
        action="curated_entry.delete",
        result="success",
        reason=body.reason,
        before=before,
    )
    return {"deleted": True}


@router.get("/grade-policy")
async def get_grade_policy(
    principal: AdminPrincipal = Depends(require(AdminPermission.runtime_read)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    # Seeded on first view so an admin sees METU's scale to edit rather than an
    # empty form, and never re-applied over a later correction.
    await ensure_policy_seeded(db)
    policy, revision = await load_grade_policy(db)
    row = await db.get(CampusGradePolicy, POLICY_ID)
    return {
        **policy_as_dict(policy),
        "notes": row.notes if row else None,
        "revision": revision,
        "updated_at": _iso(row.updated_at) if row else None,
        "editable": AdminPermission.runtime_write in principal.permissions,
    }


@router.put("/grade-policy")
async def put_grade_policy(
    body: GradePolicyIn,
    principal: AdminPrincipal = Depends(require(AdminPermission.runtime_write)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    before = policy_as_dict((await load_grade_policy(db))[0])
    row = await db.get(CampusGradePolicy, POLICY_ID)
    if row is None:
        row = CampusGradePolicy(id=POLICY_ID, revision=0)
        db.add(row)
    row.scale = dict(body.scale)
    row.non_graded = [value.strip().upper() for value in body.non_graded]
    row.passing_grades = [value.strip().upper() for value in body.passing_grades]
    row.weight_basis = body.weight_basis
    row.retake_replaces = body.retake_replaces
    row.max_credits_per_semester = body.max_credits_per_semester
    row.notes = body.notes
    row.revision = (row.revision or 0) + 1
    row.updated_by = principal.user.id
    await db.commit()
    await db.refresh(row)

    # Resident agents were constructed with the old scale, so they would keep
    # planning with it until they were evicted for idleness.
    from app.agents.pool import get_pool

    await get_pool().close_all()

    after = policy_as_dict(policy_from_row(row))
    await record_event(
        db,
        actor_user_id=principal.user.id,
        action="grade_policy.update",
        result="success",
        reason=body.reason,
        before=before,
        after=after,
    )
    return {**after, "revision": row.revision, "editable": True}
