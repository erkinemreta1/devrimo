"""Bounded tool results and privacy-preserving mutation audit hooks."""

import hashlib
import inspect
import json
import time
from typing import Any
from uuid import UUID

from app.campus.course_codes import annotate_course_codes
from app.db.models import AgentToolAudit
from app.db.session import SessionLocal
from app.logging import get_logger

logger = get_logger(__name__)
MAX_TOOL_RESULT_CHARS = 16_000
MUTATING_TOOL_NAMES = {"webmail_send_email", "webmail_reply_email"}
COURSE_DATA_TOOL_NAMES = {
    "get_schedule",
    "get_transcript",
    "list_program_courses",
    "get_course_info",
    "get_course_prerequisites",
    "get_course_replacements",
    "get_thesis_courses",
    "get_student_course_categories",
    "get_student_courses_by_category",
    "get_enrolled_courses",
    "get_course_announcements",
    "get_course_syllabus",
    "get_upcoming_assignments",
    "get_lab_recitation_info",
}


def _is_course_data_tool(function_name: str) -> bool:
    return any(
        function_name == tool_name or function_name.endswith(f"_{tool_name}")
        for tool_name in COURSE_DATA_TOOL_NAMES
    )


def _canonical_digest(arguments: dict[str, Any]) -> str:
    serialized = json.dumps(arguments, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(serialized.encode()).hexdigest()


def _bound_result(result: Any) -> Any:
    if isinstance(result, str) and len(result) > MAX_TOOL_RESULT_CHARS:
        return (
            result[:MAX_TOOL_RESULT_CHARS]
            + f"\n\n[Result truncated by Devrimo after {MAX_TOOL_RESULT_CHARS} characters. Narrow the query.]"
        )
    if isinstance(result, (dict, list)):
        serialized = json.dumps(result, ensure_ascii=False, default=str)
        if len(serialized) > MAX_TOOL_RESULT_CHARS:
            return {
                "truncated": True,
                "preview": serialized[:MAX_TOOL_RESULT_CHARS],
                "instruction": "Narrow the query before using this result.",
            }
    return result


async def record_confirmation_rejection(
    *, user_id: str, session_id: str, run_id: str, tool_name: str, arguments: dict[str, Any]
) -> None:
    """Record a declined external mutation without retaining its contents."""
    if tool_name not in MUTATING_TOOL_NAMES:
        return
    try:
        async with SessionLocal() as db:
            db.add(
                AgentToolAudit(
                    user_id=UUID(user_id),
                    session_id=session_id,
                    run_id=run_id,
                    tool_name=tool_name,
                    status="rejected",
                    argument_digest=_canonical_digest(arguments),
                    duration_ms=0,
                    error_code=None,
                )
            )
            await db.commit()
    except Exception as audit_error:
        logger.error("agent_tool_audit_failed", tool=tool_name, error=audit_error.__class__.__name__)


async def _write_mutation_audit(
    *, run_context, name: str, arguments: dict[str, Any], status: str, started: float, error
):
    if name not in MUTATING_TOOL_NAMES or run_context is None or not run_context.user_id:
        return
    try:
        async with SessionLocal() as db:
            db.add(
                AgentToolAudit(
                    user_id=UUID(run_context.user_id),
                    session_id=run_context.session_id,
                    run_id=run_context.run_id,
                    tool_name=name,
                    status=status,
                    argument_digest=_canonical_digest(arguments),
                    duration_ms=max(0, round((time.monotonic() - started) * 1000)),
                    error_code=error.__class__.__name__[:128] if error else None,
                )
            )
            await db.commit()
    except Exception as audit_error:  # the audit sink must not leak arguments or break a read/write result
        logger.error("agent_tool_audit_failed", tool=name, error=audit_error.__class__.__name__)


async def production_tool_hook(function_name, function, arguments, run_context=None):
    """Execute one tool, cap text output, and audit external mutations."""
    started = time.monotonic()
    error = None
    try:
        result = function(**arguments)
        if inspect.isawaitable(result):
            result = await result
        logger.info("agent_tool_completed", tool=function_name, duration_ms=round((time.monotonic() - started) * 1000))
        if _is_course_data_tool(function_name):
            result = annotate_course_codes(result)
        return _bound_result(result)
    except Exception as exc:
        error = exc
        logger.warning(
            "agent_tool_failed",
            tool=function_name,
            duration_ms=round((time.monotonic() - started) * 1000),
            error=exc.__class__.__name__,
        )
        raise
    finally:
        await _write_mutation_audit(
            run_context=run_context,
            name=function_name,
            arguments=arguments,
            status="failed" if error else "completed",
            started=started,
            error=error,
        )
