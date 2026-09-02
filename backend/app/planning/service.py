from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.directory import METU_ID
from app.db.models import CourseOffering, CourseRule, PlanningPolicy, StudentAcademicSnapshot

GRADE_POINTS = {
    "AA": 4.0,
    "BA": 3.5,
    "BB": 3.0,
    "CB": 2.5,
    "CC": 2.0,
    "DC": 1.5,
    "DD": 1.0,
    "FD": 0.5,
    "FF": 0.0,
}


class SemesterPlanRequest(BaseModel):
    term: str = Field(min_length=3, max_length=32)
    required_courses: list[str] = Field(default_factory=list)
    preferred_courses: list[str] = Field(default_factory=list)
    excluded_courses: list[str] = Field(default_factory=list)
    retake_courses: list[str] = Field(default_factory=list)
    min_credits: float | None = Field(default=None, ge=0, le=60)
    max_credits: float | None = Field(default=None, ge=0, le=60)
    days_off: list[str] = Field(default_factory=list)
    earliest_start: str | None = None
    latest_end: str | None = None


def _code(value: str) -> str:
    return "".join(value.upper().split())


def _grade_at_least(actual: str, required: str) -> bool:
    return GRADE_POINTS.get(actual.upper(), -1) >= GRADE_POINTS.get(required.upper(), 99)


def _prerequisite_met(rule: Any, completed: dict[str, str], cgpa: float) -> tuple[bool, str | None]:
    if not rule:
        return True, None
    if isinstance(rule, list):
        rule = {"all": rule}
    if not isinstance(rule, dict):
        return False, "invalid prerequisite rule"
    if "course" in rule:
        code = _code(str(rule["course"]))
        grade = completed.get(code)
        required = str(rule.get("min_grade", "DD"))
        return (grade is not None and _grade_at_least(grade, required), f"requires {code} with {required} or better")
    if "min_cgpa" in rule:
        try:
            required = float(rule["min_cgpa"])
        except (TypeError, ValueError):
            return False, "invalid prerequisite rule"
        return (cgpa >= required, f"requires CGPA {required:.2f}")
    if "all" in rule:
        if not isinstance(rule["all"], list):
            return False, "invalid prerequisite rule"
        failures = []
        for child in rule["all"]:
            met, reason = _prerequisite_met(child, completed, cgpa)
            if not met:
                failures.append(reason or "unmet prerequisite")
        return (not failures, "; ".join(failures) if failures else None)
    if "any" in rule:
        if not isinstance(rule["any"], list):
            return False, "invalid prerequisite rule"
        reasons = []
        for child in rule["any"]:
            met, reason = _prerequisite_met(child, completed, cgpa)
            if met:
                return True, None
            reasons.append(reason or "unmet prerequisite")
        return False, "one of: " + ", ".join(reasons)
    return False, "invalid or unsupported prerequisite rule"


def _minutes(value: str | None, fallback: int) -> int:
    if not value:
        return fallback
    try:
        hour, minute = value.split(":", 1)
        return int(hour) * 60 + int(minute)
    except (ValueError, AttributeError):
        return fallback


def _meetings(offering: CourseOffering) -> list[tuple[str, int, int]]:
    result = []
    for meeting in offering.schedule or []:
        if not isinstance(meeting, dict) or not meeting.get("day"):
            continue
        result.append(
            (
                str(meeting["day"]).lower(),
                _minutes(str(meeting.get("start", "")), 0),
                _minutes(str(meeting.get("end", "")), 24 * 60),
            )
        )
    return result


def _fits_user_constraints(offering: CourseOffering, request: SemesterPlanRequest) -> tuple[bool, str | None]:
    days_off = {day.lower() for day in request.days_off}
    earliest = _minutes(request.earliest_start, 0)
    latest = _minutes(request.latest_end, 24 * 60)
    for day, start, end in _meetings(offering):
        if day in days_off:
            return False, f"meets on requested day off ({day})"
        if start < earliest:
            return False, f"starts before {request.earliest_start}"
        if end > latest:
            return False, f"ends after {request.latest_end}"
    return True, None


def _conflicts(offering: CourseOffering, selected: list[CourseOffering]) -> bool:
    for day, start, end in _meetings(offering):
        for other in selected:
            for other_day, other_start, other_end in _meetings(other):
                if day == other_day and start < other_end and other_start < end:
                    return True
    return False


def _best_combination(
    groups: list[tuple[str, list[CourseOffering]]],
    required: set[str],
    preferred: set[str],
    max_credits: float,
) -> list[CourseOffering]:
    best: list[CourseOffering] = []
    best_score = (-1, -1.0, -1, 0)
    visited = 0

    def visit(index: int, selected: list[CourseOffering], credits: float) -> None:
        nonlocal best, best_score, visited
        visited += 1
        if visited > 150_000:
            return
        if index == len(groups):
            codes = {_code(item.course_code) for item in selected}
            days = {day for item in selected for day, _, _ in _meetings(item)}
            score = (len(codes & required), credits, len(codes & preferred), -len(days))
            if score > best_score:
                best_score = score
                best = list(selected)
            return
        code, sections = groups[index]
        if code not in required:
            visit(index + 1, selected, credits)
        for offering in sections:
            next_credits = credits + float(offering.credits)
            if next_credits <= max_credits and not _conflicts(offering, selected):
                selected.append(offering)
                visit(index + 1, selected, next_credits)
                selected.pop()

    visit(0, [], 0)
    return best


async def plan_semester(db: AsyncSession, user_id: UUID, request: SemesterPlanRequest) -> dict:
    snapshot = await db.get(StudentAcademicSnapshot, (user_id, request.term))
    if snapshot is None:
        return {
            "status": "needs_academic_snapshot",
            "detail": "Refresh the student's SAIS transcript and current registration before planning.",
            "term": request.term,
        }
    offerings = (
        await db.execute(select(CourseOffering).where(CourseOffering.term == request.term))
    ).scalars().all()
    rules = {rule.course_code: rule for rule in (await db.execute(select(CourseRule))).scalars()}
    policy = (
        await db.execute(
            select(PlanningPolicy)
            .where(PlanningPolicy.organization_id == METU_ID, PlanningPolicy.active.is_(True))
            .order_by(PlanningPolicy.revision.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    policy_rules = policy.rules if policy else {}
    max_credits = min(float(request.max_credits or policy_rules.get("max_credits", 20)), 60)
    min_credits = float(request.min_credits or policy_rules.get("min_credits", 0))
    current_credits = float(snapshot.current_credits)
    current_points = float(snapshot.current_grade_points)
    cgpa = current_points / current_credits if current_credits else 0.0
    completed = {
        _code(str(item.get("course_code", ""))): str(item.get("grade", ""))
        for item in snapshot.completed_courses
        if isinstance(item, dict) and item.get("course_code") and item.get("grade")
    }
    required = {_code(item) for item in request.required_courses}
    preferred = {_code(item) for item in request.preferred_courses}
    excluded = {_code(item) for item in request.excluded_courses}
    retakes = {_code(item) for item in request.retake_courses}
    eligible: dict[str, list[CourseOffering]] = defaultdict(list)
    exclusions: list[dict] = []
    for offering in offerings:
        code = _code(offering.course_code)
        reason = None
        if code in excluded:
            reason = "excluded by the student"
        elif code in completed and code not in retakes:
            reason = "already completed"
        else:
            rule = rules.get(code)
            if rule is None:
                reason = "prerequisite data unavailable"
                met, prerequisite_reason = False, reason
            else:
                met, prerequisite_reason = _prerequisite_met(rule.prerequisites, completed, cgpa)
            if not met:
                reason = prerequisite_reason
            else:
                fits, constraint_reason = _fits_user_constraints(offering, request)
                if not fits:
                    reason = constraint_reason
        if reason:
            exclusions.append({"course_code": code, "section": offering.section, "reason": reason})
        else:
            eligible[code].append(offering)
    groups = sorted(
        eligible.items(),
        key=lambda item: (item[0] not in required, item[0] not in preferred, item[0]),
    )
    selected = _best_combination(groups, required, preferred, max_credits)
    selected_codes = {_code(item.course_code) for item in selected}
    missing_required = sorted(required - selected_codes)
    selected_credits = sum(float(item.credits) for item in selected)
    projected = (
        (current_points + selected_credits * 4.0) / (current_credits + selected_credits)
        if current_credits + selected_credits
        else 4.0
    )
    status = "ok"
    if missing_required or selected_credits < min_credits:
        status = "constraints_unsatisfied"
    return {
        "status": status,
        "term": request.term,
        "maximum_semester_gpa": 4.0 if selected else None,
        "projected_cumulative_gpa": round(projected, 3),
        "current_cumulative_gpa": round(cgpa, 3),
        "selected_credits": round(selected_credits, 2),
        "courses": [
            {
                "course_code": _code(item.course_code),
                "section": item.section,
                "title": item.title,
                "credits": float(item.credits),
                "schedule": item.schedule,
                "source_url": item.source_url,
            }
            for item in selected
        ],
        "missing_required_courses": missing_required,
        "excluded_options": exclusions,
        "assumptions": [
            "Every selected course receives AA (4.00).",
            "Offerings, prerequisites, and the academic snapshot are treated as fresh only at their timestamps.",
            "Only one section of each course is selected and overlapping meetings are rejected.",
        ],
        "freshness": {
            "academic_snapshot": snapshot.fetched_at.isoformat(),
            "offerings": max((item.fetched_at for item in offerings), default=None).isoformat() if offerings else None,
            "policy_revision": policy.revision if policy else None,
            "calculated_at": datetime.now(UTC).isoformat(),
        },
    }


async def upsert_academic_snapshot(
    db: AsyncSession,
    user_id: UUID,
    term: str,
    *,
    completed_courses: list[dict],
    enrolled_courses: list[dict],
    current_credits: Decimal | float,
    current_grade_points: Decimal | float,
    source: str = "sais",
) -> StudentAcademicSnapshot:
    snapshot = await db.get(StudentAcademicSnapshot, (user_id, term))
    if snapshot is None:
        snapshot = StudentAcademicSnapshot(user_id=user_id, term=term)
        db.add(snapshot)
    snapshot.completed_courses = completed_courses
    snapshot.enrolled_courses = enrolled_courses
    snapshot.current_credits = current_credits
    snapshot.current_grade_points = current_grade_points
    snapshot.source = source
    snapshot.fetched_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(snapshot)
    return snapshot
