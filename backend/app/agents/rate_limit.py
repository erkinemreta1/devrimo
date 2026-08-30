"""Persistent, per-student model-token budgets and per-turn usage capture."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import UserTokenUsage


def current_hour(now: datetime | None = None) -> datetime:
    value = now or datetime.now(UTC)
    return value.astimezone(UTC).replace(minute=0, second=0, microsecond=0)


@dataclass
class TurnUsage:
    input_characters: int = 0
    output_characters: int = 0
    reported_tokens: int = 0

    def observe_event(self, event) -> None:
        metrics = getattr(event, "metrics", None)
        total_tokens = int(getattr(metrics, "total_tokens", 0) or 0) if metrics is not None else 0
        # Run-level metrics are cumulative, so keep the largest observation.
        self.reported_tokens = max(self.reported_tokens, total_tokens)

    def observe_content(self, content: str) -> None:
        self.output_characters += len(content)

    @property
    def billable_tokens(self) -> int:
        if self.reported_tokens > 0:
            return self.reported_tokens
        # Providers do not guarantee usage on failed/cancelled streams. Charge
        # a conservative fallback so repeatedly aborting requests cannot evade
        # the budget. This value is never shown as provider-reported usage.
        return max(1, (self.input_characters + self.output_characters + 3) // 4)


async def get_current_usage(db: AsyncSession, user_id: UUID) -> UserTokenUsage | None:
    bucket = current_hour()
    result = await db.execute(
        select(UserTokenUsage).where(
            UserTokenUsage.user_id == user_id,
            UserTokenUsage.bucket_start == bucket,
        )
    )
    return result.scalar_one_or_none()


async def enforce_token_budget(db: AsyncSession, user_id: UUID) -> None:
    limit = get_settings().user_token_limit_per_hour
    if limit <= 0:
        return
    usage = await get_current_usage(db, user_id)
    if usage is None or usage.total_tokens < limit:
        return

    now = datetime.now(UTC)
    retry_after = max(1, int(((current_hour(now) + timedelta(hours=1)) - now).total_seconds()))
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Hourly AI token limit reached. Try again after the next hour.",
        headers={"Retry-After": str(retry_after)},
    )


async def record_token_usage(db: AsyncSession, user_id: UUID, tokens: int) -> None:
    bucket = current_hour()
    usage = await get_current_usage(db, user_id)
    if usage is None:
        usage = UserTokenUsage(
            user_id=user_id,
            bucket_start=bucket,
            total_tokens=0,
            request_count=0,
        )
        db.add(usage)
    usage.total_tokens += max(0, tokens)
    usage.request_count += 1
    await db.commit()
