"""initial schema: agents, chat_sessions

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-29
"""

import sqlalchemy as sa

from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("host_port", sa.Integer(), nullable=True),
        sa.Column("hermes_image_tag", sa.String(length=255), nullable=False),
        sa.Column("container_id", sa.String(length=255), nullable=True),
        sa.Column("container_name", sa.String(length=255), nullable=False),
        sa.Column("volume_name", sa.String(length=255), nullable=False),
        sa.Column("api_key_enc", sa.LargeBinary(), nullable=False),
        sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("turn_lock_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("turn_lock_owner", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_agents_user_id", "agents", ["user_id"], unique=True)

    op.create_table(
        "chat_sessions",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("agent_id", sa.Uuid(), sa.ForeignKey("agents.id"), nullable=False),
        sa.Column("hermes_session_id", sa.String(length=255), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("message_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_chat_sessions_user_id", "chat_sessions", ["user_id"])
    op.create_index("ix_chat_sessions_updated_at", "chat_sessions", ["updated_at"])


def downgrade() -> None:
    op.drop_index("ix_chat_sessions_updated_at", table_name="chat_sessions")
    op.drop_index("ix_chat_sessions_user_id", table_name="chat_sessions")
    op.drop_table("chat_sessions")
    op.drop_index("ix_agents_user_id", table_name="agents")
    op.drop_table("agents")
