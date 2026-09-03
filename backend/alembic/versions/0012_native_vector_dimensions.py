"""Store embeddings at native dimensions with separate HNSW indexes.

Revision ID: 0012_native_vector_dimensions
Revises: 0011_language_aware_search
"""

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

from alembic import op

revision = "0012_native_vector_dimensions"
down_revision = "0011_language_aware_search"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        # Arbitrary legacy widths cannot be indexed natively in one pgvector
        # column. Fail with an actionable message instead of silently changing
        # an embedding model's configured output shape.
        op.execute(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM knowledge_embedding_settings
                    WHERE dimensions NOT IN (384, 768, 1536)
                ) THEN
                    RAISE EXCEPTION
                        'Reconfigure embedding dimensions to 384, 768, or 1536 before upgrading';
                END IF;
            END $$
            """
        )
    op.drop_constraint("ck_embedding_settings_dimensions", "knowledge_embedding_settings", type_="check")
    op.create_check_constraint(
        "ck_embedding_settings_dimensions",
        "knowledge_embedding_settings",
        "dimensions IN (384, 768, 1536)",
    )
    op.drop_index("ix_knowledge_records_embedding_model_current", table_name="campus_knowledge_records")
    op.execute("DROP INDEX IF EXISTS ix_knowledge_records_embedding_hnsw")
    op.alter_column("campus_knowledge_records", "embedding", new_column_name="embedding_1536")
    op.add_column("campus_knowledge_records", sa.Column("embedding_384", Vector(384), nullable=True))
    op.add_column("campus_knowledge_records", sa.Column("embedding_768", Vector(768), nullable=True))

    if op.get_bind().dialect.name == "postgresql":
        # Existing short vectors were zero-padded. Recover their native prefix
        # so deployments retain indexed data through this migration when
        # subvector (added in pgvector 0.7.0) is available. On pgvector < 0.7.0,
        # clear padded short vectors so they can be re-embedded cleanly at native dimensions.
        op.execute(
            """
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM pg_proc WHERE proname = 'subvector') THEN
                    UPDATE campus_knowledge_records SET embedding_384 =
                        subvector(embedding_1536, 1, 384)::vector(384), embedding_1536 = NULL
                        WHERE embedding_1536 IS NOT NULL AND embedding_model ~ '\\:384(\\:[0-9a-f]{8})?$';
                    UPDATE campus_knowledge_records SET embedding_768 =
                        subvector(embedding_1536, 1, 768)::vector(768), embedding_1536 = NULL
                        WHERE embedding_1536 IS NOT NULL AND embedding_model ~ '\\:768(\\:[0-9a-f]{8})?$';
                ELSE
                    UPDATE campus_knowledge_records SET embedding_1536 = NULL
                        WHERE embedding_1536 IS NOT NULL
                        AND (
                            embedding_model ~ '\\:384(\\:[0-9a-f]{8})?$'
                            OR embedding_model ~ '\\:768(\\:[0-9a-f]{8})?$'
                        );
                END IF;
            END $$;
            """
        )
        for dimensions in (384, 768, 1536):
            op.execute(
                f"CREATE INDEX ix_knowledge_records_embedding_{dimensions}_hnsw "
                f"ON campus_knowledge_records USING hnsw (embedding_{dimensions} vector_cosine_ops) "
                f"WHERE embedding_{dimensions} IS NOT NULL AND is_current"
            )

    predicate = sa.text(
        "is_current AND (embedding_384 IS NOT NULL OR embedding_768 IS NOT NULL OR embedding_1536 IS NOT NULL)"
    )
    op.create_index(
        "ix_knowledge_records_embedding_model_current",
        "campus_knowledge_records",
        ["embedding_model", "source_id"],
        postgresql_where=predicate,
    )


def downgrade() -> None:
    op.drop_constraint("ck_embedding_settings_dimensions", "knowledge_embedding_settings", type_="check")
    op.create_check_constraint(
        "ck_embedding_settings_dimensions",
        "knowledge_embedding_settings",
        "dimensions BETWEEN 1 AND 1536",
    )
    op.drop_index("ix_knowledge_records_embedding_model_current", table_name="campus_knowledge_records")
    for dimensions in (384, 768, 1536):
        op.execute(f"DROP INDEX IF EXISTS ix_knowledge_records_embedding_{dimensions}_hnsw")
    # Smaller vectors require a reindex after downgrading because the old
    # schema cannot store them without recreating the removed padding.
    op.drop_column("campus_knowledge_records", "embedding_768")
    op.drop_column("campus_knowledge_records", "embedding_384")
    op.alter_column("campus_knowledge_records", "embedding_1536", new_column_name="embedding")
    op.create_index(
        "ix_knowledge_records_embedding_model_current",
        "campus_knowledge_records",
        ["embedding_model", "source_id"],
        postgresql_where=sa.text("is_current AND embedding IS NOT NULL"),
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "CREATE INDEX ix_knowledge_records_embedding_hnsw ON campus_knowledge_records "
            "USING hnsw (embedding vector_cosine_ops) WHERE embedding IS NOT NULL AND is_current"
        )
