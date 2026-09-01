from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.jwt import AuthenticatedUser
from app.db.models import StudentContext, UserPreference, UserUpdateState
from app.db.session import get_db
from app.planning.groups import get_course_group
from app.planning.service import SemesterPlanRequest, plan_semester
from app.student import service
from app.student.updates import get_updates

router = APIRouter()


class ContextIn(BaseModel):
    department: str | None = Field(default=None, max_length=255)
    degree_level: Literal["undergraduate", "masters", "doctoral", "exchange", "other"] | None = None
    program_code: str | None = Field(default=None, max_length=32)
    campus: str | None = Field(default=None, max_length=255)
    confirm_verified: bool = False


class PreferenceIn(BaseModel):
    value: dict[str, Any]


class GroupRequestIn(BaseModel):
    term: str = Field(min_length=3, max_length=32)
    course_code: str = Field(min_length=2, max_length=32)
    section: str | None = Field(default=None, max_length=16)


def _context_out(context: StudentContext) -> dict:
    return {
        "department": context.department,
        "degree_level": context.degree_level,
        "program_code": context.program_code,
        "campus": context.campus,
        "source": context.source,
        "verified_at": context.verified_at,
        "confirmed_at": context.confirmed_at,
        "needs_confirmation": context.verified_at is not None and context.confirmed_at is None,
    }


@router.get("/context")
async def context_get(
    user: AuthenticatedUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> dict:
    return _context_out(await service.get_context(db, user.id))


@router.put("/context")
async def context_put(
    body: ContextIn,
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    context = await service.get_context(db, user.id)
    if body.confirm_verified:
        if context.verified_at is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "There is no verified SAIS context to confirm")
        context.confirmed_at = datetime.now(UTC)
    else:
        context.department = body.department
        context.degree_level = body.degree_level
        context.program_code = body.program_code
        context.campus = body.campus
        context.source = "manual"
        context.verified_at = None
        context.confirmed_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(context)
    return _context_out(context)


@router.get("/preferences")
async def preferences_get(
    user: AuthenticatedUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> dict:
    preferences = await service.list_preferences(db, user.id)
    return {
        "items": [
            {
                "key": item.key,
                "value": item.value,
                "provenance": item.provenance,
                "confidence": float(item.confidence),
                "updated_at": item.updated_at,
            }
            for item in preferences
        ],
        "allowed_keys": sorted(service.ALLOWED_PREFERENCE_KEYS),
    }


@router.put("/preferences/{key}")
async def preference_put(
    key: str,
    body: PreferenceIn,
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        item = await service.save_preference(
            db, user.id, key=key, value=body.value, provenance="explicit", confidence=1
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    return {"key": item.key, "value": item.value, "provenance": item.provenance, "confidence": 1}


@router.delete("/preferences/{key}", status_code=status.HTTP_204_NO_CONTENT)
async def preference_delete(
    key: str,
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await db.execute(delete(UserPreference).where(UserPreference.user_id == user.id, UserPreference.key == key))
    await db.commit()


@router.get("/updates")
async def updates_get(
    digest: bool = False,
    limit: int = Query(default=30, ge=1, le=100),
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await get_updates(db, user.id, digest=digest, limit=limit)


@router.put("/updates/{record_id}/state")
async def update_state(
    record_id: UUID,
    read: bool | None = None,
    dismissed: bool | None = None,
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    state = await db.get(UserUpdateState, (user.id, record_id))
    if state is None:
        state = UserUpdateState(user_id=user.id, record_id=record_id)
        db.add(state)
    now = datetime.now(UTC)
    if read is not None:
        state.read_at = now if read else None
    if dismissed is not None:
        state.dismissed_at = now if dismissed else None
    await db.commit()
    return {"record_id": str(record_id), "read": state.read_at is not None, "dismissed": state.dismissed_at is not None}


@router.post("/plan")
async def semester_plan(
    body: SemesterPlanRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await plan_semester(db, user.id, body)


@router.post("/course-group")
async def course_group(
    body: GroupRequestIn,
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await get_course_group(
        db, user.id, term=body.term, course_code=body.course_code, section=body.section
    )
