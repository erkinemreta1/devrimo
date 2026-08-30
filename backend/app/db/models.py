import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Enum, ForeignKey, Integer, LargeBinary, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class AgentStatus(enum.StrEnum):
    provisioning = "provisioning"
    running = "running"
    stopped = "stopped"
    error = "error"
    destroying = "destroying"


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(unique=True, index=True, nullable=False)
    status: Mapped[AgentStatus] = mapped_column(
        Enum(AgentStatus, native_enum=False, length=32), default=AgentStatus.provisioning, nullable=False
    )
    host_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hermes_image_tag: Mapped[str] = mapped_column(String(255), nullable=False)

    container_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    container_name: Mapped[str] = mapped_column(String(255), nullable=False)
    volume_name: Mapped[str] = mapped_column(String(255), nullable=False)
    api_key_enc: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)

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

    hermes_session_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
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
    instead. The password is Fernet-encrypted with ``SECRET_ENCRYPTION_KEY``
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
    # Set when the credentials change, cleared once the agent container has
    # been recreated with the new MCP config. Lets the UI say "restart to
    # apply" instead of silently serving a stale toolset.
    config_dirty: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
