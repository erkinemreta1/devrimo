"""Per-user preferences and onboarding progress.

The profile row is created on first read rather than at signup: identity
lives in Supabase, so there is no server-side signup hook to hang creation
off, and a lazily created row keeps the "user exists in Supabase but not
here" state from being an error anyone has to handle.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.jwt import AuthenticatedUser
from app.campus import service as campus_service
from app.db.session import get_db
from app.schemas import ProfileIn, ProfileOut

router = APIRouter()


@router.get("", response_model=ProfileOut)
async def get_profile(
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProfileOut:
    profile = await campus_service.get_or_create_profile(db, user.id)
    return ProfileOut.from_model(profile)


@router.patch("", response_model=ProfileOut)
async def patch_profile(
    body: ProfileIn,
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProfileOut:
    profile = await campus_service.get_or_create_profile(db, user.id)

    # Only fields the client actually sent are touched, so a PATCH carrying
    # one step's answers can't blank out an earlier step's.
    changes = body.model_dump(exclude_unset=True)
    if "display_name" in changes:
        profile.display_name = changes["display_name"]
    if "department" in changes:
        profile.department = changes["department"]
    if "degree_level" in changes:
        profile.degree_level = changes["degree_level"]
    if changes.get("locale"):
        profile.locale = changes["locale"]
    if "onboarding_step" in changes:
        profile.onboarding_step = changes["onboarding_step"]
    if "onboarding_completed" in changes and changes["onboarding_completed"] is not None:
        # Re-completing keeps the original timestamp; that's the date the
        # student first finished, and nothing benefits from moving it.
        if changes["onboarding_completed"]:
            profile.onboarding_completed_at = profile.onboarding_completed_at or datetime.now(UTC)
        else:
            profile.onboarding_completed_at = None

    await db.commit()
    await db.refresh(profile)
    return ProfileOut.from_model(profile)
