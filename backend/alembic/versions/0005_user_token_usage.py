"""Add persistent per-user hourly token accounting.

Revision ID: 0005_user_token_usage
Revises: 0004_scholar_runtime
"""

import sqlalchemy as sa

from alembic import op

revision = "0005_user_token_usage"
down_revision = "0004_scholar_runtime"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_token_usage",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("bucket_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("request_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "bucket_start", name="uq_user_token_usage_user_bucket"),
    )
    op.create_index("ix_user_token_usage_bucket_start", "user_token_usage", ["bucket_start"])
    op.create_index("ix_user_token_usage_user_id", "user_token_usage", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_user_token_usage_user_id", table_name="user_token_usage")
    op.drop_index("ix_user_token_usage_bucket_start", table_name="user_token_usage")
    op.drop_table("user_token_usage")
