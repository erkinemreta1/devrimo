from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.campus.sources.models import ADAPTER_IDS, SOURCE_KINDS
from app.db.models import AdminRole


class ReasonIn(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)


class DeleteUserIn(ReasonIn):
    confirm_email: str = Field(min_length=3, max_length=320)


class InviteIn(BaseModel):
    email: str = Field(min_length=3, max_length=320)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        value = value.strip().lower()
        if "@" not in value:
            raise ValueError("A valid email is required")
        return value


class AgentActionIn(BaseModel):
    action: Literal["start", "stop", "restart", "destroy"]
    reason: str = Field(min_length=3, max_length=1000)


class MembershipIn(BaseModel):
    user_id: UUID
    role: AdminRole
    organization_id: UUID | None = None
    reason: str = Field(min_length=3, max_length=1000)


class RuntimeSettingsIn(BaseModel):
    model_id: str = Field(min_length=2, max_length=255)
    profile: Literal["scholar", "legacy"]
    max_tokens: int = Field(ge=256, le=131072)
    legacy_history_runs: int = Field(ge=0, le=50)
    scholar_history_runs: int = Field(ge=0, le=50)
    tool_call_limit: int = Field(ge=1, le=50)
    learning_enabled: bool
    input_token_price: float = Field(ge=0, le=1)
    output_token_price: float = Field(ge=0, le=1)
    knowledge_enabled: bool = True
    knowledge_max_results: int = Field(default=8, ge=1, le=50)
    reason: str = Field(min_length=3, max_length=1000)


class CampusSourceIn(BaseModel):
    """A campus source as an admin submits it.

    Validation stays deliberately shallow on ``config``: its shape belongs to
    the adapter, and a schema here would have to be updated every time an
    adapter grows an option — which is exactly the coupling this design exists
    to avoid. What an admin gets instead is ``POST /admin/sources/preview``,
    which answers the real question ("does this parse?") rather than the
    shallow one ("are the keys spelled right?").
    """

    slug: str = Field(min_length=2, max_length=64, pattern=r"^[a-z0-9][a-z0-9-]*$")
    name: str = Field(min_length=2, max_length=255)
    adapter: str
    kind: str
    base_url: str = Field(min_length=8, max_length=500)
    config: dict[str, Any] = Field(default_factory=dict)
    encoding: str | None = Field(default=None, max_length=32)
    languages: list[str] = Field(default_factory=lambda: ["tr"])
    departments: list[str] = Field(default_factory=list)
    degree_levels: list[str] = Field(default_factory=list)
    audience_rules: dict[str, str] = Field(default_factory=dict)
    # Sixty seconds is the floor the table's check constraint enforces too: a
    # source that re-crawls faster than that is a denial of service against a
    # university web team, delivered from our IP.
    refresh_seconds: int = Field(default=21_600, ge=60, le=2_592_000)
    max_pages: int = Field(default=3, ge=1, le=50)
    max_items: int = Field(default=100, ge=1, le=1000)
    priority: int = Field(default=100, ge=0, le=1000)
    enabled: bool = True
    reason: str = Field(min_length=3, max_length=1000)

    @field_validator("adapter")
    @classmethod
    def _known_adapter(cls, value: str) -> str:
        if value not in ADAPTER_IDS:
            raise ValueError(f"Unknown adapter; expected one of {', '.join(ADAPTER_IDS)}")
        return value

    @field_validator("kind")
    @classmethod
    def _known_kind(cls, value: str) -> str:
        if value not in SOURCE_KINDS:
            raise ValueError(f"Unknown kind; expected one of {', '.join(SOURCE_KINDS)}")
        return value

    @field_validator("base_url")
    @classmethod
    def _http_url(cls, value: str) -> str:
        if not value.startswith(("http://", "https://")):
            raise ValueError("base_url must be an http(s) URL")
        return value.rstrip("/")

    @field_validator("languages")
    @classmethod
    def _known_languages(cls, value: list[str]) -> list[str]:
        languages = [item.strip().lower() for item in value if item.strip().lower() in ("tr", "en")]
        return languages or ["tr"]

    @field_validator("departments")
    @classmethod
    def _upper_departments(cls, value: list[str]) -> list[str]:
        return sorted({item.strip().upper() for item in value if item.strip()})


class CampusSourcePreviewIn(CampusSourceIn):
    """Same shape, but a dry run needs no slug uniqueness and no reason."""

    slug: str = Field(default="preview", min_length=2, max_length=64)
    reason: str = Field(default="preview", min_length=3, max_length=1000)
    limit: int = Field(default=10, ge=1, le=50)


class CuratedEntryIn(BaseModel):
    kind: Literal["whatsapp_group", "club", "event", "note"]
    entry_key: str | None = Field(default=None, max_length=128)
    title: str = Field(min_length=2, max_length=500)
    body: str = Field(default="", max_length=20_000)
    url: str | None = Field(default=None, max_length=1000)
    language: Literal["tr", "en"] = "tr"
    departments: list[str] = Field(default_factory=list)
    degree_levels: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    enabled: bool = True
    reason: str = Field(min_length=3, max_length=1000)

    @field_validator("entry_key")
    @classmethod
    def _normalize_key(cls, value: str | None) -> str | None:
        # Course codes are the common key and students type them every way
        # imaginable ("ceng 315", "Ceng315"), so they are normalised on the way
        # in rather than matched loosely on the way out.
        return "".join(value.split()).upper() if value and value.strip() else None

    @field_validator("url")
    @classmethod
    def _safe_url(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        value = value.strip()
        if not value.startswith(("https://", "http://")):
            raise ValueError("url must be an http(s) URL")
        return value


class GradePolicyIn(BaseModel):
    scale: dict[str, float]
    non_graded: list[str] = Field(default_factory=list)
    passing_grades: list[str] = Field(default_factory=list)
    weight_basis: Literal["credit", "ects"] = "credit"
    retake_replaces: bool = True
    max_credits_per_semester: int = Field(default=40, ge=1, le=100)
    notes: str | None = Field(default=None, max_length=2000)
    reason: str = Field(min_length=3, max_length=1000)

    @field_validator("scale")
    @classmethod
    def _sane_scale(cls, value: dict[str, float]) -> dict[str, float]:
        if not value:
            raise ValueError("The grade scale cannot be empty")
        cleaned = {}
        for letter, points in value.items():
            letter = letter.strip().upper()
            if not letter:
                raise ValueError("Grade letters cannot be blank")
            if not 0 <= float(points) <= 10:
                raise ValueError(f"Points for {letter} are outside the plausible 0-10 range")
            cleaned[letter] = float(points)
        return cleaned
