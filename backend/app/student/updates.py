from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import StudentContext, UserMailFact, UserPreference, UserUpdateState
from app.knowledge.retrieval import SearchFilters, search_knowledge


def _interest_query(preferences: list[UserPreference]) -> str:
    terms: list[str] = []
    for preference in preferences:
        if preference.key not in {"interests", "event_categories"}:
            continue
        value = preference.value
        items = value.get("items", []) if isinstance(value, dict) else []
        terms.extend(str(item) for item in items if str(item).strip())
    return " OR ".join(dict.fromkeys(terms[:20]))


async def get_updates(db: AsyncSession, user_id: UUID, *, digest: bool = False, limit: int = 30) -> dict:
    now = datetime.now(UTC)
    context = await db.get(StudentContext, user_id)
    preferences = (
        await db.execute(select(UserPreference).where(UserPreference.user_id == user_id))
    ).scalars().all()
    query = _interest_query(preferences)
    public = await search_knowledge(
        db,
        query,
        SearchFilters(
            record_types=("event", "announcement", "calendar", "service_status"),
            campus=context.campus if context else None,
            department=context.department if context else None,
            degree_level=context.degree_level if context else None,
            starts_after=now - timedelta(days=7),
            starts_before=now + timedelta(days=90),
        ),
        limit=max(limit * 2, 20),
    )
    states = {
        str(state.record_id): state
        for state in (
            await db.execute(select(UserUpdateState).where(UserUpdateState.user_id == user_id))
        ).scalars()
    }
    items = []
    for item in public:
        state = states.get(item["id"])
        if state and state.dismissed_at:
            continue
        items.append({**item, "origin": "campus", "read": bool(state and state.read_at)})
    mail_rows = (
        await db.execute(
            select(UserMailFact)
            .where(
                UserMailFact.user_id == user_id,
                or_(UserMailFact.valid_until.is_(None), UserMailFact.valid_until >= now),
            )
            .order_by(UserMailFact.extracted_at.desc())
            .limit(limit)
        )
    ).scalars()
    for fact in mail_rows:
        items.append(
            {
                "id": f"mail:{fact.id}",
                "type": fact.fact_type,
                "title": fact.title,
                "summary": fact.summary,
                "content": fact.summary,
                "url": None,
                "starts_at": fact.starts_at.isoformat() if fact.starts_at else None,
                "ends_at": fact.ends_at.isoformat() if fact.ends_at else None,
                "source": f"Email · {fact.sender_domain or 'METU'}",
                "retrieved_at": fact.extracted_at.isoformat(),
                "origin": "mail_fact",
                "read": False,
            }
        )
    items.sort(key=lambda item: item.get("starts_at") or item.get("published_at") or item["retrieved_at"], reverse=True)
    size = min(limit, 5) if digest else limit
    return {
        "mode": "digest" if digest else "feed",
        "items": items[:size],
        "personalized_by": {
            "department": context.department if context else None,
            "degree_level": context.degree_level if context else None,
            "campus": context.campus if context else None,
            "interests": query.split(" OR ") if query else [],
        },
        "generated_at": now.isoformat(),
    }
