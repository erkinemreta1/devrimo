"""Add asymmetric query/document embedding instructions.

Revision ID: 0010_embedding_prefixes
Revises: 0009_knowledge_chunk_search
"""

import sqlalchemy as sa

from alembic import op

revision = "0010_embedding_prefixes"
down_revision = "0009_knowledge_chunk_search"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Empty defaults keep every already-indexed corpus valid: with no document
    # prefix the embedding model label is unchanged, so stored vectors stay
    # comparable and no reindex is forced by this migration.
    op.add_column(
        "knowledge_embedding_settings",
        sa.Column("query_prefix", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "knowledge_embedding_settings",
        sa.Column("document_prefix", sa.Text(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("knowledge_embedding_settings", "document_prefix")
    op.drop_column("knowledge_embedding_settings", "query_prefix")
