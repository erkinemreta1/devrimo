"""Parsers, selected by a source row rather than chosen in code.

An adapter turns one configured source into :class:`SourceItem`s. Adding a
campus site is a row in ``campus_sources`` naming one of these; adding a *kind*
of site is a module here plus one line in :data:`ADAPTERS`, and nothing else in
the service changes.

Each adapter is split in two on purpose. The parsing is pure functions of markup
and config, tested against saved pages with no network at all — the property
that makes :mod:`app.campus.mcp_config` cheap to test. The walking is a thin
``collect`` that drives an injected fetcher, so it can be exercised against a
dictionary of canned pages.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.campus.sources.fetch import FetchedPage
from app.campus.sources.models import SourceItem, SourceSpec


class Fetcher(Protocol):
    """What an adapter is allowed to do to the network.

    Narrow on purpose: an adapter that could open its own client would bypass
    the allowlist, the crawl delay, and the byte cap in one line.
    """

    async def get(self, url: str, *, etag: str | None = None, last_modified: str | None = None) -> FetchedPage: ...


@dataclass
class AdapterContext:
    """Everything an adapter is given. ``db`` is set only for ``curated``."""

    spec: SourceSpec
    fetcher: Fetcher
    db: AsyncSession | None = None


Adapter = Callable[[AdapterContext], Awaitable[list[SourceItem]]]


async def per_language(spec: SourceSpec, run) -> list[SourceItem]:
    """Run ``run(language)`` for each configured language, tolerating one failing.

    METU's bilingual sites are not reliably bilingual. A unit publishes the
    Turkish page and not the English one, or renames only one of them, and the
    other 404s. Failing the whole source there would throw away 153 correctly
    parsed calendar rows because a translation is missing — so a language that
    fails is recorded and skipped, and only *every* language failing is a
    failure. It is the same judgement :mod:`app.agents.toolset` makes when one
    campus server is down.
    """
    from app.campus.sources.models import SourceError
    from app.logging import get_logger

    logger = get_logger(__name__)
    items: list[SourceItem] = []
    failures: list[tuple[str, SourceError]] = []
    for language in spec.languages:
        try:
            items.extend(await run(language))
        except SourceError as exc:
            failures.append((language, exc))

    if failures and not items:
        raise failures[0][1]
    for language, exc in failures:
        logger.warning("campus_source_language_skipped", source=spec.slug, language=language, error=exc.message)
    return items


def get_adapter(name: str) -> Adapter:
    """Resolve an adapter by name, raising the pipeline's own error type.

    Imported lazily so that a bad ``adapter`` value on one source row fails that
    source's run instead of the module import that every source depends on.
    """
    from app.campus.sources.models import SourceError

    adapter = ADAPTERS.get(name)
    if adapter is None:
        raise SourceError("unknown_adapter", f"No adapter named {name!r}")
    return adapter


def _load() -> dict[str, Adapter]:
    from app.campus.sources.adapters.curated import collect as curated
    from app.campus.sources.adapters.drupal_listing import collect as drupal_listing
    from app.campus.sources.adapters.html_table import collect as html_table
    from app.campus.sources.adapters.page import collect as page
    from app.campus.sources.adapters.rss import collect as rss

    return {
        "drupal_listing": drupal_listing,
        "html_table": html_table,
        "page": page,
        "rss": rss,
        "curated": curated,
    }


ADAPTERS: dict[str, Adapter] = _load()

__all__ = ["ADAPTERS", "Adapter", "AdapterContext", "Fetcher", "SourceItem", "SourceSpec", "get_adapter"]
