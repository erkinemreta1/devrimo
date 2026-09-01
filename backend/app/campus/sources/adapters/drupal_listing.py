"""Announcement listings on METU's Drupal sites, of which there are two shapes.

Most METU units run Drupal 10 on the shared "miys" theme — oidb, yurtlar,
spormd, kim, ceng, math, psy — with announcements at ``/{lang}/announcements``,
``?page=N`` pagination, and a node page carrying
``<time datetime="…" class="datetime">``. That is *not* a rule. ``ie.metu.edu.tr``
is Drupal 7, lists at ``/en/tum-duyurular``, and puts its nodes under
``/en/announcement/{slug}`` — singular. Even on one host the listing alias and
the node alias disagree: ``yurtlar`` lists at ``/tr/announcements`` while its
nodes live at ``/tr/duyurular/…``.

So nothing here is inferred from the host. The listing paths, the pattern that
recognises an item link, and the pagination parameter are all configuration:

```json
{
  "listings": {"tr": "/tr/announcements", "en": "/en/announcements"},
  "item_pattern": "^/(tr|en)/(duyurular|announcements)/[^/]+$",
  "page_param": "page",
  "listing_region": {"tag": "main"},
  "node_region": {"tag": "main"},
  "fetch_nodes": true
}
```

``fetch_nodes: false`` covers the sites whose listing already carries the whole
teaser and whose node pages would double the request count for nothing.
"""

import re
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo

from app.campus.sources.adapters import AdapterContext, per_language
from app.campus.sources.htmlkit import Region, decode, extract_links, extract_text, first_datetime, page_title
from app.campus.sources.models import SourceError, SourceItem, SourceSpec

ISTANBUL = ZoneInfo("Europe/Istanbul")

# ``dd/mm/yyyy`` as the Drupal views listing renders it. Only consulted when the
# node page offers no <time> element, which is the Drupal 7 case.
_LISTING_DATE = re.compile(r"\b(\d{2})/(\d{2})/(\d{4})\b")


def _better_title(current: str, candidate: str) -> bool:
    """Whether ``candidate`` is a better headline than what we already have.

    A Drupal teaser links the same node up to four times: an image with no text,
    the headline, the ``dd/mm/yyyy`` date, and a "read more" wrapping the whole
    teaser body. Simply taking the shortest non-empty text picks the *date* —
    which is how every spormd announcement ends up titled "21/07/2026". So
    pure-date link text is discarded outright, and among what is left the
    shortest wins, which is the headline rather than the teaser paragraph.
    """
    candidate = candidate.strip()
    if not candidate or _LISTING_DATE.fullmatch(candidate):
        return False
    if not current or _LISTING_DATE.fullmatch(current):
        return True
    return len(candidate) < len(current)


@dataclass(frozen=True)
class ListingEntry:
    """One announcement as the listing page describes it."""

    url: str
    title: str
    published_at: datetime | None = None


def parse_listing(markup: str, base_url: str, config: dict) -> list[ListingEntry]:
    """Item links on one listing page.

    The date is taken from the listing rather than only from the node because
    Drupal 7 sites — ``ie.metu.edu.tr``, ``faq.cc.metu.edu.tr`` — render no
    ``<time>`` element at all. Their teaser's ``dd/mm/yyyy`` is the only
    publication date on offer, and without it every one of their documents
    would be undated and unsortable.
    """
    pattern = re.compile(config.get("item_pattern", r"/(duyurular|announcements)/"))
    region = Region.from_config(config.get("listing_region"))
    titles: dict[str, str] = {}
    dates: dict[str, datetime | None] = {}
    order: list[str] = []
    for href, text in extract_links(markup, region=region):
        if not href or href.startswith(("#", "mailto:", "javascript:")):
            continue
        path = urlparse(href).path
        if not pattern.search(path):
            continue
        absolute = urljoin(base_url, href)
        if absolute not in titles:
            order.append(absolute)
            titles[absolute] = ""
            dates[absolute] = None
        if _better_title(titles[absolute], text):
            titles[absolute] = text.strip()
        if dates[absolute] is None:
            dates[absolute] = listing_date(text)
    return [ListingEntry(url=url, title=titles[url], published_at=dates[url]) for url in order]


def parse_node(
    markup: str,
    url: str,
    config: dict,
    *,
    fallback_title: str = "",
    fallback_date: datetime | None = None,
    language: str = "tr",
) -> SourceItem:
    """One announcement page as an item."""
    region = Region.from_config(config.get("node_region") or {"tag": "main"})
    body = extract_text(markup, region=region)
    if not body:
        # A theme with no <main> would otherwise yield an empty document that
        # still costs an embedding.
        body = extract_text(markup)
    title = fallback_title.strip() or page_title(markup, region=region)
    return SourceItem(
        external_id=url,
        title=title[:500],
        body=body,
        url=url,
        language=language,
        published_at=first_datetime(markup) or fallback_date,
        extra={"path": urlparse(url).path},
    )


def listing_date(text: str) -> datetime | None:
    """The ``dd/mm/yyyy`` a Drupal listing prints next to a teaser."""
    match = _LISTING_DATE.search(text or "")
    if not match:
        return None
    day, month, year = (int(part) for part in match.groups())
    try:
        return datetime(year, month, day, tzinfo=ISTANBUL)
    except ValueError:
        return None


def _page_url(spec: SourceSpec, path: str, index: int, config: dict) -> str:
    base = spec.absolute(path)
    if index == 0:
        return base
    param = config.get("page_param", "page")
    separator = "&" if "?" in base else "?"
    return f"{base}{separator}{param}={index}"


async def collect(context: AdapterContext) -> list[SourceItem]:
    spec, fetcher = context.spec, context.fetcher
    config = spec.config
    listings: dict[str, str] = config.get("listings") or {}
    fetch_nodes = config.get("fetch_nodes", True)
    seen: set[str] = set()

    async def for_language(language: str) -> list[SourceItem]:
        path = listings.get(language)
        if not path:
            return []
        collected: list[SourceItem] = []
        for index in range(max(1, spec.max_pages)):
            url = _page_url(spec, path, index, config)
            try:
                page = await fetcher.get(url)
            except SourceError:
                # Past the last page some sites 404 rather than returning an
                # empty view. That is the end of the listing, not a broken
                # source — but on page 0 it really is broken, so it propagates.
                if index == 0:
                    raise
                break
            markup = decode(page.body, declared=page.declared_charset, override=spec.encoding)
            found = parse_listing(markup, page.url, config)
            if not found:
                # An empty page means the pagination ran out, which is normal;
                # an empty *first* page is a parse failure and the ingest layer
                # reports it as one.
                break
            for entry in found:
                # ``seen`` is the item cap as well as the cross-language
                # dedupe: every accepted entry lands in it exactly once, so it
                # counts distinct items rather than double-counting them.
                if entry.url in seen or len(seen) >= spec.max_items:
                    continue
                seen.add(entry.url)
                if not fetch_nodes:
                    collected.append(
                        SourceItem(
                            external_id=entry.url,
                            title=entry.title[:500],
                            body=entry.title,
                            url=entry.url,
                            language=language,
                            published_at=entry.published_at,
                            extra={"from_listing": True},
                        )
                    )
                    continue
                try:
                    node = await fetcher.get(entry.url)
                except SourceError:
                    # One announcement that has been unpublished since the
                    # listing was rendered must not cost the other ninety.
                    continue
                collected.append(
                    parse_node(
                        decode(node.body, declared=node.declared_charset, override=spec.encoding),
                        node.url,
                        config,
                        fallback_title=entry.title,
                        fallback_date=entry.published_at,
                        language=language,
                    )
                )
            if len(seen) >= spec.max_items:
                break
        return collected

    return await per_language(spec, for_language)
