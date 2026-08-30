"""Drop the container-era agent columns and rename the session key for Agno.

The agent no longer runs in a container, so nothing on ``agents`` needs to
address one: no image tag, no container or volume name, no per-container API
key, no published port. Agno's own tables (``agno_sessions``, ``agno_runs``,
...) are created by its database layer on first use and are deliberately not
described here — this migration only touches tables this app owns.

``api_key_enc`` held a Fernet-encrypted per-container key. Dropping the column
destroys those keys, which is correct: there is no longer a container to
authenticate to, and keeping decryptable secrets for a system that no longer
exists is strictly worse than losing them.

Revision ID: 0003_agno_runtime
Revises: 0002_campus_mcp
"""

import sqlalchemy as sa

from alembic import op

revision = "0003_agno_runtime"
down_revision = "0002_campus_mcp"
branch_labels = None
depends_on = None

_DROPPED_AGENT_COLUMNS = (
    "host_port",
    "hermes_image_tag",
    "container_id",
    "container_name",
    "volume_name",
    "api_key_enc",
)


def upgrade() -> None:
    # batch_alter_table so this also works on SQLite, which cannot DROP COLUMN
    # in place and which local dev runs against.
    with op.batch_alter_table("agents") as batch:
        for column in _DROPPED_AGENT_COLUMNS:
            batch.drop_column(column)

    with op.batch_alter_table("chat_sessions") as batch:
        batch.alter_column("hermes_session_id", new_column_name="agno_session_id")


def downgrade() -> None:
    with op.batch_alter_table("chat_sessions") as batch:
        batch.alter_column("agno_session_id", new_column_name="hermes_session_id")

    with op.batch_alter_table("agents") as batch:
        batch.add_column(sa.Column("host_port", sa.Integer(), nullable=True))
        # The dropped values are unrecoverable, so the restored columns are
        # nullable even where they were originally NOT NULL. A downgrade puts
        # the schema back; it cannot put the containers back.
        batch.add_column(sa.Column("hermes_image_tag", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("container_id", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("container_name", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("volume_name", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("api_key_enc", sa.LargeBinary(), nullable=True))
