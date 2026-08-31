"""Add admin-configurable LLM per-token pricing to agent runtime settings.

Revision ID: 0006_llm_pricing
Revises: 0005_admin_operations
"""

import sqlalchemy as sa

from alembic import op

revision = "0006_llm_pricing"
down_revision = "0005_admin_operations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agent_runtime_settings", sa.Column("input_token_price", sa.Float(), nullable=True))
    op.add_column("agent_runtime_settings", sa.Column("output_token_price", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("agent_runtime_settings", "output_token_price")
    op.drop_column("agent_runtime_settings", "input_token_price")
