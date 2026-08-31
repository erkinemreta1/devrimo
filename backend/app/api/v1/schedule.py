"""Token-free course catalog access for the visual schedule builder.

These endpoints call the already connected Course Info MCP function directly.
No Agent run, language model, prompt, memory, or learning pass is involved.
"""

import asyncio
import inspect
import json
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
    cache_key = (tool_suffix, *(f"{key}={value}" for key, value in sorted(values.items())))
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


@router.get("/courses/{course_code}")
async def course_sections(
    course_code: str,
    department: str = Query(min_length=1, max_length=20),
    semester: str = Query(min_length=1, max_length=20),
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return {
        "data": await _call_course_info(
            db,
            user,
            "get_course_info",
            {"department": department, "semester": semester, "course": course_code},
        )
    }
