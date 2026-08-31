from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AdminAuditEvent


async def record_event(
    db: AsyncSession,
    *,
    actor_user_id: UUID,
    action: str,
    result: str,
    target_user_id: UUID | None = None,
    organization_id: UUID | None = None,
    reason: str | None = None,
    before: dict | None = None,
    after: dict | None = None,
) -> AdminAuditEvent:
    """Record allowlisted state only; callers must never pass secrets or content."""
    event = AdminAuditEvent(
        actor_user_id=actor_user_id,
        target_user_id=target_user_id,
        organization_id=organization_id,
        action=action[:100],
        result=result[:32],
        reason=reason[:1000] if reason else None,
        before_state=before,
        after_state=after,
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return event
