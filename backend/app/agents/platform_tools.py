"""Broad first-party tools backed by the shared campus intelligence services."""

from datetime import datetime
from uuid import UUID

from agno.tools.decorator import tool

from app.db.session import SessionLocal
from app.knowledge.retrieval import SearchFilters, search_knowledge
from app.knowledge.retrieval import read_campus_page as read_indexed_page
from app.planning.calculator import compute as calculate
from app.planning.groups import get_course_group as resolve_course_group
from app.planning.mcp_bridge import refresh_from_sais
from app.planning.service import SemesterPlanRequest
from app.planning.service import plan_semester as build_plan
from app.student import service as student_service


def build_platform_tools(user_id: UUID, connected: list) -> list:
    @tool(name="search_campus_knowledge")
    async def search_campus_knowledge(
        query: str,
        record_types: list[str] | None = None,
        starts_after: str | None = None,
        starts_before: str | None = None,
        limit: int = 10,
    ) -> list[dict]:
        """Search indexed campus facts with verified student-audience filters and citations."""
        async with SessionLocal() as db:
            context = await student_service.get_context(db, user_id)
            return await search_knowledge(
                db,
                query,
                SearchFilters(
                    record_types=tuple(record_types or []),
                    campus=context.campus,
                    department=context.department,
                    degree_level=context.degree_level,
                    starts_after=datetime.fromisoformat(starts_after) if starts_after else None,
                    starts_before=datetime.fromisoformat(starts_before) if starts_before else None,
                ),
                limit=max(1, min(limit, 25)),
            )

    @tool(name="read_campus_page")
    async def read_campus_page(url: str) -> dict:
        """Read one already-approved, indexed campus page by its canonical URL."""
        async with SessionLocal() as db:
            result = await read_indexed_page(db, url)
            return result or {"status": "not_indexed", "url": url}

    @tool(name="plan_semester")
    async def plan_semester(request: dict) -> dict:
        """Deterministically plan from server-fetched transcript, offerings, prerequisites, and policies."""
        parsed = SemesterPlanRequest.model_validate(request)
        await refresh_from_sais(user_id, parsed.term, connected)
        async with SessionLocal() as db:
            return await build_plan(db, user_id, parsed)

    @tool(name="get_course_group")
    async def get_course_group(course: str, term: str, section: str | None = None) -> dict:
        """Return a curated course-group invite only after code-level enrollment checks."""
        await refresh_from_sais(user_id, term, connected)
        async with SessionLocal() as db:
            return await resolve_course_group(db, user_id, term=term, course_code=course, section=section)

    @tool(name="compute")
    def compute(expression: str) -> float:
        """Safely evaluate arithmetic expressions without code execution."""
        return calculate(expression)

    return [search_campus_knowledge, read_campus_page, plan_semester, get_course_group, compute]
