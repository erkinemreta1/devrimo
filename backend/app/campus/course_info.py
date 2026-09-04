"""Token-free reads of the Course Info MCP server.

The schedule builder needs the METU catalog, not an opinion about it: which
courses a department offers this term, which sections a course has, which
department a code belongs to. All of that is already exposed by the connected
Course Info server, so these helpers call its functions directly — no Agent
run, no model, no prompt, no tokens.

Owning the cache here rather than in the HTTP layer is what lets
``DELETE /student/academic-data`` actually reach it: a student who asks for
their stored data to be removed should not keep being served their department
from a dict inside a request handler.
"""

import inspect
import re
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import manager
from app.campus.mcp_results import mcp_payload, parse_json_document
from app.core.ttl_cache import TTLCache

TOOLKIT_NAME = "campus:course_info"

# Catalog data changes when the registrar publishes, not between page loads, so
# a quarter hour is generous; the bound exists so a long-lived worker's cache
# cannot grow with every course any student has ever opened.
_catalog = TTLCache(ttl_seconds=15 * 60, max_entries=4096)

_THREE_DIGITS = re.compile(r"^\d{3}$")
_ALPHA_PREFIX = re.compile(r"^[A-Z]{2,6}")

# Every Course Info tool names its arguments slightly differently across
# versions. Listed most specific first so a schema carrying both ``category``
# and a generic ``name`` binds the value to the one that means it.
_ARGUMENT_ALIASES = {
    "department": ("department", "department_code", "dept", "dept_code", "program", "program_code"),
    "semester": ("semester", "semester_code", "term", "term_code"),
    "course": ("course", "course_code", "code"),
    "query": ("query", "keyword", "search", "name"),
    "category": ("category", "category_id", "category_code", "code", "id", "name"),
}


def forget_user(user_id: UUID) -> None:
    """Drop every cached catalog answer belonging to one student."""
    prefix = str(user_id)
    _catalog.purge(lambda key: isinstance(key, tuple) and bool(key) and key[0] == prefix)


def json_value(value: Any) -> Any:
    """Coerce an unwrapped MCP payload into plain JSON-serialisable data."""
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    if isinstance(value, str):
        parsed = parse_json_document(value)
        return parsed if isinstance(parsed, str) else json_value(parsed)
    if isinstance(value, list):
        return [json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: json_value(item) for key, item in value.items()}
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)


async def call_course_info(
    db: AsyncSession,
    user_id: UUID,
    tool_suffix: str,
    values: dict[str, str],
) -> Any:
    """Call one Course Info function and return its payload as plain data.

    Some curriculum tools are student-specific, so the user id is part of the
    cache key and answers are never shared between accounts.
    """
    cache_key = (str(user_id), tool_suffix, *(f"{key}={value}" for key, value in sorted(values.items())))
    return await _catalog.run(cache_key, lambda: _invoke(db, user_id, tool_suffix, values))


async def _invoke(db: AsyncSession, user_id: UUID, tool_suffix: str, values: dict[str, str]) -> Any:
    agent = await manager.get_agent_or_404(db, user_id)
    resident = await manager.resident_for(db, agent)
    toolkit = next((item for item in resident.toolkits if item.name == TOOLKIT_NAME), None)
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
    return json_value(mcp_payload(result))


def _tool_arguments(function, values: dict[str, str]) -> dict[str, str]:
    properties = (function.parameters or {}).get("properties", {})
    arguments: dict[str, str] = {}
    for value_name, value in values.items():
        for candidate in _ARGUMENT_ALIASES[value_name]:
            if candidate in properties:
                arguments[candidate] = value
                break
    missing = set((function.parameters or {}).get("required", [])) - arguments.keys()
    if missing:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            f"Course Info tool schema is unsupported; missing arguments: {', '.join(sorted(missing))}",
        )
    return arguments


# --- department identity ----------------------------------------------------


def _normalized(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.casefold())


def _department_candidates(value: Any) -> list[tuple[str, str]]:
    """Every ``(code, name)`` pair a departments payload explicitly labels."""
    records: list[dict[str, Any]] = []

    def visit(item: Any) -> None:
        if isinstance(item, list):
            for child in item:
                visit(child)
            return
        if not isinstance(item, dict):
            return
        records.append(item)
        for child in item.values():
            visit(child)

    visit(value)

    candidates: list[tuple[str, str]] = []
    for record in records:
        code = ""
        name = ""
        for key, item in record.items():
            if not isinstance(item, (str, int)):
                continue
            normalized_key = _normalized(str(key))
            text = str(item).strip()
            if not code and "code" in normalized_key and _THREE_DIGITS.match(text):
                code = text
            if not name and "name" in normalized_key and text:
                name = text
        if code:
            candidates.append((code, name))
    return list(dict.fromkeys(candidates))


def department_code(value: Any, query: str) -> str | None:
    """The three-digit code of the department ``query`` names, or ``None``.

    Only a field explicitly labelled as a code is ever read, and only when it
    is exactly three digits. Scanning a payload for any three-digit run — which
    is what the frontend used to do — happily returns a student id, a year or a
    row count and then quietly serves someone else's course list.

    Ambiguity resolves to ``None`` rather than to a guess, for the same reason:
    the wrong department produces a completely plausible-looking answer, so the
    caller has to be able to tell that we did not know.
    """
    candidates = _department_candidates(value)
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0][0]
    wanted = _normalized(query)
    if not wanted:
        return None
    for match in (
        lambda name: name == wanted,
        lambda name: name.startswith(wanted),
        lambda name: wanted in name,
    ):
        hits = {code for code, name in candidates if match(_normalized(name))}
        if len(hits) == 1:
            return hits.pop()
    return None


async def resolve_department(db: AsyncSession, user_id: UUID, query: str) -> str | None:
    """Look a department name or abbreviation up in the catalog itself."""
    if not query.strip():
        return None
    departments = await call_course_info(db, user_id, "search_departments", {"query": query.strip()})
    return department_code(departments, query)


async def department_for_course(
    db: AsyncSession,
    user_id: UUID,
    compact_course: str,
    home_department: str,
) -> str:
    """The department that owns ``compact_course``.

    A full seven-digit METU code carries its owning department in the first
    three digits. An alphabetic code (``MATH260``) does not, and assuming the
    student's own department turns a service course into a lookup for a course
    that does not exist — a CENG student opening MATH 260 would be asking for
    5710260. The prefix is resolved through the catalog's own department search
    instead of guessed, and an unresolvable prefix is reported rather than
    silently answered from the wrong department.
    """
    if compact_course.isdigit() and len(compact_course) == 7:
        return compact_course[:3]
    prefix = _ALPHA_PREFIX.match(compact_course)
    if prefix is None:
        return home_department
    resolved = await resolve_department(db, user_id, prefix.group(0))
    if resolved is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"Could not identify which department owns {compact_course}. "
            "Use the course's full seven-digit METU code.",
        )
    return resolved
