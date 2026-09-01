from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class FetchedDocument:
    url: str
    body: bytes
    content_type: str
    etag: str | None = None
    last_modified: str | None = None
    not_modified: bool = False

    @property
    def text(self) -> str:
        charset = "utf-8"
        for part in self.content_type.split(";")[1:]:
            key, _, value = part.strip().partition("=")
            if key.lower() == "charset" and value:
                charset = value.strip('"')
        return self.body.decode(charset, errors="replace")


@dataclass(slots=True)
class ParsedRecord:
    external_id: str
    record_type: str
    title: str
    content: str
    summary: str | None = None
    url: str | None = None
    language: str = "tr"
    campus: str | None = None
    department: str | None = None
    degree_level: str | None = None
    audience: dict[str, Any] = field(default_factory=dict)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    published_at: datetime | None = None
    valid_until: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
