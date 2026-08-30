"""user profiles + encrypted campus (METU) credentials

Revision ID: 0002_campus_mcp
Revises: 0001_initial
Create Date: 2026-08-30
"""

import sqlalchemy as sa

from alembic import op

revision = "0002_campus_mcp"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_profiles",
        sa.Column("user_id", sa.Uuid(), primary_key=True),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("department", sa.String(length=255), nullable=True),
        sa.Column("locale", sa.String(length=8), nullable=False, server_default="tr"),
        sa.Column("onboarding_step", sa.String(length=64), nullable=True),
        sa.Column("onboarding_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "campus_credentials",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("metu_username", sa.String(length=255), nullable=False),
        sa.Column("metu_password_enc", sa.LargeBinary(), nullable=True),
        sa.Column("odtuclass_token_enc", sa.LargeBinary(), nullable=True),
        sa.Column("odtuclass_base_url", sa.String(length=255), nullable=True),
        sa.Column("locale", sa.String(length=8), nullable=False, server_default="tr"),
        sa.Column("enabled_tools", sa.JSON(), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verification_error", sa.Text(), nullable=True),
        sa.Column("config_dirty", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_campus_credentials_user_id", "campus_credentials", ["user_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_campus_credentials_user_id", table_name="campus_credentials")
    op.drop_table("campus_credentials")
    op.drop_table("user_profiles")
