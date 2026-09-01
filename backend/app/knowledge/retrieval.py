import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import and_, func, literal_column, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CampusKnowledgeRecord, CampusSource
from app.knowledge.embeddings import embed_query


@dataclass(slots=True)
class SearchFilters:
    record_types: tuple[str, ...] = ()
    language: str | None = None
    campus: str | None = None
    department: str | None = None
    degree_level: str | None = None
    starts_after: datetime | None = None
    starts_before: datetime | None = None
    include_expired: bool = False


def _tokens(text: str) -> set[str]:
    return {token for token in re.findall(r"[\wçğıöşüÇĞİÖŞÜ-]+", text.lower()) if len(token) > 1}


def _cosine(left: list[float] | None, right: list[float] | None) -> float:
    if not left or not right:
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=False))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    return dot / (left_norm * right_norm) if left_norm and right_norm else 0.0


def _serialize(record: CampusKnowledgeRecord, source: CampusSource, score: float) -> dict:
    return {
        "id": str(record.id),
        "type": record.record_type,
        "title": record.title,
        "summary": record.summary,
        "content": record.content,
        "url": record.url,
        "language": record.language,
        "starts_at": record.starts_at.isoformat() if record.starts_at else None,
        "ends_at": record.ends_at.isoformat() if record.ends_at else None,
        "published_at": record.published_at.isoformat() if record.published_at else None,
        "audience": record.audience,
        "source": source.name,
        "source_id": str(source.id),
        "retrieved_at": datetime.now(UTC).isoformat(),
        "source_last_success_at": source.last_success_at.isoformat() if source.last_success_at else None,
        "score": round(score, 6),
    }


async def search_knowledge(
    db: AsyncSession, query: str, filters: SearchFilters | None = None, *, limit: int = 10
) -> list[dict]:
    filters = filters or SearchFilters()
    now = datetime.now(UTC)
    conditions = [CampusKnowledgeRecord.is_current.is_(True), CampusSource.status == "published"]
    if filters.record_types:
        conditions.append(CampusKnowledgeRecord.record_type.in_(filters.record_types))
    if filters.language:
        conditions.append(CampusKnowledgeRecord.language == filters.language)
    if filters.campus:
        conditions.append(or_(CampusKnowledgeRecord.campus.is_(None), CampusKnowledgeRecord.campus == filters.campus))
    if filters.department:
        conditions.append(
            or_(CampusKnowledgeRecord.department.is_(None), CampusKnowledgeRecord.department == filters.department)
        )
    if filters.degree_level:
        conditions.append(
            or_(
                CampusKnowledgeRecord.degree_level.is_(None),
                CampusKnowledgeRecord.degree_level == filters.degree_level,
            )
        )
    if filters.starts_after:
        conditions.append(
            or_(CampusKnowledgeRecord.starts_at.is_(None), CampusKnowledgeRecord.starts_at >= filters.starts_after)
        )
    if filters.starts_before:
        conditions.append(
            or_(CampusKnowledgeRecord.starts_at.is_(None), CampusKnowledgeRecord.starts_at <= filters.starts_before)
        )
    if not filters.include_expired:
        conditions.append(or_(CampusKnowledgeRecord.valid_until.is_(None), CampusKnowledgeRecord.valid_until >= now))

    query_embedding = await embed_query(query) if query.strip() else None
    base = select(CampusKnowledgeRecord, CampusSource).join(
        CampusSource, CampusSource.id == CampusKnowledgeRecord.source_id
    )
    postgres = db.get_bind().dialect.name == "postgresql"
    if postgres and query.strip():
        tsquery = func.websearch_to_tsquery("simple", query)
        fts_rank = func.ts_rank_cd(literal_column("search_vector"), tsquery)
        if query_embedding is not None:
            semantic = 1 - CampusKnowledgeRecord.embedding.cosine_distance(query_embedding)
            score = fts_rank * 0.55 + func.coalesce(semantic, 0) * 0.30 + CampusKnowledgeRecord.authority / 1000
            match = or_(literal_column("search_vector").op("@@")(tsquery), CampusKnowledgeRecord.embedding.is_not(None))
        else:
            score = fts_rank * 0.85 + CampusKnowledgeRecord.authority / 1000
            match = literal_column("search_vector").op("@@")(tsquery)
        statement = base.add_columns(score.label("rank")).where(*conditions, match).order_by(score.desc()).limit(limit)
        rows = (await db.execute(statement)).all()
        return [_serialize(record, source, float(rank or 0)) for record, source, rank in rows]

    candidate_statement = (
        base.where(and_(*conditions)).order_by(CampusKnowledgeRecord.published_at.desc()).limit(250)
    )
    candidates = (await db.execute(candidate_statement)).all()
    query_tokens = _tokens(query)
    ranked: list[tuple[float, CampusKnowledgeRecord, CampusSource]] = []
    for record, source in candidates:
        haystack = _tokens(f"{record.title} {record.summary or ''} {record.content}")
        keyword = len(query_tokens & haystack) / max(len(query_tokens), 1) if query_tokens else 0.5
        semantic = _cosine(query_embedding, record.embedding) if query_embedding is not None else 0
        freshness = 0.05 if record.published_at and (now - record.published_at).days <= 14 else 0
        score = keyword * 0.55 + semantic * 0.30 + record.authority / 1000 + freshness
        if not query_tokens or keyword or semantic > 0.25:
            ranked.append((score, record, source))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return [_serialize(record, source, score) for score, record, source in ranked[:limit]]


async def read_campus_page(db: AsyncSession, url: str) -> dict | None:
    row = (
        await db.execute(
            select(CampusKnowledgeRecord, CampusSource)
            .join(CampusSource, CampusSource.id == CampusKnowledgeRecord.source_id)
            .where(CampusKnowledgeRecord.url == url, CampusKnowledgeRecord.is_current.is_(True))
            .order_by(CampusKnowledgeRecord.last_seen_at.desc())
            .limit(1)
        )
    ).one_or_none()
    return _serialize(row[0], row[1], 1.0) if row else None
