"""Replace unstemmed search with language-aware FTS and trigram matching.

The original ``search_vector`` used the ``simple`` configuration, which does no
stemming and mis-folds Turkish's dotted/dotless I, so retrieval compensated in
Python with a hand-written suffix stripper. Postgres ships a Snowball stemmer
for both languages in this corpus; Snowball's Turkish still over-stems bare
nouns ("kütüphane" and "kütüphaneye" reduce differently), so a trigram index
covers that class instead of application code.

Revision ID: 0011_language_aware_search
Revises: 0010_embedding_prefixes
"""

from alembic import op

revision = "0011_language_aware_search"
down_revision = "0010_embedding_prefixes"
branch_labels = None
depends_on = None

_CONFIG = "CASE WHEN language = 'en' THEN 'english'::regconfig ELSE 'turkish'::regconfig END"
_SEARCH_VECTOR = (
    f"setweight(to_tsvector({_CONFIG}, coalesce(title, '')), 'A') || "
    f"setweight(to_tsvector({_CONFIG}, coalesce(summary, '')), 'B') || "
    f"setweight(to_tsvector({_CONFIG}, coalesce(content, '')), 'C')"
)
_SIMPLE_VECTOR = (
    "setweight(to_tsvector('simple', coalesce(title, '')), 'A') || "
    "setweight(to_tsvector('simple', coalesce(summary, '')), 'B') || "
    "setweight(to_tsvector('simple', coalesce(content, '')), 'C')"
)
_SEARCH_TEXT = "coalesce(title, '') || ' ' || coalesce(summary, '') || ' ' || coalesce(content, '')"


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # A generated column's expression cannot be altered in place.
    op.execute("DROP INDEX IF EXISTS ix_knowledge_records_fts")
    op.execute("ALTER TABLE campus_knowledge_records DROP COLUMN IF EXISTS search_vector")
    op.execute(
        "ALTER TABLE campus_knowledge_records ADD COLUMN search_vector tsvector "
        f"GENERATED ALWAYS AS ({_SEARCH_VECTOR}) STORED"
    )
    op.execute("CREATE INDEX ix_knowledge_records_fts ON campus_knowledge_records USING gin (search_vector)")

    op.execute(
        "ALTER TABLE campus_knowledge_records ADD COLUMN search_text text "
        f"GENERATED ALWAYS AS ({_SEARCH_TEXT}) STORED"
    )
    op.execute(
        "CREATE INDEX ix_knowledge_records_trgm ON campus_knowledge_records "
        "USING gin (search_text gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_knowledge_records_trgm")
    op.execute("ALTER TABLE campus_knowledge_records DROP COLUMN IF EXISTS search_text")
    op.execute("DROP INDEX IF EXISTS ix_knowledge_records_fts")
    op.execute("ALTER TABLE campus_knowledge_records DROP COLUMN IF EXISTS search_vector")
    op.execute(
        "ALTER TABLE campus_knowledge_records ADD COLUMN search_vector tsvector "
        f"GENERATED ALWAYS AS ({_SIMPLE_VECTOR}) STORED"
    )
    op.execute("CREATE INDEX ix_knowledge_records_fts ON campus_knowledge_records USING gin (search_vector)")
