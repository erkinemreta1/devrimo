from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.directory import active_account
from app.core.crypto import decrypt_secret
from app.db.models import (
    CourseGroupAccessAudit,
    CourseGroupLink,
    StudentAcademicSnapshot,
    StudentContext,
)


def _code(value: str) -> str:
    return "".join(value.upper().split())


async def get_course_group(
    db: AsyncSession, user_id: UUID, *, term: str, course_code: str, section: str | None = None
) -> dict:
    now = datetime.now(UTC)
    account = await active_account(db, user_id)
    if account is None:
        return {"status": "not_found", "detail": "No active group has been curated for this course."}
    statement = select(CourseGroupLink).where(
        CourseGroupLink.organization_id == account.organization_id,
        CourseGroupLink.course_code == _code(course_code),
        CourseGroupLink.active.is_(True),
        or_(CourseGroupLink.valid_until.is_(None), CourseGroupLink.valid_until >= now),
    )
    if section:
        statement = statement.where(or_(CourseGroupLink.section == "", CourseGroupLink.section == section))
    links = (await db.execute(statement.order_by(CourseGroupLink.section.desc()))).scalars().all()
    if not links:
        return {"status": "not_found", "detail": "No active group has been curated for this course."}
    snapshot = await db.get(StudentAcademicSnapshot, (user_id, term))
    context = await db.get(StudentContext, user_id)
    enrolled = snapshot.enrolled_courses if snapshot else []
    for link in links:
        match = next(
            (
                item
                for item in enrolled
                if isinstance(item, dict)
                and _code(str(item.get("course_code", ""))) == link.course_code
                and (not link.section or str(item.get("section", "")) == link.section)
            ),
            None,
        )
        reason = None
        if snapshot is None:
            reason = "academic_snapshot_missing"
        elif match is None:
            reason = "not_enrolled"
        elif link.eligibility.get("department") and (
            context is None or context.department != link.eligibility["department"]
        ):
            reason = "department_mismatch"
        elif link.eligibility.get("degree_level") and (
            context is None or context.degree_level != link.eligibility["degree_level"]
        ):
            reason = "degree_level_mismatch"
        if reason:
            db.add(CourseGroupAccessAudit(user_id=user_id, group_id=link.id, result="denied", reason_code=reason))
            await db.commit()
            continue
        db.add(CourseGroupAccessAudit(user_id=user_id, group_id=link.id, result="granted"))
        await db.commit()
        return {
            "status": "ok",
            "course_code": link.course_code,
            "section": link.section or None,
            "term": term,
            "invite_url": decrypt_secret(link.invite_url_enc),
            "verified_against_snapshot_at": snapshot.fetched_at.isoformat(),
        }
    return {"status": "not_eligible", "detail": "Current enrollment does not satisfy the curated group's rules."}
