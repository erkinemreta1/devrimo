import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class AgentStatus(enum.StrEnum):
    provisioning = "provisioning"
    running = "running"
    stopped = "stopped"
    error = "error"
    destroying = "destroying"


class AccountStatus(enum.StrEnum):
    active = "active"
    suspended = "suspended"
    deletion_pending = "deletion_pending"
    deleted = "deleted"


class AdminRole(enum.StrEnum):
    super_admin = "super_admin"
    operator = "operator"
    campus_admin = "campus_admin"


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AccountDirectory(Base):
    __tablename__ = "account_directory"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'suspended', 'deletion_pending', 'deleted')",
            name="ck_account_directory_status",
        ),
        Index("ix_account_directory_org_status_created", "organization_id", "status", "created_at", "user_id"),
        Index("ix_account_directory_org_last_seen", "organization_id", "last_seen_at", "user_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    email_normalized: Mapped[str | None] = mapped_column(String(320), nullable=True, index=True)
    status: Mapped[AccountStatus] = mapped_column(
        Enum(AccountStatus, native_enum=False, length=32), default=AccountStatus.active, nullable=False
    )
    auth_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    suspended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    suspended_reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class AdminMembership(Base):
    __tablename__ = "admin_memberships"
    __table_args__ = (
        CheckConstraint(
            "role IN ('super_admin', 'operator', 'campus_admin')",
            name="ck_admin_memberships_role",
        ),
        Index("ix_admin_memberships_org_role", "organization_id", "role", "user_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id"), nullable=True)
    role: Mapped[AdminRole] = mapped_column(Enum(AdminRole, native_enum=False, length=32), nullable=False)
    granted_by: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class AdminAuditEvent(Base):
    __tablename__ = "admin_audit_events"
    __table_args__ = (
        Index("ix_admin_audit_created_id", "created_at", "id"),
        Index("ix_admin_audit_org_created", "organization_id", "created_at", "id"),
        Index("ix_admin_audit_target_created", "target_user_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    actor_user_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    target_user_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    result: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    before_state: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after_state: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AgentRuntimeSettings(Base):
    __tablename__ = "agent_runtime_settings"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default="default")
    model_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    profile: Mapped[str | None] = mapped_column(String(32), nullable=True)
    max_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    legacy_history_runs: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scholar_history_runs: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tool_call_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    learning_enabled: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    # Per single token, not per million — matches the PostHog $ai_*_token_price
    # properties these feed directly.
    input_token_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    output_token_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Campus knowledge knobs live on this row rather than one of their own so
    # that a single ``revision`` still invalidates every resident agent: the
    # corpus is attached at Agent construction time, exactly like the model is.
    knowledge_enabled: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    knowledge_max_results: Mapped[int | None] = mapped_column(Integer, nullable=True)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Agent(Base):
    """A user's entitlement to an agent, plus its last known health.

    Carries no container identity any more: the agent is built in-process on
    demand (see :mod:`app.agents.pool`) and its conversation history lives in
    the Agno tables, so there is nothing here that has to survive a restart
    except the row itself.
    """

    __tablename__ = "agents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(unique=True, index=True, nullable=False)
    status: Mapped[AgentStatus] = mapped_column(
        Enum(AgentStatus, native_enum=False, length=32), default=AgentStatus.running, nullable=False
    )

    last_active_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    turn_lock_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    turn_lock_owner: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    chat_sessions: Mapped[list["ChatSession"]] = relationship(back_populates="agent", cascade="all, delete-orphan")


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(index=True, nullable=False)
    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agents.id"), nullable=False)

    # Agno's own session key. Kept distinct from ``id`` (which the client
    # mints) so the two can diverge without a migration.
    agno_session_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    message_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), index=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    agent: Mapped[Agent] = relationship(back_populates="chat_sessions")


class UserProfile(Base):
    """Per-user preferences and onboarding progress.

    Kept separate from :class:`CampusCredential` so the common read path — "has
    this student finished onboarding?" — never loads a row containing secrets.
    Rows are created lazily on first read; there is no signup hook to hang
    creation off, since identity lives in Supabase.
    """

    __tablename__ = "user_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)

    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    department: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # "undergraduate" | "graduate" | "english_prep". Scopes campus knowledge
    # retrieval: much of the academic calendar applies to one of these and not
    # the others, and answering "when is Add-Drop" without it means reciting
    # every variant back at the student.
    degree_level: Mapped[str | None] = mapped_column(String(32), nullable=True)
    locale: Mapped[str] = mapped_column(String(8), default="tr", nullable=False)

    # The step the student would land on if they reloaded mid-flow. Free-form
    # rather than an enum so the frontend can re-order the wizard without a
    # migration.
    onboarding_step: Mapped[str | None] = mapped_column(String(64), nullable=True)
    onboarding_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    @property
    def onboarding_completed(self) -> bool:
        return self.onboarding_completed_at is not None


class CampusCredential(Base):
    """One student's METU credentials, encrypted at rest.

    These exist because the campus MCP servers authenticate to METU as the
    student — there is no delegated-token flow at student.metu.edu.tr to use
    instead. Each server is spawned with only its own entry's credentials in
    its process environment; see :mod:`app.campus.mcp_config`. The password is
    Fernet-encrypted with ``SECRET_ENCRYPTION_KEY``
    (see ``app/core/crypto.py``), is decrypted only in
    ``app/campus/credentials.py``, and is never included in any response
    schema.
    """

    __tablename__ = "campus_credentials"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(unique=True, index=True, nullable=False)

    metu_username: Mapped[str] = mapped_column(String(255), nullable=False)
    metu_password_enc: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    # Optional alternative to the password for ODTUClass specifically: a Moodle
    # web service token the student can mint and revoke themselves.
    odtuclass_token_enc: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    odtuclass_base_url: Mapped[str | None] = mapped_column(String(255), nullable=True)

    locale: Mapped[str] = mapped_column(String(8), default="tr", nullable=False)
    enabled_tools: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)

    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verification_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Set when the credentials change, cleared once the resident agent has
    # been rebuilt with the new toolset. Lets the UI say "restart to apply"
    # instead of silently serving a stale toolset.
    config_dirty: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Monotonic generation checked by every broker replica. Tool ids alone do
    # not change when a password or token is rotated, so they cannot be used as
    # a cache key for credential-bearing MCP subprocesses.
    credential_revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AgentToolAudit(Base):
    """Minimal audit trail for external mutations; never stores message bodies."""

    __tablename__ = "agent_tool_audit"
    __table_args__ = (Index("ix_agent_tool_audit_user_created", "user_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # No separate index here: this table is insert-heavy and
    # ``ix_agent_tool_audit_user_created`` already serves user_id-only lookups
    # on its leading column, so a second one would only cost write amplification.
    user_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    session_id: Mapped[str] = mapped_column(String(255), nullable=False)
    run_id: Mapped[str] = mapped_column(String(255), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    # SHA-256 of canonicalized arguments supports incident correlation without
    # retaining recipients, subjects, bodies, or campus records.
    argument_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class CampusSource(Base):
    """One configured origin of public campus content.

    This table is the reason the knowledge layer is not a pile of scrapers. A
    source is *data*: an adapter slug plus the configuration that adapter needs.
    Adding ``ie.metu.edu.tr`` — Drupal 7, ``/en/announcement/{slug}`` singular,
    listed at ``/en/tum-duyurular`` — is a row rather than a deploy, which
    matters because METU's units do not share one site shape. The Drupal 10
    "miys" theme covers oidb, yurtlar, spormd, kim, ceng, math and psy; it does
    not cover everything, and assuming otherwise silently loses departments.

    Nothing here is secret: every field describes a public URL or how to parse
    one. That is what lets the whole table be admin-editable and audit-logged
    rather than held in deployment environment.
    """

    __tablename__ = "campus_sources"
    __table_args__ = (
        Index("ix_campus_sources_enabled_next", "enabled", "next_run_at"),
        CheckConstraint("refresh_seconds >= 60", name="ck_campus_sources_refresh_floor"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Which parser runs. Resolved against ``app.campus.sources.adapters`` at
    # ingest time; an unknown value fails that one source with a recorded error
    # rather than raising into the loop.
    adapter: Mapped[str] = mapped_column(String(32), nullable=False)
    # What the resulting documents are, for retrieval filtering and for the
    # citation the persona is required to produce.
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    base_url: Mapped[str] = mapped_column(String(500), nullable=False)
    # Adapter-specific: listing paths, link patterns, table shape, per-language
    # URLs. Deliberately opaque here — the adapter owns its own schema.
    config: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    # Declared charset is honoured first; this overrides it. catalog.metu.edu.tr
    # serves ISO-8859-9, and decoding that as UTF-8 mangles every Turkish word.
    encoding: Mapped[str | None] = mapped_column(String(32), nullable=True)
    languages: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)

    # Audience scoping. Empty means university-wide, which is the common case:
    # Add-Drop applies to everyone, a CENG announcement does not.
    departments: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    degree_levels: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    # ``{"lisansüstü": "degree_level:graduate"}``. The academic calendar carries
    # its audience in prose rather than in a column, so tagging rows on ingest
    # is the only way to answer "when is Add-Drop *for me*" instead of reciting
    # all 155 rows back at the student.
    audience_rules: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    refresh_seconds: Mapped[int] = mapped_column(Integer, default=21_600, nullable=False)
    max_pages: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    max_items: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False)

    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    # Bumped on every edit, on the same reasoning as
    # ``AgentRuntimeSettings.revision``: cached views compare against it.
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class CampusSourceRun(Base):
    """One ingest attempt, kept so a source that stopped parsing is visible.

    A scraper that silently returns zero items looks exactly like a quiet week
    on the site it scrapes. These rows separate the two, and they are what the
    admin UI shows instead of asking an operator to read logs.
    """

    __tablename__ = "campus_source_runs"
    __table_args__ = (Index("ix_campus_source_runs_source_started", "source_id", "started_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("campus_sources.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    items_seen: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    items_written: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    items_unchanged: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    requests_made: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    bytes_fetched: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class CampusCuratedEntry(Base):
    """Campus knowledge that exists in no crawlable place.

    Course WhatsApp groups are the clearest case: admins add these by hand and
    no amount of crawling produces them. Club registrations and hand-entered
    events land here too, and they reach the student through the same retrieval
    path as a crawled announcement — so the agent has one way to answer a
    campus question, not two.
    """

    __tablename__ = "campus_curated_entries"
    __table_args__ = (
        Index("ix_campus_curated_kind_key", "kind", "entry_key"),
        CheckConstraint(
            "kind IN ('whatsapp_group', 'club', 'event', 'note')",
            name="ck_campus_curated_kind",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    # The handle a student would ask by: a course code for a WhatsApp group, a
    # club slug for a club. Course codes are normalised upper-case by the API.
    entry_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    body: Mapped[str] = mapped_column(Text, default="", nullable=False)
    url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    language: Mapped[str] = mapped_column(String(8), default="tr", nullable=False)

    departments: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    degree_levels: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)

    # A stale WhatsApp invite is worse than no answer, so entries carry a
    # validity window and expired ones stop being retrievable.
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    updated_by: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class CampusGradePolicy(Base):
    """The university's grading rules, as data an admin can correct.

    METU's letter-to-point scale, whether an average weights METU credits or
    ECTS, and whether a retake replaces or averages are all set by regulation.
    Compiling them in would make a regulation change a deploy, and would make a
    wrong answer to "what is the maximum GPA I can reach" a code bug rather
    than a settings fix.
    """

    __tablename__ = "campus_grade_policies"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default="default")
    # ``{"AA": 4.0, "BA": 3.5, ...}``
    scale: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    # Grades carrying neither points nor credits: withdrawn, exempt, in progress.
    non_graded: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    # "credit" (METU credit) or "ects".
    weight_basis: Mapped[str] = mapped_column(String(16), default="credit", nullable=False)
    # Whether a repeated course replaces the earlier attempt in the average.
    retake_replaces: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    max_credits_per_semester: Mapped[int] = mapped_column(Integer, default=40, nullable=False)
    passing_grades: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
