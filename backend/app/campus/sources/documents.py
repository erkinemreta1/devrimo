"""Parsed items to corpus documents, with the metadata retrieval needs.

Two decisions live here and both come straight from the questions this layer
exists to answer.

**Audience tagging.** The academic calendar states who a row applies to in
prose — "Lisansüstü programlara", "Temel İngilizce Birimi", "YKS ile lisans
programlarına" — and never in a column. Without tagging, "when is Add-Drop
week?" retrieves against 153 undifferentiated rows and the model has to guess
which of them is about this student. ``audience_rules`` on the source turn
those phrases into ``degree_level:graduate``-style tags at ingest time, once,
instead of on every question.

**Content hashing.** Embeddings are bought from a hosted API. Re-embedding a
weekly-refreshed corpus that did not change would be the whole running cost of
this feature, so an unchanged document is recognised and skipped.
"""

import hashlib
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.campus.sources.models import SourceItem, SourceSpec

# How much of one page goes into a single document. Long enough to keep an
# announcement whole (they are short), short enough that one FAQ article does
# not dominate a retrieval.
MAX_DOCUMENT_CHARS = 6_000


@dataclass(frozen=True)
class CampusDocument:
    """One row of the corpus, ready to embed."""

    doc_id: str
    name: str
    content: str
    content_hash: str
    meta_data: dict[str, Any] = field(default_factory=dict)


def lower_tr(value: str) -> str:
    """Lower-case with Turkish's two dotted letters handled.

    ``"İngilizce".lower()`` under the C locale produces ``"i̇ngilizce"`` with a
    combining dot, which then fails a plain substring match against
    ``"ingilizce"``. Since the audience rules are matched case-insensitively
    against Turkish prose, getting this wrong silently drops the tag.
    """
    return value.replace("İ", "i").replace("I", "ı").lower()


def audience_tags(text: str, rules: dict[str, str]) -> list[str]:
    """Tags whose configured phrase appears in this item's text."""
    if not rules:
        return []
    haystack = lower_tr(text)
    found = {tag for phrase, tag in rules.items() if phrase and lower_tr(phrase) in haystack}
    return sorted(found)


def content_hash(title: str, body: str) -> str:
    """Stable digest of what would be embedded.

    Whitespace-normalised, because Drupal re-renders a page with different
    indentation on every deploy and that must not read as a content change.
    """
    normalised = re.sub(r"\s+", " ", f"{title}\n{body}").strip()
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()


def document_id(source_slug: str, external_id: str) -> str:
    """Stable id for one item of one source, so re-ingest updates in place."""
    return hashlib.sha256(f"{source_slug}\x00{external_id}".encode()).hexdigest()[:32]


def _truncate(body: str) -> str:
    if len(body) <= MAX_DOCUMENT_CHARS:
        return body
    return body[:MAX_DOCUMENT_CHARS].rsplit(" ", 1)[0] + " …"


def to_document(spec: SourceSpec, item: SourceItem, *, fetched_at: datetime | None = None) -> CampusDocument:
    fetched_at = fetched_at or datetime.now(UTC)
    body = _truncate(item.body.strip())
    # The title is repeated into the content on purpose: retrieval matches
    # against the embedded text, and a title-only match ("Ders Ekleme -
    # Bırakma") is exactly the case that has to work.
    content = f"{item.title}\n\n{body}".strip() if item.title else body

    extra = dict(item.extra or {})
    departments = list(extra.pop("departments", None) or spec.departments)
    degree_levels = list(extra.pop("degree_levels", None) or spec.degree_levels)
    tags = audience_tags(f"{item.title}\n{item.body}", spec.audience_rules)
    # A tag is the finer-grained statement, so it overrides the source-level
    # default: a graduate-only row on a university-wide calendar must not stay
    # university-wide just because the calendar as a whole is.
    for tag in tags:
        prefix, _, value = tag.partition(":")
        if prefix == "degree_level" and value and value not in degree_levels:
            degree_levels.append(value)

    meta_data: dict[str, Any] = {
        "source_slug": spec.slug,
        "source_name": spec.name,
        "kind": spec.kind,
        "title": item.title,
        "url": item.url,
        "language": item.language,
        "published_at": item.published_at.isoformat() if item.published_at else None,
        "fetched_at": fetched_at.isoformat(),
        "departments": departments,
        "degree_levels": degree_levels,
        "audience_tags": tags,
    }
    # Adapter-specific facts (calendar dates, curated entry keys) ride along
    # rather than being flattened into prose, so the retriever can use them.
    meta_data.update({key: value for key, value in extra.items() if value is not None})

    digest = content_hash(item.title, body)
    meta_data["content_hash"] = digest
    return CampusDocument(
        doc_id=document_id(spec.slug, item.external_id),
        name=item.title[:200] or spec.name,
        content=content,
        content_hash=digest,
        meta_data=meta_data,
    )


def to_documents(
    spec: SourceSpec, items: list[SourceItem], *, fetched_at: datetime | None = None
) -> list[CampusDocument]:
    fetched_at = fetched_at or datetime.now(UTC)
    documents: list[CampusDocument] = []
    seen: set[str] = set()
    for item in items:
        if item.is_empty():
            continue
        document = to_document(spec, item, fetched_at=fetched_at)
        if document.doc_id in seen:
            # A listing that links the same node under two language aliases
            # would otherwise be embedded twice and crowd out other results.
            continue
        seen.add(document.doc_id)
        documents.append(document)
    return documents
