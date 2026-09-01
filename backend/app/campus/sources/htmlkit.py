"""Small HTML helpers for the campus adapters, on the standard library only.

Every page this package reads is server-rendered by Drupal 7, Drupal 10,
WordPress, or a PHP script from 2013. None of it needs a browser, a CSS engine,
or a DOM — it needs "the links under this element", "the rows of this table",
and "the readable text of this article". ``html.parser`` is a real tokenizer and
gives all three, so this module exists instead of a parsing dependency the
project would then have to pin and keep current.

Regions are expressed as tag plus optional id/class rather than as CSS
selectors. That is enough for these sites (``<main>``, ``#mcontent2``,
``.view-content``) and it keeps the configuration an admin types into the source
form small enough to get right.
"""

import re
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser

# Content in these never belongs in an extracted document body.
_INVISIBLE_TAGS = frozenset({"script", "style", "noscript", "template", "svg"})
# Chrome that repeats on every page of a Drupal site. Dropping it stops each
# document from carrying the same 200-line navigation menu into the embedder,
# which would otherwise make every page on a site look alike.
_CHROME_TAGS = frozenset({"nav", "header", "footer", "form"})
_BLOCK_TAGS = frozenset(
    {
        "p",
        "div",
        "section",
        "article",
        "main",
        "aside",
        "li",
        "ul",
        "ol",
        "dl",
        "dt",
        "dd",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "tr",
        "table",
        "thead",
        "tbody",
        "blockquote",
        "figure",
        "figcaption",
        "pre",
        "address",
    }
)
_CELL_TAGS = frozenset({"td", "th"})
# Void elements never get an end tag, so counting them as depth would leave the
# parser permanently convinced it is inside an element that already closed.
_VOID_TAGS = frozenset(
    {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
)


@dataclass(frozen=True)
class Region:
    """Where in a document to look. ``tag=None`` means the whole document."""

    tag: str | None = None
    attr: str | None = None  # "id" or "class"
    value: str | None = None

    @classmethod
    def from_config(cls, raw: dict | None) -> "Region":
        if not raw:
            return cls()
        return cls(tag=raw.get("tag"), attr=raw.get("attr"), value=raw.get("value"))

    def matches(self, tag: str, attrs: dict[str, str]) -> bool:
        if self.tag and tag != self.tag:
            return False
        if not self.attr or not self.value:
            return bool(self.tag)
        actual = attrs.get(self.attr, "")
        if self.attr == "class":
            return self.value in actual.split()
        return actual == self.value


def _attrs_to_dict(attrs: list[tuple[str, str | None]]) -> dict[str, str]:
    return {key.lower(): (value or "") for key, value in attrs}


class _RegionAware(HTMLParser):
    """Base parser that knows whether it is currently inside the target region.

    Void elements never open a region, and unbalanced markup is survived by
    tracking depth rather than a stack of names: these pages predate anyone
    validating them, and a stray unclosed ``<div>`` must not silently truncate
    a document to nothing.
    """

    def __init__(self, region: Region | None = None) -> None:
        super().__init__(convert_charrefs=True)
        self._region = region or Region()
        self._region_depth: int | None = None
        self._region_open = False
        self._region_seen = False
        self._depth = 0
        self._skip_depth: int | None = None
        self._skip_tags: frozenset[str] = _INVISIBLE_TAGS

    @property
    def in_region(self) -> bool:
        if self._region.tag is None:
            return True
        return self._region_open

    @property
    def skipping(self) -> bool:
        return self._skip_depth is not None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        as_dict = _attrs_to_dict(attrs)
        if tag in _VOID_TAGS:
            self.on_start(tag, as_dict)
            return
        self._depth += 1
        if self._skip_depth is None and tag in self._skip_tags:
            self._skip_depth = self._depth
        if not self._region_seen and self._region.tag and self._region.matches(tag, as_dict):
            self._region_seen = True
            self._region_open = True
            self._region_depth = self._depth
        self.on_start(tag, as_dict)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.on_start(tag.lower(), _attrs_to_dict(attrs))
        self.on_end(tag.lower())

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in _VOID_TAGS:
            return
        self.on_end(tag)
        if self._skip_depth is not None and self._depth <= self._skip_depth:
            self._skip_depth = None
        if self._region_open and self._region_depth is not None and self._depth <= self._region_depth:
            # The region closed. It is never reopened: a second element with the
            # same id would otherwise append trailing page chrome to what was
            # supposed to be one article.
            self._region_open = False
        self._depth = max(0, self._depth - 1)

    # Subclass hooks — no-ops so a subclass only overrides what it needs.
    def on_start(self, tag: str, attrs: dict[str, str]) -> None: ...

    def on_end(self, tag: str) -> None: ...


class _TextExtractor(_RegionAware):
    def __init__(self, region: Region | None = None, *, drop_chrome: bool = True) -> None:
        super().__init__(region)
        self._skip_tags = _INVISIBLE_TAGS | _CHROME_TAGS if drop_chrome else _INVISIBLE_TAGS
        self.parts: list[str] = []

    def on_start(self, tag: str, attrs: dict[str, str]) -> None:
        if not self.in_region or self.skipping:
            return
        if tag == "br" or tag in _BLOCK_TAGS:
            self.parts.append("\n")
        elif tag in _CELL_TAGS:
            self.parts.append("\t")

    def on_end(self, tag: str) -> None:
        if self.in_region and not self.skipping and tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self.in_region and not self.skipping:
            self.parts.append(data)


class _LinkExtractor(_RegionAware):
    def __init__(self, region: Region | None = None) -> None:
        super().__init__(region)
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def on_start(self, tag: str, attrs: dict[str, str]) -> None:
        if tag == "a" and self.in_region and not self.skipping:
            self._href = attrs.get("href")
            self._text = []

    def on_end(self, tag: str) -> None:
        if tag == "a" and self._href is not None:
            self.links.append((self._href, re.sub(r"\s+", " ", "".join(self._text)).strip()))
            self._href = None
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)


class _TableExtractor(_RegionAware):
    """Tables as ``[[cell, cell], ...]``, cell text flattened.

    Cells keep their newlines: the academic calendar packs a date range and a
    multi-line description into two cells, and collapsing the description to one
    line loses the bullet structure that says which students a row applies to.
    """

    def __init__(self, region: Region | None = None) -> None:
        super().__init__(region)
        self.tables: list[list[list[str]]] = []
        self._table: list[list[str]] | None = None
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def on_start(self, tag: str, attrs: dict[str, str]) -> None:
        if not self.in_region or self.skipping:
            return
        if tag == "table":
            self._table = []
        elif tag == "tr" and self._table is not None:
            self._row = []
        elif tag in _CELL_TAGS and self._row is not None:
            self._cell = []
        elif tag == "br" and self._cell is not None:
            self._cell.append("\n")

    def on_end(self, tag: str) -> None:
        if tag in _CELL_TAGS and self._cell is not None and self._row is not None:
            self._row.append(_tidy("".join(self._cell)))
            self._cell = None
        elif tag == "tr" and self._row is not None and self._table is not None:
            if any(cell for cell in self._row):
                self._table.append(self._row)
            self._row = None
        elif tag == "table" and self._table is not None:
            self.tables.append(self._table)
            self._table = None

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)


class _AttributeCollector(HTMLParser):
    def __init__(self, tag: str, attr: str) -> None:
        super().__init__(convert_charrefs=True)
        self.tag = tag
        self.attr = attr
        self.values: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == self.tag:
            value = _attrs_to_dict(attrs).get(self.attr)
            if value:
                self.values.append(value)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)


def _tidy(text: str) -> str:
    """Collapse runs of whitespace but keep paragraph structure."""
    text = text.replace("\xa0", " ").replace("​", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def decode(raw: bytes, *, declared: str | None = None, override: str | None = None) -> str:
    """Bytes to text: explicit override, then strict UTF-8, then the declaration.

    The order matters and is not the obvious one. ``catalog.metu.edu.tr``
    declares ``<meta charset="iso8859-9">`` and then serves UTF-8 anyway — a
    legacy page whose declaration is simply wrong. Trusting a declaration first
    cannot recover from that, because single-byte codecs decode *any* byte
    sequence successfully: ISO-8859-9 never raises, it just silently turns
    ``Türkçe`` into ``TÃ¼rkÃ§e`` and stores the mojibake in the corpus.

    Strict UTF-8 first is the reliable discriminator instead. Genuine
    ISO-8859-9 Turkish text is almost never valid UTF-8 — the accented
    characters are lone high bytes — so a strict decode that *succeeds* is
    strong evidence the bytes really are UTF-8, and one that fails falls
    through to the declared charset. ``override`` still wins outright, because
    it is the admin's escape hatch for whatever this heuristic gets wrong.
    """
    for candidate in (override, "utf-8", declared):
        if not candidate:
            continue
        try:
            return raw.decode(candidate)
        except (LookupError, UnicodeDecodeError):
            continue
    return raw.decode("utf-8", errors="replace")


def charset_from_meta(raw: bytes) -> str | None:
    """The charset a page declares in its own markup, if any."""
    head = raw[:4096].decode("ascii", errors="ignore")
    match = re.search(r'<meta[^>]+charset=["\']?\s*([\w-]+)', head, re.I)
    return match.group(1) if match else None


def extract_text(markup: str, *, region: Region | None = None, drop_chrome: bool = True) -> str:
    parser = _TextExtractor(region, drop_chrome=drop_chrome)
    parser.feed(markup)
    parser.close()
    return _tidy("".join(parser.parts))


def extract_links(markup: str, *, region: Region | None = None) -> list[tuple[str, str]]:
    parser = _LinkExtractor(region)
    parser.feed(markup)
    parser.close()
    return parser.links


def extract_tables(markup: str, *, region: Region | None = None) -> list[list[list[str]]]:
    parser = _TableExtractor(region)
    parser.feed(markup)
    parser.close()
    return parser.tables


def extract_attributes(markup: str, tag: str, attr: str) -> list[str]:
    parser = _AttributeCollector(tag.lower(), attr.lower())
    parser.feed(markup)
    parser.close()
    return parser.values


def first_datetime(markup: str) -> datetime | None:
    """The first ``<time datetime="...">`` on the page.

    Every METU Drupal 10 node renders its date this way
    (``<time datetime="2026-07-13T12:05:10+03:00" class="datetime">``), which is
    the only machine-readable publication date these sites offer.
    """
    for raw in extract_attributes(markup, "time", "datetime"):
        parsed = parse_iso8601(raw)
        if parsed is not None:
            return parsed
    return None


def parse_iso8601(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


class _HeadingExtractor(_RegionAware):
    def __init__(self, region: Region | None = None, *, level: str = "h1") -> None:
        super().__init__(region)
        self._level = level
        self.headings: list[str] = []
        self._buffer: list[str] | None = None

    def on_start(self, tag: str, attrs: dict[str, str]) -> None:
        if tag == self._level and self.in_region and not self.skipping:
            self._buffer = []

    def on_end(self, tag: str) -> None:
        if tag == self._level and self._buffer is not None:
            text = _tidy("".join(self._buffer))
            if text:
                self.headings.append(text)
            self._buffer = None

    def handle_data(self, data: str) -> None:
        if self._buffer is not None:
            self._buffer.append(data)


def headings(markup: str, *, region: Region | None = None, level: str = "h1") -> list[str]:
    parser = _HeadingExtractor(region, level=level)
    parser.feed(markup)
    parser.close()
    return parser.headings


def page_title(markup: str, *, region: Region | None = None) -> str:
    """The document's own title, preferring a heading inside the content region.

    Searching the whole page for the first ``<h1>`` is wrong on more than one
    METU site. ``faq.cc.metu.edu.tr`` renders the site name as the first
    ``<h1>`` and the article's real question ("meturoam ağına nasıl
    bağlanabilirim?") as the second, and its ``<title>`` is the site name too —
    so a page-wide search labels all 405 FAQ articles identically, and the
    corpus becomes unsearchable by title. Scoping to the configured region
    picks the article's own heading.
    """
    if region is not None and region.tag:
        scoped = headings(markup, region=region)
        if scoped:
            return scoped[0]
    for candidate in headings(markup):
        return candidate
    match = re.search(r"<title[^>]*>(.*?)</title>", markup, re.S | re.I)
    return extract_text(match.group(1), drop_chrome=False) if match else ""
