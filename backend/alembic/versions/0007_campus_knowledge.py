"""Campus knowledge layer: configurable sources, curated entries, grading policy.

Revision ID: 0007_campus_knowledge
Revises: 0006_llm_pricing

The ``vector`` extension is created here rather than left to the vector client.
Agno's PgVector would issue ``CREATE EXTENSION`` itself on first use, but that
needs superuser on most managed Postgres instances and would fail at the moment
a student asks a question rather than at deploy time. On SQLite — the test
suite and most local development — the statement is skipped and the corpus
simply reports itself unavailable.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0007_campus_knowledge"
down_revision = "0006_llm_pricing"
branch_labels = None
depends_on = None


def _json() -> sa.types.TypeEngine:
    """JSONB on Postgres, JSON elsewhere.

    JSONB is what makes the corpus queryable by ``meta_data->>'source_slug'``,
    which is how per-source counts and deletes work.
    """
    return postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.add_column("user_profiles", sa.Column("degree_level", sa.String(length=32), nullable=True))
    op.add_column("agent_runtime_settings", sa.Column("knowledge_enabled", sa.Boolean(), nullable=True))
    op.add_column("agent_runtime_settings", sa.Column("knowledge_max_results", sa.Integer(), nullable=True))

    op.create_table(
        "campus_sources",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("slug", sa.String(length=64), nullable=False, unique=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("adapter", sa.String(length=32), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("base_url", sa.String(length=500), nullable=False),
        sa.Column("config", _json(), nullable=False, server_default="{}"),
        sa.Column("encoding", sa.String(length=32), nullable=True),
        sa.Column("languages", _json(), nullable=False, server_default="[]"),
        sa.Column("departments", _json(), nullable=False, server_default="[]"),
        sa.Column("degree_levels", _json(), nullable=False, server_default="[]"),
        sa.Column("audience_rules", _json(), nullable=False, server_default="{}"),
        sa.Column("refresh_seconds", sa.Integer(), nullable=False, server_default="21600"),
        sa.Column("max_pages", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("max_items", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status", sa.String(length=32), nullable=True),
        sa.Column("last_error", sa.String(length=1000), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("refresh_seconds >= 60", name="ck_campus_sources_refresh_floor"),
    )
    op.create_index("ix_campus_sources_enabled_next", "campus_sources", ["enabled", "next_run_at"])

    op.create_table(
        "campus_source_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("source_id", sa.Uuid(), sa.ForeignKey("campus_sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("items_seen", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("items_written", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("items_unchanged", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("requests_made", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("bytes_fetched", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_campus_source_runs_source_started", "campus_source_runs", ["source_id", "started_at"])

    op.create_table(
        "campus_curated_entries",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("entry_key", sa.String(length=128), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("body", sa.Text(), nullable=False, server_default=""),
        sa.Column("url", sa.String(length=1000), nullable=True),
        sa.Column("language", sa.String(length=8), nullable=False, server_default="tr"),
        sa.Column("departments", _json(), nullable=False, server_default="[]"),
        sa.Column("degree_levels", _json(), nullable=False, server_default="[]"),
        sa.Column("tags", _json(), nullable=False, server_default="[]"),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "kind IN ('whatsapp_group', 'club', 'event', 'note')",
            name="ck_campus_curated_kind",
        ),
    )
    op.create_index("ix_campus_curated_kind_key", "campus_curated_entries", ["kind", "entry_key"])

    op.create_table(
        "campus_grade_policies",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("scale", _json(), nullable=False, server_default="{}"),
        sa.Column("non_graded", _json(), nullable=False, server_default="[]"),
        sa.Column("weight_basis", sa.String(length=16), nullable=False, server_default="credit"),
        sa.Column("retake_replaces", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("max_credits_per_semester", sa.Integer(), nullable=False, server_default="40"),
        sa.Column("passing_grades", _json(), nullable=False, server_default="[]"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("campus_grade_policies")
    op.drop_index("ix_campus_curated_kind_key", table_name="campus_curated_entries")
    op.drop_table("campus_curated_entries")
    op.drop_index("ix_campus_source_runs_source_started", table_name="campus_source_runs")
    op.drop_table("campus_source_runs")
    op.drop_index("ix_campus_sources_enabled_next", table_name="campus_sources")
    op.drop_table("campus_sources")
    op.drop_column("agent_runtime_settings", "knowledge_max_results")
    op.drop_column("agent_runtime_settings", "knowledge_enabled")
    op.drop_column("user_profiles", "degree_level")
    # The vector extension is left in place: other schemas may rely on it, and
    # dropping an extension takes its data with it.
