"""Add the privacy-safe operational admin schema.

Revision ID: 0005_admin_operations
Revises: 0004_scholar_runtime
"""

import uuid

import sqlalchemy as sa

from alembic import op

revision = "0005_admin_operations"
down_revision = "0004_scholar_runtime"
branch_labels = None
depends_on = None

METU_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.bulk_insert(
        sa.table("organizations", sa.column("id", sa.Uuid()), sa.column("slug"), sa.column("name")),
        [{"id": METU_ID, "slug": "metu", "name": "Middle East Technical University"}],
    )

    op.create_table(
        "account_directory",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(320), nullable=True),
        sa.Column("email_normalized", sa.String(320), nullable=True),
        sa.Column("status", sa.String(32), server_default="active", nullable=False),
        sa.Column("auth_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("suspended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("suspended_reason", sa.String(1000), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.CheckConstraint(
            "status IN ('active', 'suspended', 'deletion_pending', 'deleted')",
            name="ck_account_directory_status",
        ),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_index("ix_account_directory_email_normalized", "account_directory", ["email_normalized"])
    op.create_index(
        "ix_account_directory_org_status_created",
        "account_directory",
        ["organization_id", "status", "created_at", "user_id"],
    )
    op.create_index(
        "ix_account_directory_org_last_seen", "account_directory", ["organization_id", "last_seen_at", "user_id"]
    )

    op.create_table(
        "admin_memberships",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=True),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("granted_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.CheckConstraint(
            "role IN ('super_admin', 'operator', 'campus_admin')",
            name="ck_admin_memberships_role",
        ),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_index("ix_admin_memberships_org_role", "admin_memberships", ["organization_id", "role", "user_id"])

    op.create_table(
        "admin_audit_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column("target_user_id", sa.Uuid(), nullable=True),
        sa.Column("organization_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("result", sa.String(32), nullable=False),
        sa.Column("reason", sa.String(1000), nullable=True),
        sa.Column("before_state", sa.JSON(), nullable=True),
        sa.Column("after_state", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_admin_audit_created_id", "admin_audit_events", ["created_at", "id"])
    op.create_index("ix_admin_audit_org_created", "admin_audit_events", ["organization_id", "created_at", "id"])
    op.create_index("ix_admin_audit_target_created", "admin_audit_events", ["target_user_id", "created_at"])

    op.create_table(
        "agent_runtime_settings",
        sa.Column("id", sa.String(32), nullable=False),
        sa.Column("model_id", sa.String(255), nullable=True),
        sa.Column("profile", sa.String(32), nullable=True),
        sa.Column("max_tokens", sa.Integer(), nullable=True),
        sa.Column("legacy_history_runs", sa.Integer(), nullable=True),
        sa.Column("scholar_history_runs", sa.Integer(), nullable=True),
        sa.Column("tool_call_limit", sa.Integer(), nullable=True),
        sa.Column("learning_enabled", sa.Boolean(), nullable=True),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.bulk_insert(sa.table("agent_runtime_settings", sa.column("id")), [{"id": "default"}])

    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            """
            CREATE FUNCTION reject_admin_audit_mutation() RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'admin_audit_events is append-only';
            END;
            $$ LANGUAGE plpgsql
            """
        )
        op.execute(
            """
            CREATE TRIGGER admin_audit_events_append_only
            BEFORE UPDATE OR DELETE ON admin_audit_events
            FOR EACH ROW EXECUTE FUNCTION reject_admin_audit_mutation()
            """
        )
    else:
        op.execute(
            """
            CREATE TRIGGER admin_audit_events_no_update
            BEFORE UPDATE ON admin_audit_events
            BEGIN SELECT RAISE(ABORT, 'admin_audit_events is append-only'); END
            """
        )
        op.execute(
            """
            CREATE TRIGGER admin_audit_events_no_delete
            BEFORE DELETE ON admin_audit_events
            BEGIN SELECT RAISE(ABORT, 'admin_audit_events is append-only'); END
            """
        )


def downgrade() -> None:
    op.drop_table("agent_runtime_settings")
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER admin_audit_events_append_only ON admin_audit_events")
        op.execute("DROP FUNCTION reject_admin_audit_mutation()")
    else:
        op.execute("DROP TRIGGER admin_audit_events_no_update")
        op.execute("DROP TRIGGER admin_audit_events_no_delete")
    op.drop_index("ix_admin_audit_org_created", table_name="admin_audit_events")
    op.drop_index("ix_admin_audit_target_created", table_name="admin_audit_events")
    op.drop_index("ix_admin_audit_created_id", table_name="admin_audit_events")
    op.drop_table("admin_audit_events")
    op.drop_index("ix_admin_memberships_org_role", table_name="admin_memberships")
    op.drop_table("admin_memberships")
    op.drop_index("ix_account_directory_org_last_seen", table_name="account_directory")
    op.drop_index("ix_account_directory_org_status_created", table_name="account_directory")
    op.drop_index("ix_account_directory_email_normalized", table_name="account_directory")
    op.drop_table("account_directory")
    op.drop_table("organizations")
