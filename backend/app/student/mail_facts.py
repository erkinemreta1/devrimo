import hashlib
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import UserMailFact, UserProfile


async def store_extracted_mail_facts(
    db: AsyncSession,
    user_id: UUID,
    *,
    message_id: str,
    raw_body: str,
    sender_domain: str | None,
    facts: list[dict],
) -> int:
    """Persist structured facts after extraction and discard the raw body.

    The raw body is accepted only to derive a non-reversible correlation
    digest. It is never assigned to an ORM field, log, or return value.
    """
    profile = await db.get(UserProfile, user_id)
    if profile is None or not profile.mail_facts_enabled:
        return 0
    message_digest = hashlib.sha256(raw_body.encode()).hexdigest()
    stored = 0
    for index, fact in enumerate(facts):
        title = str(fact.get("title", "")).strip()
        summary = str(fact.get("summary", "")).strip()
        if not title or not summary:
            continue
        external_id = hashlib.sha256(f"{message_id}:{index}:{title}".encode()).hexdigest()
        row = (
            await db.execute(
                select(UserMailFact).where(
                    UserMailFact.user_id == user_id, UserMailFact.external_id == external_id
                )
            )
        ).scalar_one_or_none()
        if row is None:
            row = UserMailFact(
                user_id=user_id,
                external_id=external_id,
                fact_type=str(fact.get("fact_type", "announcement"))[:32],
                title=title,
                summary=summary,
                sender_domain=sender_domain,
                message_digest=message_digest,
            )
            db.add(row)
            stored += 1
        for field in ("starts_at", "ends_at", "valid_until"):
            value = fact.get(field)
            if isinstance(value, datetime):
                setattr(row, field, value if value.tzinfo else value.replace(tzinfo=UTC))
        row.extracted_at = datetime.now(UTC)
    if stored:
        await db.commit()
    return stored
