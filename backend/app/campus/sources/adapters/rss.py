"""RSS, for the one METU site that actually has a working feed.

This adapter carries a warning worth stating plainly, because it is the trap
this whole package was designed around: **every METU Drupal site answers
``/rss.xml`` with HTTP 200 and an empty feed.** ``oidb``, ``yurtlar``,
``spormd``, ``faq.cc`` and the department sites all do it — the default
front-page feed exists, nothing is promoted to it, and a feed-first design
would therefore ingest nothing at all while every health check stayed green.

So an empty feed is treated as a failure here, not as "no news this week". The
sites that genuinely use this adapter are the ones with real feeds, such as
``haber.metu.edu.tr`` (WordPress) at ``/tr/feed/``.

Config: ``{"feeds": {"tr": "/tr/feed/", "en": "/en/feed/"}}``
"""

import re
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

from app.campus.sources.adapters import AdapterContext, per_language
from app.campus.sources.htmlkit import extract_text, parse_iso8601
from app.campus.sources.models import SourceError, SourceItem

_CONTENT_NS = "{http://purl.org/rss/1.0/modules/content/}encoded"
# A feed is data from a site we do not control. ElementTree does not resolve
# external entities, but it will happily expand internally-defined ones, so a
# document type declaration is refused outright rather than parsed.
_DOCTYPE = re.compile(rb"<!(DOCTYPE|ENTITY)", re.I)


def _text(node: ElementTree.Element | None) -> str:
    return (node.text or "").strip() if node is not None else ""


def _published(item: ElementTree.Element):
    for tag in ("pubDate", "{http://purl.org/dc/elements/1.1/}date", "published", "updated"):
        raw = _text(item.find(tag))
        if not raw:
            continue
        parsed = parse_iso8601(raw)
        if parsed is not None:
            return parsed
        try:
            return parsedate_to_datetime(raw)
        except (TypeError, ValueError):
            continue
    return None


def parse_feed(raw: bytes, *, language: str = "tr") -> list[SourceItem]:
    """Feed bytes to items. Raises when the feed carries no entries."""
    if _DOCTYPE.search(raw[:4096]):
        raise SourceError("unsafe_xml", "Feed declares a DTD; refusing to parse it")
    try:
        root = ElementTree.fromstring(raw)
    except ElementTree.ParseError as exc:
        raise SourceError("bad_feed", f"Feed is not well-formed XML: {exc}") from exc

    entries = root.iterfind(".//item")
    items: list[SourceItem] = []
    for entry in entries:
        link = _text(entry.find("link"))
        title = _text(entry.find("title"))
        body_html = _text(entry.find(_CONTENT_NS)) or _text(entry.find("description"))
        body = extract_text(body_html, drop_chrome=False) if body_html else ""
        if not link and not title:
            continue
        items.append(
            SourceItem(
                external_id=link or title,
                title=title[:500],
                body=body or title,
                url=link or None,
                language=language,
                published_at=_published(entry),
            )
        )
    if not items:
        # See the module docstring: this is the METU-specific failure mode, and
        # letting it pass as success is how a source silently stops working.
        raise SourceError("empty_feed", "Feed parsed but contained no items")
    return items


async def collect(context: AdapterContext) -> list[SourceItem]:
    spec, fetcher = context.spec, context.fetcher
    feeds = spec.config.get("feeds") or {}

    async def for_language(language: str) -> list[SourceItem]:
        path = feeds.get(language)
        if not path:
            return []
        fetched = await fetcher.get(spec.absolute(path))
        return parse_feed(fetched.body, language=language)[: spec.max_items]

    return await per_language(spec, for_language)
