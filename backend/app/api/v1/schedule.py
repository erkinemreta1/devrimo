"""Token-free course catalog access for the visual schedule builder.

These endpoints call the already connected Course Info MCP function directly.
No Agent run, language model, prompt, memory, or learning pass is involved.
"""

import asyncio
import inspect
import json
import re
import time
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import manager
from app.auth.dependencies import get_current_user
from app.auth.jwt import AuthenticatedUser
from app.db.models import StudentAcademicSnapshot, StudentContext
from app.db.session import get_db
from app.logging import get_logger
from app.planning.mcp_bridge import sync_student_context_from_sais

router = APIRouter()
logger = get_logger(__name__)
_CACHE_TTL_SECONDS = 15 * 60
_cache: dict[tuple[str, ...], tuple[float, Any]] = {}
_locks: dict[str, asyncio.Lock] = {}


class AiScheduleCourse(BaseModel):
    code: str = Field(min_length=3, max_length=20)
    name: str = Field(default="", max_length=255)


class AiScheduleRequest(BaseModel):
    department: str = Field(min_length=3, max_length=20)
    semester: str = Field(min_length=4, max_length=20)
    courses: list[AiScheduleCourse] = Field(default_factory=list, max_length=20)


def _json_value(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    if isinstance(value, str):
        try:
            return _json_value(json.loads(value))
        except json.JSONDecodeError:
            return value
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        # Agno wraps MCP results in a content block whose text contains the
        # tool's actual JSON payload.  Unwrap a single textual result so every
        # schedule endpoint exposes the same plain data shape.
        content = value.get("content")
        if isinstance(content, dict):
            return _json_value(content)
        if isinstance(content, str):
            try:
                return _json_value(json.loads(content))
            except json.JSONDecodeError:
                pass
        if isinstance(content, list):
            texts = [item.get("text") for item in content if isinstance(item, dict) and isinstance(item.get("text"), str)]
            if len(texts) == 1:
                return _json_value(texts[0])
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)


def _cached(key: tuple[str, ...]) -> Any | None:
    item = _cache.get(key)
    if item is None or time.monotonic() - item[0] > _CACHE_TTL_SECONDS:
        _cache.pop(key, None)
        return None
    return item[1]


def _tool_arguments(function, values: dict[str, str]) -> dict[str, str]:
    properties = (function.parameters or {}).get("properties", {})
    aliases = {
        "department": ("department", "department_code", "dept", "dept_code", "program", "program_code"),
        "semester": ("semester", "semester_code", "term", "term_code"),
        "course": ("course", "course_code", "code"),
        "query": ("query", "keyword", "search", "name"),
        "category": ("category", "category_id", "category_code", "code", "id", "name"),
    }
    arguments: dict[str, str] = {}
    for value_name, value in values.items():
        for candidate in aliases[value_name]:
            if candidate in properties:
                arguments[candidate] = value
                break
    required = set((function.parameters or {}).get("required", []))
    missing = required - arguments.keys()
    if missing:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            f"Course Info tool schema is unsupported; missing arguments: {', '.join(sorted(missing))}",
        )
    return arguments


async def _call_course_info(
    db: AsyncSession,
    user: AuthenticatedUser,
    tool_suffix: str,
    values: dict[str, str],
) -> Any:
    # Some curriculum tools are student-specific, so cache entries must never
    # be shared between accounts.
    cache_key = (str(user.id), tool_suffix, *(f"{key}={value}" for key, value in sorted(values.items())))
    cached = _cached(cache_key)
    if cached is not None:
        return cached

    lock = _locks.setdefault(str(user.id), asyncio.Lock())
    async with lock:
        cached = _cached(cache_key)
        if cached is not None:
            return cached

        agent = await manager.get_agent_or_404(db, user.id)
        resident = await manager.resident_for(db, agent)
        toolkit = next((item for item in resident.toolkits if item.name == "campus:course_info"), None)
        if toolkit is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Course catalog access is not enabled")

        function_name = f"course_info_{tool_suffix}"
        function = (toolkit.functions or {}).get(function_name)
        if function is None or function.entrypoint is None:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Course Info tool is unavailable: {tool_suffix}")

        arguments = _tool_arguments(function, values)
        try:
            result = function.entrypoint(**arguments)
            if inspect.isawaitable(result):
                result = await result
        except Exception as exc:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Course catalog request failed: {exc}") from exc

        normalized = _json_value(result)
        _cache[cache_key] = (time.monotonic(), normalized)
        return normalized


async def _call_sais_student_info(db: AsyncSession, user: AuthenticatedUser) -> Any:
    cache_key = (str(user.id), "sais_get_student_info")
    cached = _cached(cache_key)
    if cached is not None:
        return cached
    agent = await manager.get_agent_or_404(db, user.id)
    resident = await manager.resident_for(db, agent)
    toolkit = next((item for item in resident.toolkits if item.name == "campus:sais"), None)
    function = (toolkit.functions or {}).get("sais_get_student_info") if toolkit else None
    if function is None or function.entrypoint is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "SAIS student information access is not enabled")
    try:
        result = function.entrypoint()
        if inspect.isawaitable(result):
            result = await result
    except Exception as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"SAIS student information request failed: {exc}") from exc
    normalized = _json_value(result)
    _cache[cache_key] = (time.monotonic(), normalized)
    return normalized


def _department_query(value: Any) -> str | None:
    if isinstance(value, str):
        # FastMCP text results may arrive as a rendered table or a plain-text
        # summary instead of a JSON object.  Only read explicitly labelled
        # department/program rows so unrelated three-digit values (student id,
        # year, etc.) can never be mistaken for a department.
        text = value.strip()
        try:
            decoded = json.loads(text)
        except json.JSONDecodeError:
            decoded = None
        if decoded is not None and decoded != value:
            return _department_query(decoded)
        for pattern in (
            r"(?im)^\s*(?:department|dept\.?|program(?:me)?|b[oö]l[uü]m)\s*[:|=-]\s*([^\r\n|]+)",
            r"(?im)^\s*\|?\s*(?:department|dept\.?|program(?:me)?|b[oö]l[uü]m)\s*\|\s*([^|\r\n]+)",
            r'(?i)["\'][^"\']*(?:department|dept\.?|program(?:me)?|b[oö]l[uü]m)[^"\']*["\']\s*:\s*["\']([^"\']+)',
        ):
            match = re.search(pattern, text)
            if match and (candidate := match.group(1).strip(" *`\t")):
                return candidate
        return None
    if isinstance(value, list):
        return next((result for item in value if (result := _department_query(item))), None)
    if not isinstance(value, dict):
        return None
    for key, item in value.items():
        normalized_key = str(key).lower().replace("_", "").replace("-", "")
        if any(part in normalized_key for part in ("department", "program", "bolum", "bölüm")) and isinstance(item, (str, int)):
            text = str(item).strip()
            if text:
                return text
    return next((result for item in value.values() if (result := _department_query(item))), None)


@router.get("/student-context")
async def student_context(
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    context = await db.get(StudentContext, user.id)
    if context is None or not (context.department or context.program_code):
        try:
            await sync_student_context_from_sais(user.id)
            await db.rollback()
            context = await db.get(StudentContext, user.id)
        except Exception as exc:
            logger.warning("schedule_context_sync_failed", user_id=str(user.id), error=str(exc))
    student = (
        {
            "department": context.department,
            "degree_level": context.degree_level,
            "program_code": context.program_code,
            "campus": context.campus,
            "source": context.source,
        }
        if context
        else None
    )
    query = (context.department or context.program_code) if context else None
    departments = None
    direct_code = re.search(r"\b\d{3}\b", context.program_code or "") if context else None
    if query and not direct_code:
        try:
            departments = await _call_course_info(db, user, "search_departments", {"query": query})
        except HTTPException:
            departments = None
    return {
        "student": student,
        "department_query": query,
        "department_code": direct_code.group(0) if direct_code else None,
        "departments": departments,
    }


@router.get("/metadata")
async def metadata(
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return {"data": await _call_course_info(db, user, "get_departments_and_semesters", {})}


@router.get("/departments/search")
async def search_departments(
    query: str = Query(min_length=1, max_length=100),
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return {"data": await _call_course_info(db, user, "search_departments", {"query": query})}


@router.get("/courses")
async def courses(
    department: str = Query(min_length=1, max_length=20),
    semester: str = Query(min_length=1, max_length=20),
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return {"data": await _call_course_info(db, user, "list_program_courses", {"department": department, "semester": semester})}


def _category_candidates(value: Any) -> list[str]:
    candidates: list[str] = []

    def visit(item: Any) -> None:
        if isinstance(item, list):
            for child in item:
                visit(child)
            return
        if not isinstance(item, dict):
            return
        normalized = {str(key).lower().replace("_", "").replace("-", ""): child for key, child in item.items()}
        if not any("course" in key for key in normalized):
            for key in ("categoryid", "categorycode", "category", "id", "code", "name"):
                candidate = normalized.get(key)
                if isinstance(candidate, (str, int)) and str(candidate).strip():
                    candidates.append(str(candidate).strip())
                    break
        for child in item.values():
            visit(child)

    visit(value)
    return list(dict.fromkeys(candidates))[:24]


@router.get("/curriculum")
async def curriculum(
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the student's curriculum categories and their course rows.

    This is a direct MCP data pipeline. It does not construct or run an Agent
    and therefore does not invoke an LLM or consume model tokens.
    """
    categories = await _call_course_info(db, user, "get_student_course_categories", {})
    category_courses: list[dict[str, Any]] = []
    for category in _category_candidates(categories):
        try:
            courses_for_category = await _call_course_info(
                db,
                user,
                "get_student_courses_by_category",
                {"category": category},
            )
        except HTTPException:
            continue
        category_courses.append({"category": category, "courses": courses_for_category})
    return {"categories": categories, "category_courses": category_courses}


@router.get("/courses/{course_code}")
async def course_sections(
    course_code: str,
    department: str = Query(min_length=1, max_length=20),
    semester: str = Query(min_length=1, max_length=20),
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    compact_course = course_code.upper().replace(" ", "").replace("-", "")
    # A full METU course code carries the owning department in its first
    # three digits. Service/common courses in a student's curriculum (MATH,
    # PHYS, ENG, etc.) must be looked up through their own department rather
    # than the student's home department.
    lookup_department = compact_course[:3] if compact_course.isdigit() and len(compact_course) == 7 else department
    if not compact_course.isdigit() and (number := re.search(r"(\d{3})$", compact_course)):
        compact_course = f"{lookup_department}0{number.group(1)}"
    elif compact_course.isdigit() and len(compact_course) == 3:
        compact_course = f"{lookup_department}0{compact_course}"
    # Course Info's contract accepts the full seven-digit METU code even
    # though department is also a separate argument (e.g. 5670201).
    data = await _call_course_info(
            db,
            user,
            "get_course_info",
            {"department": lookup_department, "semester": semester, "course": compact_course},
        )
    return {"data": data}


def _json_from_agent(value: Any) -> dict[str, Any]:
    content = getattr(value, "content", value)
    if not isinstance(content, str):
        content = json.dumps(_json_value(content), ensure_ascii=False)
    text = content.strip()
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Schedule assistant returned an invalid response")
        try:
            parsed = json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Schedule assistant returned invalid JSON") from exc
    if not isinstance(parsed, dict):
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Schedule assistant response must be an object")
    return parsed


@router.post("/ai-plan")
async def ai_schedule_plan(
    body: AiScheduleRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Use one bounded agent run to fill gaps left by direct catalog calls."""
    snapshot = await db.scalar(
        select(StudentAcademicSnapshot)
        .where(StudentAcademicSnapshot.user_id == user.id)
        .order_by(StudentAcademicSnapshot.fetched_at.desc())
        .limit(1)
    )
    completed_codes = []
    if snapshot:
        for item in snapshot.completed_courses:
            if isinstance(item, str) and item.strip():
                completed_codes.append(item.strip())
            elif isinstance(item, dict):
                for key in ("course_code", "courseCode", "code", "course", "ders_kodu"):
                    value = item.get(key)
                    if isinstance(value, (str, int)) and str(value).strip():
                        completed_codes.append(str(value).strip())
                        break
    agent_record = await manager.get_agent_or_404(db, user.id)
    lock_owner = f"schedule-{uuid4()}"
    if not await manager.acquire_turn_lock(db, agent_record, lock_owner):
        raise HTTPException(status.HTTP_409_CONFLICT, "Agent is busy with another message")
    lease = None
    try:
        lease = await manager.lease_for(db, agent_record)
        from app.agents.scholar.context import build_run_dependencies

        dependencies = await build_run_dependencies(db, user.id, lease.resident)
        # Only course identifiers enter the instruction. Display names can be
        # user-authored, so keeping them out prevents prompt-shaped names from
        # changing the planner contract.
        requested = [item.code for item in body.courses]
        prompt = f"""You are preparing machine-readable input for Devrimo's METU schedule planner.
Use the connected Course Info and SAIS tools. Verify the target semester FIRST and never infer that a course is offered merely from a prior semester.
Student's home department: {body.department}
Target semester: {body.semester}
Requested course pool: {json.dumps(requested, ensure_ascii=False)}
Completed courses from the stored SAIS transcript snapshot: {json.dumps(completed_codes, ensure_ascii=False)}

Return ONLY valid JSON with this exact shape:
{{"courses":[{{"code":"full METU course code","name":"official name","credits":0,"sections":[{{"section":"1","instructor":"","meetings":[{{"day":"Mon|Tue|Wed|Thu|Fri","start":9,"duration":1,"room":""}}]}}]}}],"warnings":[]}}

Rules:
- For an empty requested pool, return course recommendations only. Read the student's actual curriculum/category details and transcript, determine the next unmet requirements from completed prerequisites and curriculum order, then intersect them with courses actually offered in {body.semester}. Do not guess the student's semester number.
- Course recommendation and section lookup are separate operations. For an empty requested pool, do not fetch section details, return `sections: []`, and do not warn about missing section or meeting times. The UI loads current section times directly when the student opens a course.
- The stored completed-course list is authoritative. Do not call SAIS transcript tools again when it is non-empty, and never recommend a completed course.
- If the stored completed-course list is empty, use SAIS transcript once before recommending courses.
- For a non-empty pool, return only those courses that are actually offered in {body.semester}.
- Department {body.department} identifies the student's degree program; it is NOT a course filter. Include required common, service, elective, and cross-department courses (for example MATH, PHYS, ENG, CENG) when the curriculum requires them.
- Use each course's full seven-digit METU code as its identity. Its first three digits identify the department that owns that course. Never rewrite an external course with the student's home-department prefix.
- Compare completed and recommended courses by their full course codes. Do not treat courses from different departments that share the same last three digits as the same course.
- Course codes must be full seven-digit METU codes when available.
- Section and meeting data must come from tools. Never invent a day, time, room, section, credit, or offering status.
- If a course is verified but its meeting times are unavailable, include the course with an empty sections array and add a short warning.
- Do not include prose, Markdown, citations, or reasoning outside the JSON."""
        result = await asyncio.wait_for(
            lease.agent.arun(
                input=prompt,
                session_id=f"schedule-{uuid4()}",
                user_id=str(user.id),
                dependencies=dependencies,
                stream=False,
            ),
            timeout=180,
        )
        payload = _json_from_agent(result)
        warnings = [
            warning
            for warning in payload.get("warnings", [])
            if isinstance(warning, str)
            and not re.search(r"section|meeting time|şube|ders saat", warning, re.IGNORECASE)
        ]
        return {
            "courses": payload.get("courses", []),
            "warnings": warnings,
            "source": "ai_verified",
        }
    except TimeoutError as exc:
        raise HTTPException(status.HTTP_504_GATEWAY_TIMEOUT, "Course recommendation timed out; try again") from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("schedule_agent_failed", user_id=str(user.id), error=str(exc))
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "The course recommendation service failed. Department and term were not changed; try this step again.",
        ) from exc
    finally:
        if lease is not None:
            await lease.release()
        await manager.release_turn_lock(db, agent_record, lock_owner)
