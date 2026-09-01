"""Read-only bridge from legacy per-user MCPs into typed planning snapshots.

The agent never supplies transcript values to the planner. This bridge calls
the connected SAIS functions directly, normalizes their structured results,
and persists only the typed private snapshot used by deterministic code.
"""

import json
from collections.abc import Iterable
from typing import Any
from uuid import UUID

from agno.tools.mcp import MCPTools

from app.db.session import SessionLocal
from app.planning.service import upsert_academic_snapshot
from app.student.service import apply_verified_context


def _function(toolkits: Iterable[MCPTools], name: str):
    for toolkit in toolkits:
        function = (toolkit.functions or {}).get(name)
        if function is not None:
            return function
    return None


async def _payload(function) -> Any:
    if function is None or function.entrypoint is None:
        return None
    result = await function.entrypoint()
    metadata = getattr(result, "metadata", None) or {}
    if metadata.get("structured_content") is not None:
        return metadata["structured_content"]
    content = getattr(result, "content", result)
    if isinstance(content, str):
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return None
    return content


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
    if not completed and credits <= 0:
        return False
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
            await apply_verified_context(
                db,
                user_id,
                department=str(_find_value(student_info, {"department", "bolum"}) or "") or None,
                degree_level=str(_find_value(student_info, {"degree_level", "level", "program_level"}) or "") or None,
                program_code=str(_find_value(student_info, {"program_code", "program"}) or "") or None,
                campus=str(_find_value(student_info, {"campus", "yerleske"}) or "") or None,
            )
    return True
