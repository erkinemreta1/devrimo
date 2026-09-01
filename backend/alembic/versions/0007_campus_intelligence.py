"""Add the configurable campus intelligence platform.

Revision ID: 0007_campus_intelligence
Revises: 0006_llm_pricing
"""

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

from alembic import op

revision = "0007_campus_intelligence"
down_revision = "0006_llm_pricing"
branch_labels = None
depends_on = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    bind = op.get_bind()
    postgres = bind.dialect.name == "postgresql"
    if postgres:
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.add_column(
        "user_profiles", sa.Column("mail_facts_enabled", sa.Boolean(), server_default=sa.false(), nullable=False)
    )

    op.create_table(
        "campus_sources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("language", sa.String(8), server_default="tr", nullable=False),
        sa.Column("authority", sa.Integer(), server_default="50", nullable=False),
        sa.Column("audience", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("schedule_seconds", sa.Integer(), server_default="3600", nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("status", sa.String(16), server_default="draft", nullable=False),
        sa.Column("active_revision_id", sa.Uuid(), nullable=True),
        sa.Column("etag", sa.Text(), nullable=True),
        sa.Column("last_modified", sa.Text(), nullable=True),
        sa.Column("last_fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "kind IN ('drupal', 'html_page', 'html_table', 'rss', 'ical', 'json', 'pdf', "
            "'approved_social', 'email_facts', 'curated')",
            name="ck_campus_sources_kind",
        ),
        sa.CheckConstraint("status IN ('draft', 'published', 'disabled')", name="ck_campus_sources_status"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_campus_sources_org_status", "campus_sources", ["organization_id", "status", "enabled"])

    op.create_table(
        "campus_source_revisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), server_default="draft", nullable=False),
        sa.Column("config", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("validation", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('draft', 'valid', 'published', 'rejected')", name="ck_source_revision_status"),
        sa.ForeignKeyConstraint(["source_id"], ["campus_sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_id", "revision", name="uq_campus_source_revisions_source_revision"),
    )
    op.create_index(
        "ix_source_revisions_source_created", "campus_source_revisions", ["source_id", "created_at"]
    )

    op.create_table(
        "campus_ingestion_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("revision_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(16), server_default="queued", nullable=False),
        sa.Column("attempt", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default="5", nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("leased_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_owner", sa.String(128), nullable=True),
        sa.Column("error_code", sa.String(128), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('queued', 'leased', 'completed', 'failed', 'dead')", name="ck_ingestion_jobs_status"
        ),
        sa.ForeignKeyConstraint(["source_id"], ["campus_sources.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["revision_id"], ["campus_source_revisions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ingestion_jobs_claim", "campus_ingestion_jobs", ["status", "available_at", "created_at"]
    )
    op.create_index(
        "ix_ingestion_jobs_source_created", "campus_ingestion_jobs", ["source_id", "created_at"]
    )

    op.create_table(
        "campus_knowledge_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("source_revision_id", sa.Uuid(), nullable=False),
        sa.Column("external_id", sa.Text(), nullable=False),
        sa.Column("record_type", sa.String(32), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("language", sa.String(8), server_default="tr", nullable=False),
        sa.Column("campus", sa.Text(), nullable=True),
        sa.Column("department", sa.Text(), nullable=True),
        sa.Column("degree_level", sa.String(32), nullable=True),
        sa.Column("audience", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("authority", sa.Integer(), server_default="50", nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("metadata", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("embedding", Vector(1536), nullable=True),
        sa.Column("embedding_model", sa.Text(), nullable=True),
        sa.Column("is_current", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "record_type IN ('announcement', 'calendar', 'event', 'service_status', 'guide', 'course', 'policy')",
            name="ck_knowledge_records_type",
        ),
        sa.ForeignKeyConstraint(["source_id"], ["campus_sources.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_revision_id"], ["campus_source_revisions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_id", "external_id", name="uq_knowledge_records_source_external"),
    )
    op.create_index(
        "ix_knowledge_records_source_current", "campus_knowledge_records", ["source_id", "is_current"]
    )
    op.create_index(
        "ix_knowledge_records_type_dates", "campus_knowledge_records", ["record_type", "starts_at", "ends_at"]
    )
    op.create_index(
        "ix_knowledge_records_audience",
        "campus_knowledge_records",
        ["campus", "department", "degree_level"],
    )
    op.create_index(
        "ix_knowledge_records_published", "campus_knowledge_records", ["published_at", "id"]
    )
    if postgres:
        op.execute(
            "ALTER TABLE campus_knowledge_records ADD COLUMN search_vector tsvector "
            "GENERATED ALWAYS AS (setweight(to_tsvector('simple', coalesce(title, '')), 'A') || "
            "setweight(to_tsvector('simple', coalesce(summary, '')), 'B') || "
            "setweight(to_tsvector('simple', coalesce(content, '')), 'C')) STORED"
        )
        op.execute("CREATE INDEX ix_knowledge_records_fts ON campus_knowledge_records USING gin (search_vector)")
        op.execute(
            "CREATE INDEX ix_knowledge_records_embedding_hnsw ON campus_knowledge_records "
            "USING hnsw (embedding vector_cosine_ops) WHERE embedding IS NOT NULL AND is_current"
        )

    op.create_table(
        "student_contexts",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("department", sa.Text(), nullable=True),
        sa.Column("degree_level", sa.String(32), nullable=True),
        sa.Column("program_code", sa.String(32), nullable=True),
        sa.Column("campus", sa.Text(), nullable=True),
        sa.Column("source", sa.String(32), server_default="manual", nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_table(
        "user_preferences",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(64), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("provenance", sa.String(16), nullable=False),
        sa.Column("confidence", sa.Numeric(4, 3), server_default="1", nullable=False),
        *_timestamps(),
        sa.CheckConstraint("provenance IN ('explicit', 'learned')", name="ck_user_preferences_provenance"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "key", name="uq_user_preferences_user_key"),
    )
    op.create_index("ix_user_preferences_user_updated", "user_preferences", ["user_id", "updated_at"])

    op.create_table(
        "user_update_states",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("record_id", sa.Uuid(), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["record_id"], ["campus_knowledge_records.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "record_id"),
    )
    op.create_index("ix_user_update_states_user_updated", "user_update_states", ["user_id", "updated_at"])

    op.create_table(
        "student_academic_snapshots",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("term", sa.String(32), nullable=False),
        sa.Column("completed_courses", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("enrolled_courses", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("current_credits", sa.Numeric(8, 2), server_default="0", nullable=False),
        sa.Column("current_grade_points", sa.Numeric(10, 3), server_default="0", nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("source", sa.String(32), server_default="sais", nullable=False),
        sa.PrimaryKeyConstraint("user_id", "term"),
    )
    op.create_index(
        "ix_academic_snapshots_user_fetched", "student_academic_snapshots", ["user_id", "fetched_at"]
    )

    op.create_table(
        "course_offerings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("term", sa.String(32), nullable=False),
        sa.Column("course_code", sa.String(32), nullable=False),
        sa.Column("section", sa.String(16), server_default="1", nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("credits", sa.Numeric(6, 2), nullable=False),
        sa.Column("schedule", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("campus", sa.Text(), nullable=True),
        sa.Column("department", sa.Text(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("term", "course_code", "section", name="uq_course_offerings_term_course_section"),
    )
    op.create_index("ix_course_offerings_term_course", "course_offerings", ["term", "course_code"])

    op.create_table(
        "course_rules",
        sa.Column("course_code", sa.String(32), nullable=False),
        sa.Column("prerequisites", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("exclusions", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("catalog_url", sa.Text(), nullable=True),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("course_code"),
    )

    op.create_table(
        "planning_policies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("rules", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "name", "revision", name="uq_planning_policies_org_name_revision"),
    )
    op.create_index("ix_planning_policies_org_active", "planning_policies", ["organization_id", "active"])

    op.create_table(
        "course_group_links",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("term", sa.String(32), nullable=False),
        sa.Column("course_code", sa.String(32), nullable=False),
        sa.Column("section", sa.String(16), nullable=True),
        sa.Column("invite_url_enc", sa.LargeBinary(), nullable=False),
        sa.Column("eligibility", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id", "term", "course_code", "section", name="uq_course_group_links_course_section"
        ),
    )
    op.create_index(
        "ix_course_group_links_lookup", "course_group_links", ["term", "course_code", "section", "active"]
    )
    op.create_table(
        "course_group_access_audit",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("group_id", sa.Uuid(), nullable=False),
        sa.Column("result", sa.String(32), nullable=False),
        sa.Column("reason_code", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_course_group_access_user_created", "course_group_access_audit", ["user_id", "created_at"]
    )
    op.create_table(
        "user_mail_facts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("external_id", sa.String(64), nullable=False),
        sa.Column("fact_type", sa.String(32), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("sender_domain", sa.Text(), nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("message_digest", sa.String(64), nullable=False),
        sa.Column("extracted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "external_id", name="uq_user_mail_facts_user_external"),
    )
    op.create_index(
        "ix_user_mail_facts_user_dates", "user_mail_facts", ["user_id", "starts_at", "valid_until"]
    )

    if postgres:
        # These tables are backend-owned. RLS plus revoked Data API roles keeps
        # accidental public-schema exposure from turning them into public APIs.
        protected = (
            "campus_sources",
            "campus_source_revisions",
            "campus_ingestion_jobs",
            "campus_knowledge_records",
            "student_contexts",
            "user_preferences",
            "user_update_states",
            "student_academic_snapshots",
            "course_offerings",
            "course_rules",
            "planning_policies",
            "course_group_links",
            "course_group_access_audit",
            "user_mail_facts",
        )
        for table in protected:
            op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            "DO $$ BEGIN "
            "IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN "
            f"REVOKE ALL ON {', '.join(protected)} FROM anon; END IF; "
            "IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN "
            f"REVOKE ALL ON {', '.join(protected)} FROM authenticated; END IF; END $$"
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_knowledge_records_embedding_hnsw")
        op.execute("DROP INDEX IF EXISTS ix_knowledge_records_fts")
    for table in (
        "user_mail_facts",
        "course_group_access_audit",
        "course_group_links",
        "planning_policies",
        "course_rules",
        "course_offerings",
        "student_academic_snapshots",
        "user_update_states",
        "user_preferences",
        "student_contexts",
        "campus_knowledge_records",
        "campus_ingestion_jobs",
        "campus_source_revisions",
        "campus_sources",
    ):
        op.drop_table(table)
    op.drop_column("user_profiles", "mail_facts_enabled")
