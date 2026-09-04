"""Read-only bridge from legacy per-user MCPs into typed planning snapshots.

The agent never supplies transcript values to the planner. This bridge calls
the connected SAIS functions directly, normalizes their structured results,
and persists only the typed private snapshot used by deterministic code.
"""

from collections.abc import AsyncIterator, Iterable
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID

from agno.tools.mcp import MCPTools
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.toolset import build_toolkits, close_toolkits, connect_toolkits
from app.campus import service as campus_service
from app.campus.mcp_results import mcp_payload
from app.config import get_settings
from app.db.session import SessionLocal
from app.logging import get_logger
from app.planning.service import upsert_academic_snapshot
from app.student.service import apply_verified_context

logger = get_logger(__name__)


def _function(toolkits: Iterable[MCPTools], name: str):
    for toolkit in toolkits:
        function = (toolkit.functions or {}).get(name)
        if function is not None:
            return function
    return None


async def _payload(function) -> Any:
    if function is None or function.entrypoint is None:
        return None
    payload = mcp_payload(await function.entrypoint())
    # A payload still in string form means the server answered with prose
    # rather than a document, which this bridge has no way to normalize.
    return None if isinstance(payload, str) else payload


def _find_value(value: Any, keys: set[str]) -> Any:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() in keys and child not in (None, ""):
                return child
        for child in value.values():
            found = _find_value(child, keys)
            if found not in (None, ""):
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_value(child, keys)
            if found not in (None, ""):
                return found
    return None


def _course_rows(value: Any) -> list[dict]:
    rows: list[dict] = []
    if isinstance(value, dict):
        normalized = {str(key).lower(): child for key, child in value.items()}
        code = next(
            (
                normalized[key]
                for key in ("course_code", "code", "ders_kodu", "course")
                if key in normalized and normalized[key]
            ),
            None,
        )
        if code:
            row = {"course_code": "".join(str(code).upper().split())}
            grade = next(
                (normalized[key] for key in ("grade", "letter_grade", "not") if normalized.get(key)), None
            )
            section = next((normalized[key] for key in ("section", "sube") if normalized.get(key)), None)
            credits = next(
                (normalized[key] for key in ("credits", "credit", "local_credit") if normalized.get(key) is not None),
                None,
            )
            if grade:
                row["grade"] = str(grade).upper()
            if section is not None:
                row["section"] = str(section)
            if credits is not None:
                row["credits"] = credits
            rows.append(row)
        else:
            for child in value.values():
                rows.extend(_course_rows(child))
    elif isinstance(value, list):
        for child in value:
            rows.extend(_course_rows(child))
    unique: dict[tuple[str, str | None, str | None], dict] = {}
    for row in rows:
        unique[(row["course_code"], row.get("section"), row.get("grade"))] = row
    return list(unique.values())


def _number(value: Any, default: float = 0) -> float:
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return default


async def refresh_from_sais(user_id: UUID, term: str, connected: list[MCPTools]) -> bool:
    """Store this student's transcript snapshot; ``False`` when SAIS gave nothing.

    An *empty* transcript is an answer, not a failure. A first-semester student
    has no completed courses and no credits, and treating that as a failed
    fetch left them with no snapshot, no stored context, and a "could not be
    fetched from SAIS" error on every refresh they tried. Only SAIS being
    unreachable or unreadable — no transcript tool, no payload — returns False.
    """
    transcript_fn = _function(connected, "sais_get_transcript")
    if transcript_fn is None:
        return False
    transcript = await _payload(transcript_fn)
    if transcript is None:
        return False
    schedule = await _payload(_function(connected, "sais_get_schedule"))
    student_info = await _payload(_function(connected, "sais_get_student_info"))
    completed = [row for row in _course_rows(transcript) if row.get("grade")]
    enrolled = _course_rows(schedule)
    credits = _number(
        _find_value(transcript, {"total_credits", "completed_credits", "credits_completed", "toplam_kredi"})
    )
    cgpa = _number(_find_value(transcript, {"cgpa", "cumulative_gpa", "gpa", "genel_not_ortalamasi"}))
    async with SessionLocal() as db:
        await upsert_academic_snapshot(
            db,
            user_id,
            term,
            completed_courses=completed,
            enrolled_courses=enrolled,
            current_credits=credits,
            current_grade_points=credits * cgpa,
            source="sais",
        )
        if student_info is not None:
            await _apply_student_info(db, user_id, student_info)
    return True


async def _apply_student_info(db: AsyncSession, user_id: UUID, student_info: Any) -> None:
    await apply_verified_context(
        db,
        user_id,
        department=str(_find_value(student_info, {"department", "bolum"}) or "") or None,
        degree_level=str(_find_value(student_info, {"degree_level", "level", "program_level"}) or "") or None,
        program_code=str(_find_value(student_info, {"program_code", "program"}) or "") or None,
        campus=str(_find_value(student_info, {"campus", "yerleske"}) or "") or None,
    )


@asynccontextmanager
async def _campus_session(user_id: UUID) -> AsyncIterator[list[MCPTools]]:
    """Connect this student's campus servers for one read outside a turn.

    The pool owns the long-lived connections, but it only builds them for a
    chat turn. This is the short-lived equivalent for a request that has to
    read SAIS without one: it spawns the servers, yields them, and always
    closes them, because a leaked subprocess holds the student's credentials
    in memory.
    """
    settings = get_settings()
    async with SessionLocal() as db:
        specs = await campus_service.campus_server_specs(db, user_id)
    connected = await connect_toolkits(build_toolkits(specs, timeout_seconds=settings.campus_mcp_timeout_seconds))
    try:
        yield connected
    finally:
        await close_toolkits(connected)


async def sync_student_context_from_sais(user_id: UUID) -> bool:
    """Fill the student's verified academic context right after they connect.

    :func:`refresh_from_sais` only runs inside a turn, when the model calls a
    planning tool, so a student who connected SAIS and opened their profile saw
    an empty academic context until they happened to ask a planning question.

    Reads ``sais_get_student_info`` alone — department, degree level, program
    code, campus, which is exactly what the profile shows. The transcript is
    deliberately not read here: it needs a term this path has no way to choose,
    and it is private data the profile never displays. The stored context is
    marked verified but unconfirmed, so the student still confirms it before
    anything uses it.
    """
    async with _campus_session(user_id) as connected:
        student_info = await _payload(_function(connected, "sais_get_student_info"))
        if student_info is None:
            return False
        async with SessionLocal() as db:
            await _apply_student_info(db, user_id, student_info)
    logger.info("student_context_synced", user_id=str(user_id))
    return True


async def sync_planning_snapshot_from_sais(user_id: UUID, term: str) -> bool:
    """Refresh the existing deterministic planner without starting an agent run."""
    async with _campus_session(user_id) as connected:
        return await refresh_from_sais(user_id, term, connected)
