"""Admin-entered campus knowledge, read from the database instead of the web.

Course WhatsApp groups are the case that forces this to exist: they are real,
students ask for them constantly, and there is no page anywhere that lists them.
Club registrations and hand-entered events are the same shape.

Making it an *adapter* rather than a second retrieval path is the point. A
curated entry becomes a document with the same metadata as a crawled
announcement, so the agent has one way to answer a campus question and the
retrieval filters (department, degree level, language) apply to both without
anything special being written for either.
"""

from datetime import UTC, datetime

from sqlalchemy import select

from app.campus.sources.adapters import AdapterContext
from app.campus.sources.models import SourceError, SourceItem
from app.db.models import CampusCuratedEntry


def _within_window(entry: CampusCuratedEntry, now: datetime) -> bool:
    """Whether an entry is live right now.

    A WhatsApp invite that expired last term is worse than no answer at all —
    the student follows it, it fails, and the agent looks like it made the link
    up. Expiry is enforced here rather than left to retrieval so that a stale
    entry stops being embedded, not just stops being ranked.
    """
    if entry.valid_from is not None and _aware(entry.valid_from) > now:
        return False
    if entry.valid_until is not None and _aware(entry.valid_until) < now:
        return False
    return True


def _aware(value: datetime) -> datetime:
    # SQLite gives naive datetimes back even for timezone-aware columns.
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def to_item(entry: CampusCuratedEntry) -> SourceItem:
    body_parts = [entry.title, entry.body]
    if entry.url:
        body_parts.append(entry.url)
    return SourceItem(
        external_id=f"curated:{entry.id}",
        title=entry.title[:500],
        body="\n".join(part for part in body_parts if part),
        url=entry.url,
        language=entry.language,
        published_at=_aware(entry.updated_at) if entry.updated_at else None,
        extra={
            "curated_kind": entry.kind,
            "entry_key": entry.entry_key,
            "tags": list(entry.tags or []),
            "departments": list(entry.departments or []),
            "degree_levels": list(entry.degree_levels or []),
            "valid_until": _aware(entry.valid_until).isoformat() if entry.valid_until else None,
        },
    )


async def collect(context: AdapterContext) -> list[SourceItem]:
    if context.db is None:
        raise SourceError("no_session", "The curated adapter needs a database session")

    kinds = context.spec.config.get("kinds") or []
    statement = select(CampusCuratedEntry).where(CampusCuratedEntry.enabled.is_(True))
    if kinds:
        statement = statement.where(CampusCuratedEntry.kind.in_(kinds))
    rows = (await context.db.execute(statement)).scalars().all()

    now = datetime.now(UTC)
    return [to_item(entry) for entry in rows if _within_window(entry, now)][: context.spec.max_items]
