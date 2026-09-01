"""The value types the source pipeline passes around.

Kept free of SQLAlchemy and of ``httpx`` on purpose. Every adapter takes a
:class:`SourceSpec` and returns :class:`SourceItem`s, which means an adapter can
be exercised against a saved page with no database and no network — the same
property that makes :mod:`app.campus.mcp_config` cheap to test.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

# Adapters that exist. Kept here rather than in the adapters package so the
# admin schema can validate a submitted source without importing parsers.
ADAPTER_IDS = ("drupal_listing", "html_table", "page", "rss", "curated")

# What a source's documents are. Drives retrieval filtering and the phrasing of
# the citation the persona has to produce.
SOURCE_KINDS = ("announcement", "calendar", "faq", "news", "curated", "policy")


@dataclass(frozen=True)
class SourceSpec:
    """A source as the pipeline sees it, whether it came from a row or a seed.

    The DB row and the seeded defaults both normalise to this, so ingest never
    has to care which it is looking at.
    """

    slug: str
    name: str
    adapter: str
    kind: str
    base_url: str
    config: dict[str, Any] = field(default_factory=dict)
    encoding: str | None = None
    languages: tuple[str, ...] = ("tr",)
    departments: tuple[str, ...] = ()
    degree_levels: tuple[str, ...] = ()
    audience_rules: dict[str, str] = field(default_factory=dict)
    refresh_seconds: int = 21_600
    max_pages: int = 3
    max_items: int = 100
    priority: int = 100
    enabled: bool = True

    def absolute(self, path: str) -> str:
        """Resolve a configured path against this source's base URL."""
        if path.startswith(("http://", "https://")):
            return path
        return f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"


@dataclass(frozen=True)
class SourceItem:
    """One parsed unit of campus content, before it becomes a document.

    ``external_id`` is what makes an ingest idempotent: re-running a source must
    update the same document rather than appending a second copy, and a URL is
    the only identifier every one of these sites actually offers.
    """

    external_id: str
    title: str
    body: str
    url: str | None = None
    language: str = "tr"
    published_at: datetime | None = None
    # Adapter-specific facts worth keeping as metadata: the calendar's parsed
    # start/end dates, an academic year, a course code on a curated entry.
    extra: dict[str, Any] = field(default_factory=dict)

    def is_empty(self) -> bool:
        return not self.title.strip() and not self.body.strip()


@dataclass
class IngestStats:
    """What one ingest attempt did, for the run record and the admin UI."""

    items_seen: int = 0
    items_written: int = 0
    items_unchanged: int = 0
    requests_made: int = 0
    bytes_fetched: int = 0

    def merge_fetch(self, requests_made: int, bytes_fetched: int) -> None:
        self.requests_made += requests_made
        self.bytes_fetched += bytes_fetched


class SourceError(Exception):
    """An ingest failed in a way worth recording against the source.

    Carries a short stable ``code`` so runs can be grouped by failure mode —
    an unreachable host and an adapter that suddenly parses nothing are very
    different problems and should not look the same in the admin UI.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
