from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import StudentContext, UserPreference

ALLOWED_PREFERENCE_KEYS = {
    "interests",
    "event_categories",
    "device_platform",
    "accessibility_display",
    "digest_preferences",
}
SENSITIVE_TERMS = {
    "health",
    "medical",
    "disability",
    "religion",
    "political",
    "ethnicity",
    "sexual",
    "disciplinary",
    "password",
    "grade",
    "transcript",
}


def validate_preference(key: str, value: dict) -> None:
    if key not in ALLOWED_PREFERENCE_KEYS:
        raise ValueError("Preference key is not in the benign preference allowlist")
    serialized = str(value).lower()
    if any(term in serialized for term in SENSITIVE_TERMS):
        raise ValueError("Sensitive traits and academic records cannot be stored as preferences")
    if len(serialized) > 4000:
        raise ValueError("Preference value is too large")


async def get_context(db: AsyncSession, user_id: UUID) -> StudentContext:
    context = await db.get(StudentContext, user_id)
    if context is None:
        context = StudentContext(user_id=user_id)
        db.add(context)
        await db.commit()
        await db.refresh(context)
    return context


async def apply_verified_context(
    db: AsyncSession,
    user_id: UUID,
    *,
    department: str | None,
    degree_level: str | None,
    program_code: str | None,
    campus: str | None,
    source: str = "sais",
) -> StudentContext:
    context = await get_context(db, user_id)
    context.department = department
    context.degree_level = degree_level
    context.program_code = program_code
    context.campus = campus
    context.source = source
    context.verified_at = datetime.now(UTC)
    context.confirmed_at = None
    await db.commit()
    await db.refresh(context)
    return context


async def save_preference(
    db: AsyncSession,
    user_id: UUID,
    *,
    key: str,
    value: dict,
    provenance: str,
    confidence: float,
) -> UserPreference:
    validate_preference(key, value)
    preference = (
        await db.execute(select(UserPreference).where(UserPreference.user_id == user_id, UserPreference.key == key))
    ).scalar_one_or_none()
    if preference is None:
        preference = UserPreference(user_id=user_id, key=key, value=value, provenance=provenance)
        db.add(preference)
    preference.value = value
    preference.provenance = provenance
    preference.confidence = max(0, min(confidence, 1))
    await db.commit()
    await db.refresh(preference)
    return preference


async def list_preferences(db: AsyncSession, user_id: UUID) -> list[UserPreference]:
    return (
        await db.execute(
            select(UserPreference).where(UserPreference.user_id == user_id).order_by(UserPreference.updated_at.desc())
        )
    ).scalars().all()
