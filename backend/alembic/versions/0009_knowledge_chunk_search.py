"""Add indexes for chunked knowledge retrieval and model-safe vector search.

Revision ID: 0009_knowledge_chunk_search
Revises: 0008_embedding_admin
"""

import sqlalchemy as sa

from alembic import op

revision = "0009_knowledge_chunk_search"
down_revision = "0008_embedding_admin"
branch_labels = None
depends_on = None


def upgrade() -> None:
    current = sa.text("is_current = 1")
    current_embedding = sa.text("is_current = 1 AND embedding IS NOT NULL")
    if op.get_bind().dialect.name == "postgresql":
        current = sa.text("is_current")
        current_embedding = sa.text("is_current AND embedding IS NOT NULL")

    op.create_index(
        "ix_knowledge_records_source_revision",
        "campus_knowledge_records",
        ["source_revision_id"],
    )
    op.create_index(
        "ix_knowledge_records_url_current",
        "campus_knowledge_records",
        ["url", "source_id"],
        sqlite_where=current,
        postgresql_where=current,
    )
    op.create_index(
        "ix_knowledge_records_embedding_model_current",
        "campus_knowledge_records",
        ["embedding_model", "source_id"],
        sqlite_where=current_embedding,
        postgresql_where=current_embedding,
    )


def downgrade() -> None:
    op.drop_index("ix_knowledge_records_embedding_model_current", table_name="campus_knowledge_records")
    op.drop_index("ix_knowledge_records_url_current", table_name="campus_knowledge_records")
    op.drop_index("ix_knowledge_records_source_revision", table_name="campus_knowledge_records")
