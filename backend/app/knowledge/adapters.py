"""Pure source adapters: bytes/config in, canonical records out."""

import hashlib
import io
import json
import re
from abc import ABC, abstractmethod
from calendar import timegm
from datetime import UTC, date, datetime, time
from typing import Any
from urllib.parse import urljoin

import feedparser
from bs4 import BeautifulSoup
from icalendar import Calendar
from pypdf import PdfReader

from app.knowledge.types import FetchedDocument, ParsedRecord

RECORD_TYPES = {"announcement", "calendar", "event", "service_status", "guide", "course", "policy"}


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _clean_content(value: Any) -> str:
    lines = [_clean(line) for line in str(value or "").replace("\r", "\n").split("\n")]
    return "\n".join(line for line in lines if line)


def _html_content(root) -> str:
    """Preserve semantic HTML boundaries for the downstream chunker."""
    block_tags = {"h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "pre", "blockquote", "tr"}
    lines: list[str] = []
    for node in root.select(", ".join(sorted(block_tags))):
        if node.find_parent(block_tags):
            continue
        text = _clean(node.get_text(" "))
        if not text:
            continue
        if node.name and node.name.startswith("h") and node.name[1:].isdigit():
            text = f"{'#' * int(node.name[1:])} {text}"
        if not lines or lines[-1] != text:
            lines.append(text)
    return "\n".join(lines) or _clean_content(root.get_text("\n"))


def _date(value: Any) -> datetime | None:
    text = _clean(value)
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    for candidate in (text, text.replace(" ", "T", 1)):
        try:
            parsed = datetime.fromisoformat(candidate)
            return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed
        except ValueError:
            pass
    return None


def _stable_id(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()


def _path(value: Any, dotted: str | None) -> Any:
    if not dotted:
        return value
    current = value
    for part in dotted.split("."):
        if isinstance(current, list):
            current = current[int(part)]
        elif isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


def _record(raw: dict[str, Any], defaults: dict[str, Any], source_url: str | None = None) -> ParsedRecord:
    merged = {**defaults, **{key: value for key, value in raw.items() if value is not None}}
    record_type = _clean(merged.get("record_type") or "announcement")
    if record_type not in RECORD_TYPES:
        raise ValueError(f"Unsupported record_type: {record_type}")
    title = _clean(merged.get("title"))
    content = _clean_content(merged.get("content") or merged.get("summary") or title)
    if not title or not content:
        raise ValueError("Every parsed record needs a title and content")
    url = _clean(merged.get("url")) or source_url
    if url and source_url:
        url = urljoin(source_url, url)
    external_id = _clean(merged.get("external_id")) or _stable_id(title, url or "", content[:500])
    return ParsedRecord(
        external_id=external_id,
        record_type=record_type,
        title=title,
        summary=_clean(merged.get("summary")) or None,
        content=content,
        url=url,
        language=_clean(merged.get("language") or "tr"),
        campus=_clean(merged.get("campus")) or None,
        department=_clean(merged.get("department")) or None,
        degree_level=_clean(merged.get("degree_level")) or None,
        audience=merged.get("audience") if isinstance(merged.get("audience"), dict) else {},
        starts_at=_date(merged.get("starts_at")),
        ends_at=_date(merged.get("ends_at")),
        published_at=_date(merged.get("published_at")),
        valid_until=_date(merged.get("valid_until")),
        metadata=merged.get("metadata") if isinstance(merged.get("metadata"), dict) else {},
    )


class SourceAdapter(ABC):
    @abstractmethod
    def parse(self, document: FetchedDocument | None, config: dict[str, Any]) -> list[ParsedRecord]: ...


class CuratedAdapter(SourceAdapter):
    def parse(self, document: FetchedDocument | None, config: dict[str, Any]) -> list[ParsedRecord]:
        defaults = config.get("defaults", {})
        return [_record(item, defaults) for item in config.get("records", [])]


class JsonAdapter(SourceAdapter):
    def parse(self, document: FetchedDocument | None, config: dict[str, Any]) -> list[ParsedRecord]:
        if document is None:
            return []
        payload = json.loads(document.text)
        items = _path(payload, config.get("items_path"))
        if isinstance(items, dict):
            items = [items]
        if not isinstance(items, list):
            raise ValueError("JSON items_path must resolve to a list or object")
        field_map = config.get("field_map", {})
        defaults = config.get("defaults", {})
        records = []
        for item in items:
            if not isinstance(item, dict):
                continue
            raw = {target: _path(item, source) for target, source in field_map.items()}
            records.append(_record(raw, defaults, document.url))
        return records


class HtmlPageAdapter(SourceAdapter):
    def parse(self, document: FetchedDocument | None, config: dict[str, Any]) -> list[ParsedRecord]:
        if document is None:
            return []
        soup = BeautifulSoup(document.text, "html.parser")
        for node in soup(["script", "style", "noscript", "nav", "footer"]):
            node.decompose()
        root = soup.select_one(config.get("content_selector", "main")) or soup.body or soup
        title_node = soup.select_one(config.get("title_selector", "h1"))
        raw = {
            "external_id": config.get("external_id") or document.url,
            "title": _clean(
                title_node.get_text(" ") if title_node else soup.title.string if soup.title else document.url
            ),
            "content": _html_content(root),
            "url": document.url,
        }
        return [_record(raw, config.get("defaults", {}), document.url)]


class DrupalAdapter(SourceAdapter):
    def parse(self, document: FetchedDocument | None, config: dict[str, Any]) -> list[ParsedRecord]:
        if document is None:
            return []
        soup = BeautifulSoup(document.text, "html.parser")
        selector = config.get("item_selector", "article, .views-row")
        nodes = soup.select(selector)
        if not nodes:
            return HtmlPageAdapter().parse(document, config)
        defaults = config.get("defaults", {})
        result = []
        for node in nodes:
            title_node = node.select_one(config.get("title_selector", "h1, h2, h3, .field--name-title"))
            link = title_node.find("a") if title_node else node.find("a")
            time_node = node.select_one(config.get("date_selector", "time, .date-display-single"))
            title = _clean(title_node.get_text(" ") if title_node else "")
            if not title:
                continue
            href = link.get("href") if link else None
            result.append(
                _record(
                    {
                        "external_id": node.get("data-history-node-id") or href,
                        "title": title,
                        "content": _html_content(node),
                        "url": href,
                        "published_at": (
                            time_node.get("datetime") if time_node and time_node.has_attr("datetime") else None
                        ),
                    },
                    defaults,
                    document.url,
                )
            )
        return result


class HtmlTableAdapter(SourceAdapter):
    def parse(self, document: FetchedDocument | None, config: dict[str, Any]) -> list[ParsedRecord]:
        if document is None:
            return []
        soup = BeautifulSoup(document.text, "html.parser")
        table = soup.select_one(config.get("table_selector", "table"))
        if table is None:
            raise ValueError("Configured table was not found")
        rows = table.select("tr")
        headers = [_clean(cell.get_text(" ")).lower() for cell in rows[0].select("th,td")] if rows else []
        defaults = config.get("defaults", {})
        field_map = config.get("field_map", {})
        records = []
        for row in rows[1:]:
            cells = [_clean(cell.get_text(" ")) for cell in row.select("th,td")]
            values = dict(zip(headers, cells, strict=False))
            raw = {target: values.get(source.lower()) for target, source in field_map.items()}
            if not raw.get("content"):
                raw["content"] = " · ".join(cells)
            records.append(_record(raw, defaults, document.url))
        return records


class FeedAdapter(SourceAdapter):
    def parse(self, document: FetchedDocument | None, config: dict[str, Any]) -> list[ParsedRecord]:
        if document is None:
            return []
        feed = feedparser.parse(document.body)
        if feed.bozo and not feed.entries:
            raise ValueError(f"Invalid RSS/Atom feed: {feed.bozo_exception}")
        defaults = config.get("defaults", {})
        result = []
        for item in feed.entries:
            content = item.get("content") or []
            content_value = content[0].get("value") if content and isinstance(content[0], dict) else None
            published = item.get("published_parsed") or item.get("updated_parsed")
            published_at = datetime.fromtimestamp(timegm(published), tz=UTC).isoformat() if published else None
            link = _clean(item.get("link"))
            result.append(
                _record(
                    {
                        "external_id": _clean(item.get("id")) or link,
                        "title": item.get("title"),
                        "content": content_value or item.get("summary") or item.get("description"),
                        "summary": item.get("summary") or item.get("description"),
                        "url": link,
                        "published_at": published_at,
                    },
                    defaults,
                    document.url,
                )
            )
        return result


def _ical_datetime(value: Any) -> str | None:
    if isinstance(value, datetime):
        return (value.replace(tzinfo=UTC) if value.tzinfo is None else value).isoformat()
    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=UTC).isoformat()
    return _clean(value) or None


class IcalAdapter(SourceAdapter):
    def parse(self, document: FetchedDocument | None, config: dict[str, Any]) -> list[ParsedRecord]:
        if document is None:
            return []
        defaults = {"record_type": "calendar", **config.get("defaults", {})}
        result = []
        calendar = Calendar.from_ical(document.body)
        for event in calendar.walk("VEVENT"):
            summary = _clean(event.get("summary"))
            description = _clean(event.get("description"))
            result.append(
                _record(
                    {
                        "external_id": _clean(event.get("uid")),
                        "title": summary,
                        "content": description or summary,
                        "url": _clean(event.get("url")),
                        "starts_at": _ical_datetime(event.decoded("dtstart", None)),
                        "ends_at": _ical_datetime(event.decoded("dtend", None)),
                    },
                    defaults,
                    document.url,
                )
            )
        return result


class PdfAdapter(SourceAdapter):
    def parse(self, document: FetchedDocument | None, config: dict[str, Any]) -> list[ParsedRecord]:
        if document is None:
            return []
        reader = PdfReader(io.BytesIO(document.body))
        parent_id = config.get("external_id") or document.url
        title = config.get("title") or document.url.rsplit("/", 1)[-1]
        defaults = config.get("defaults", {})
        records = []
        page_count = len(reader.pages)
        for page_number, page in enumerate(reader.pages, start=1):
            content = _clean_content(page.extract_text() or "")
            if not content:
                continue
            metadata = {
                **(defaults.get("metadata") if isinstance(defaults.get("metadata"), dict) else {}),
                "document_external_id": parent_id,
                "page_number": page_number,
                "page_count": page_count,
            }
            records.append(
                _record(
                    {
                        "external_id": f"{parent_id}::page:{page_number:04d}",
                        "title": title,
                        "content": content,
                        "url": document.url,
                        "metadata": metadata,
                    },
                    defaults,
                    document.url,
                )
            )
        return records


ADAPTERS: dict[str, SourceAdapter] = {
    "curated": CuratedAdapter(),
    "email_facts": CuratedAdapter(),
    "json": JsonAdapter(),
    "approved_social": JsonAdapter(),
    "html_page": HtmlPageAdapter(),
    "drupal": DrupalAdapter(),
    "html_table": HtmlTableAdapter(),
    "rss": FeedAdapter(),
    "ical": IcalAdapter(),
    "pdf": PdfAdapter(),
}


def adapter_for(kind: str) -> SourceAdapter:
    try:
        return ADAPTERS[kind]
    except KeyError as exc:
        raise ValueError(f"Unsupported source adapter: {kind}") from exc
