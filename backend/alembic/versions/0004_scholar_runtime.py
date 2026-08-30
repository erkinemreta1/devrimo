"""Add Scholar credential generations and mutation audit storage.

Revision ID: 0004_scholar_runtime
Revises: 0003_agno_runtime
"""

import sqlalchemy as sa

from alembic import op

revision = "0004_scholar_runtime"
down_revision = "0003_agno_runtime"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("campus_credentials") as batch:
        batch.add_column(sa.Column("credential_revision", sa.Integer(), nullable=False, server_default="1"))

    op.create_table(
        "agent_tool_audit",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.String(length=255), nullable=False),
        sa.Column("run_id", sa.String(length=255), nullable=False),
        sa.Column("tool_name", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("argument_digest", sa.String(length=64), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    # Only the composite index. Audit rows are written on every external
    # mutation and read back by user, and a standalone user_id index would be
    # a redundant leading-column prefix of this one.
    op.create_index("ix_agent_tool_audit_user_created", "agent_tool_audit", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_agent_tool_audit_user_created", table_name="agent_tool_audit")
    op.drop_table("agent_tool_audit")
    with op.batch_alter_table("campus_credentials") as batch:
        batch.drop_column("credential_revision")
