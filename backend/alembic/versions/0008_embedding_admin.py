"""Add admin-managed embeddings, observable progress, and current course groups.

Revision ID: 0008_embedding_admin
Revises: 0007_campus_intelligence
"""

import sqlalchemy as sa

from alembic import op

revision = "0008_embedding_admin"
down_revision = "0007_campus_intelligence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "knowledge_embedding_settings",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(16), server_default="disabled", nullable=False),
        sa.Column("model", sa.Text(), server_default="text-embedding-3-small", nullable=False),
        sa.Column("base_url", sa.Text(), nullable=True),
        sa.Column("dimensions", sa.Integer(), server_default="1536", nullable=False),
        sa.Column("batch_size", sa.Integer(), server_default="32", nullable=False),
        sa.Column("api_key_enc", sa.LargeBinary(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "provider IN ('disabled', 'local', 'remote')", name="ck_embedding_settings_provider"
        ),
        sa.CheckConstraint(
            "dimensions BETWEEN 1 AND 1536", name="ck_embedding_settings_dimensions"
        ),
        sa.CheckConstraint("batch_size BETWEEN 1 AND 128", name="ck_embedding_settings_batch_size"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("organization_id"),
    )

    with op.batch_alter_table("campus_ingestion_jobs") as batch:
        batch.add_column(sa.Column("kind", sa.String(16), server_default="ingest", nullable=False))
        batch.add_column(sa.Column("phase", sa.String(16), server_default="queued", nullable=False))
        batch.add_column(sa.Column("total_records", sa.Integer(), server_default="0", nullable=False))
        batch.add_column(sa.Column("processed_records", sa.Integer(), server_default="0", nullable=False))
        batch.add_column(sa.Column("embedded_records", sa.Integer(), server_default="0", nullable=False))
        batch.add_column(sa.Column("embedding_provider", sa.String(16), nullable=True))
        batch.add_column(sa.Column("embedding_model", sa.Text(), nullable=True))
        batch.add_column(
            sa.Column(
                "progress_updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            )
        )
        batch.create_check_constraint("ck_ingestion_jobs_kind", "kind IN ('ingest', 'reembed')")
        batch.create_check_constraint(
            "ck_ingestion_jobs_phase",
            "phase IN ('queued', 'fetching', 'parsing', 'embedding', 'storing', 'completed', 'failed')",
        )

    # Semester-specific duplicates collapse to the most recent active link.
    # Empty section is the canonical representation for a course-wide group,
    # which gives the database a portable uniqueness guarantee across engines.
    op.execute(
        "DELETE FROM course_group_links WHERE id IN ("
        "SELECT id FROM ("
        "SELECT id, ROW_NUMBER() OVER ("
        "PARTITION BY organization_id, course_code, COALESCE(section, '') "
        "ORDER BY active DESC, updated_at DESC, created_at DESC"
        ") AS duplicate_rank FROM course_group_links"
        ") ranked WHERE duplicate_rank > 1)"
    )
    op.execute("UPDATE course_group_links SET section = '' WHERE section IS NULL")
    op.drop_index("ix_course_group_links_lookup", table_name="course_group_links")
    with op.batch_alter_table("course_group_links") as batch:
        batch.drop_constraint("uq_course_group_links_course_section", type_="unique")
        batch.alter_column(
            "section",
            existing_type=sa.String(16),
            nullable=False,
            server_default="",
        )
        batch.drop_column("term")
        batch.create_unique_constraint(
            "uq_course_group_links_course_section",
            ["organization_id", "course_code", "section"],
        )
    op.create_index(
        "ix_course_group_links_lookup",
        "course_group_links",
        ["organization_id", "course_code", "section", "active"],
    )

    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE knowledge_embedding_settings ENABLE ROW LEVEL SECURITY")
        op.execute(
            "DO $$ BEGIN "
            "IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN "
            "REVOKE ALL ON knowledge_embedding_settings FROM anon; END IF; "
            "IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN "
            "REVOKE ALL ON knowledge_embedding_settings FROM authenticated; END IF; END $$"
        )


def downgrade() -> None:
    op.drop_index("ix_course_group_links_lookup", table_name="course_group_links")
    with op.batch_alter_table("course_group_links") as batch:
        batch.drop_constraint("uq_course_group_links_course_section", type_="unique")
        batch.add_column(sa.Column("term", sa.String(32), server_default="unspecified", nullable=False))
        batch.alter_column(
            "section",
            existing_type=sa.String(16),
            nullable=True,
            server_default=None,
        )
        batch.create_unique_constraint(
            "uq_course_group_links_course_section",
            ["organization_id", "term", "course_code", "section"],
        )
    op.execute("UPDATE course_group_links SET section = NULL WHERE section = ''")
    op.create_index(
        "ix_course_group_links_lookup",
        "course_group_links",
        ["term", "course_code", "section", "active"],
    )

    with op.batch_alter_table("campus_ingestion_jobs") as batch:
        batch.drop_constraint("ck_ingestion_jobs_phase", type_="check")
        batch.drop_constraint("ck_ingestion_jobs_kind", type_="check")
        batch.drop_column("progress_updated_at")
        batch.drop_column("embedding_model")
        batch.drop_column("embedding_provider")
        batch.drop_column("embedded_records")
        batch.drop_column("processed_records")
        batch.drop_column("total_records")
        batch.drop_column("phase")
        batch.drop_column("kind")

    op.drop_table("knowledge_embedding_settings")
