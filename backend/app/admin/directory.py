from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AccountDirectory, AccountStatus, Organization

METU_ID = UUID("00000000-0000-0000-0000-000000000001")


async def ensure_metu(db: AsyncSession) -> Organization:
    organization = await db.get(Organization, METU_ID)
    if organization is None:
        organization = Organization(id=METU_ID, slug="metu", name="Middle East Technical University")
        db.add(organization)
        await db.flush()
    return organization


async def touch_account(db: AsyncSession, user_id: UUID, email: str | None) -> AccountDirectory:
    await ensure_metu(db)
    account = await db.get(AccountDirectory, user_id)
    if account is None:
        account = AccountDirectory(
            user_id=user_id,
            organization_id=METU_ID,
            email=email,
            email_normalized=email.strip().lower() if email else None,
            status=AccountStatus.active,
        )
        db.add(account)
    elif account.status != AccountStatus.deleted:
        if email:
            account.email = email
            account.email_normalized = email.strip().lower()
    account.last_seen_at = datetime.now(UTC)
    await db.commit()
    if account.status != AccountStatus.active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account is not active")
    return account


async def active_account(db: AsyncSession, user_id: UUID) -> AccountDirectory | None:
    return (
        await db.execute(
            select(AccountDirectory).where(
                AccountDirectory.user_id == user_id,
                AccountDirectory.status == AccountStatus.active,
            )
        )
    ).scalar_one_or_none()
