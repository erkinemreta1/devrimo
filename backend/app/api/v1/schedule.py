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

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import manager
from app.auth.dependencies import get_current_user
from app.auth.jwt import AuthenticatedUser
from app.db.session import get_db

router = APIRouter()
_CACHE_TTL_SECONDS = 15 * 60
_cache: dict[tuple[str, ...], tuple[float, Any]] = {}
_locks: dict[str, asyncio.Lock] = {}


def _json_value(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    if isinstance(value, (dict, list, int, float, bool)) or value is None:
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
    student = await _call_sais_student_info(db, user)
    query = _department_query(student)
    departments = None
    if query:
        try:
            departments = await _call_course_info(db, user, "search_departments", {"query": query})
        except HTTPException:
            departments = None
    return {"student": student, "department_query": query, "departments": departments}


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
    if compact_course.startswith(department.upper()):
        # Keep METU's separator zero: department 567 + course 0201.
        compact_course = compact_course[len(department):] or "0"
    return {
        "data": await _call_course_info(
            db,
            user,
            "get_course_info",
            {"department": department, "semester": semester, "course": compact_course},
        )
    }
