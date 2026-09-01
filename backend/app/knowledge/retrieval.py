"""Scoping a campus search to the student who asked.

"When is Add-Drop week?" is the question this module exists for. The calendar
contributes 153 documents; roughly a dozen of them mention adding or dropping
something, and they differ by who they apply to — undergraduates, graduate
programmes, the English preparatory school, students registering for the first
time. Handing all of them to the model and hoping it picks the right one is not
an answer to "tailored to the student's department and degree level"; filtering
them before the model sees them is.

The filtering runs here in Python rather than in the vector store's own filter
DSL because that DSL compares a metadata key to a *scalar*, and this corpus is
scoped by lists: a document may name several departments, or none at all.
"University-wide" — the common case, and the one Add-Drop itself falls into —
has to mean "matches everybody", which a scalar equality cannot express.

Nothing retrieved here is trusted. Every document is text scraped from a page
anyone with a course account can post to, so the wrapper hands it to the model
labelled as data, and the persona's existing prompt-injection rule covers the
rest.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.config import get_settings
from app.knowledge.store import SearchHit, knowledge_available, search
from app.logging import get_logger
from app.observability import capture, capture_exception
from app.observability.llm import current_session_id, current_trace_id

logger = get_logger(__name__)

# Candidates pulled before filtering. Generous because scoping can discard most
# of a page of results — a graduate student's Add-Drop row sits below several
# undergraduate ones that all match the query equally well.
#
# This over-fetch is the cost of filtering in Python, and it has a limit worth
# stating: if the corpus grows until a narrowly-scoped student's documents no
# longer appear within the top MAX_CANDIDATES, they will see fewer results than
# they asked for rather than wrong ones. At the size this corpus is designed for
# — a few thousand announcements, calendar rows, and FAQ articles — that does
# not happen. The fix when it does is a scalar ``primary_department`` in the
# metadata that the vector store can pre-filter on, not a larger multiplier.
CANDIDATE_MULTIPLIER = 4
MAX_CANDIDATES = 60


@dataclass(frozen=True)
class StudentScope:
    """Who is asking, as far as the corpus is concerned."""

    department: str | None = None
    degree_level: str | None = None
    language: str = "tr"

    @classmethod
    def from_dependencies(cls, dependencies: dict[str, Any] | None) -> "StudentScope":
        dependencies = dependencies or {}
        department = dependencies.get("department")
        return cls(
            department=str(department).strip().upper() if department else None,
            degree_level=(dependencies.get("degree_level") or None),
            language=dependencies.get("locale") or "tr",
        )


def matches_scope(meta_data: dict[str, Any], scope: StudentScope) -> bool:
    """Whether one document is for this student.

    Empty is universal, in both directions. A document that names no department
    is university-wide and matches everyone; a student whose profile has no
    department yet is shown everything rather than nothing, because an
    incomplete profile must not silently empty the corpus.
    """
    departments = [str(value).upper() for value in meta_data.get("departments") or []]
    if departments and scope.department and scope.department not in departments:
        return False

    degree_levels = [str(value).lower() for value in meta_data.get("degree_levels") or []]
    if degree_levels and scope.degree_level and scope.degree_level.lower() not in degree_levels:
        return False

    return not _expired(meta_data)


def _expired(meta_data: dict[str, Any]) -> bool:
    """Whether a curated entry's validity window has closed.

    Enforced at read time as well as at ingest, because an entry can expire
    between two refreshes and a dead WhatsApp invite is worse than no answer.
    """
    raw = meta_data.get("valid_until")
    if not raw:
        return False
    try:
        valid_until = datetime.fromisoformat(str(raw))
    except ValueError:
        return False
    if valid_until.tzinfo is None:
        valid_until = valid_until.replace(tzinfo=UTC)
    return valid_until < datetime.now(UTC)


def rank_key(meta_data: dict[str, Any], scope: StudentScope) -> tuple:
    """Tie-break ordering: specific to this student first, then most recent.

    Relevance is the vector store's job and this does not second-guess it — it
    only orders documents the store already considered comparable. A CENG
    announcement outranks a university-wide one *for a CENG student*, and a
    document in their language outranks a translation, because both are more
    likely to be the one they meant.
    """
    departments = [str(value).upper() for value in meta_data.get("departments") or []]
    specific = bool(scope.department and scope.department in departments)
    same_language = meta_data.get("language") == scope.language
    published = meta_data.get("published_at") or ""
    return (not specific, not same_language, _negated_date(published))


def _negated_date(value: str) -> str:
    """Sort ISO dates descending inside an ascending tuple sort."""
    # Complement each digit so that a later date compares smaller. Cheap, and
    # avoids parsing a field that is free-form across four site generations.
    return "".join(chr(0x7E - ord(character)) if character.isdigit() else character for character in value)


def format_hit(hit: SearchHit) -> dict[str, Any]:
    """One result as the model should see it: content plus its provenance.

    The persona is required to name the source and its retrieval time, so those
    are handed over as fields rather than left for the model to infer from a
    URL. ``trust`` is stated explicitly for the same reason the campus tool
    results are: this is scraped text, not something the student said.
    """
    meta = hit.meta_data
    return {
        "title": meta.get("title"),
        "content": hit.content,
        "source": meta.get("source_name") or meta.get("source_slug"),
        "url": meta.get("url"),
        "kind": meta.get("kind"),
        "language": meta.get("language"),
        "published_at": meta.get("published_at"),
        "retrieved_at": meta.get("fetched_at"),
        "date_start": meta.get("date_start"),
        "date_end": meta.get("date_end"),
        "section": meta.get("section"),
        "academic_year": meta.get("academic_year"),
        "trust": "untrusted_campus_content",
    }


def _capture_span(query: str, *, scope: StudentScope, candidates: int, returned: int, user_id: str | None) -> None:
    trace_id = current_trace_id.get()
    if trace_id is None:
        return
    from uuid import uuid4

    capture(
        "$ai_span",
        distinct_id=user_id,
        **{
            "$ai_trace_id": trace_id,
            "$ai_session_id": current_session_id.get(),
            "$ai_parent_id": trace_id,
            "$ai_span_id": str(uuid4()),
            "$ai_span_name": "search_campus_knowledge",
            "$ai_input_state": query[:500],
            "$ai_output_state": f"{returned} of {candidates} candidates",
            "campus_scope_department": scope.department,
            "campus_scope_degree_level": scope.degree_level,
            "campus_candidates": candidates,
            "campus_returned": returned,
        },
    )


async def retrieve(
    query: str,
    *,
    scope: StudentScope,
    num_documents: int | None = None,
    user_id: str | None = None,
) -> list[dict[str, Any]]:
    """Search the corpus and return only what is for this student."""
    if not knowledge_available():
        return []
    limit = num_documents or get_settings().campus_knowledge_max_results
    candidates = min(max(limit * CANDIDATE_MULTIPLIER, limit), MAX_CANDIDATES)

    hits = await search(query, limit=candidates)
    scoped = [hit for hit in hits if matches_scope(hit.meta_data, scope)]
    scoped.sort(key=lambda hit: rank_key(hit.meta_data, scope))
    results = [format_hit(hit) for hit in scoped[:limit]]
    _capture_span(query, scope=scope, candidates=len(hits), returned=len(results), user_id=user_id)
    return results


def build_retriever():
    """The ``knowledge_retriever`` Scholar is constructed with.

    Agno inspects this signature and passes only the parameters it declares, so
    taking ``run_context`` is what gives the retriever access to the per-run
    dependencies :mod:`app.agents.scholar.context` already assembles — the
    student's department, degree level and locale, with no new plumbing.
    """

    async def campus_knowledge_retriever(query: str, num_documents: int | None = None, run_context=None):
        dependencies = getattr(run_context, "dependencies", None) if run_context is not None else None
        scope = StudentScope.from_dependencies(dependencies)
        user_id = getattr(run_context, "user_id", None) if run_context is not None else None
        try:
            return await retrieve(query, scope=scope, num_documents=num_documents, user_id=user_id)
        except Exception as exc:
            # A corpus that is down must not take the turn down with it: the
            # student still has their campus MCP tools, and the persona already
            # says to admit when a source could not be reached.
            logger.warning("campus_knowledge_search_failed", error=str(exc))
            capture_exception(
                exc,
                distinct_id=user_id,
                **{"$exception_fingerprint": ["campus_knowledge_search_failed"]},
            )
            return []

    return campus_knowledge_retriever
