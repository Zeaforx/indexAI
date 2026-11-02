"""PostgreSQL-only GIN index for title and description full-text candidates.

Revision ID: 0003
Revises: 0002

SQLite stays on the deterministic Python ranker. The index is an optimization
for PostgreSQL; both backends still use the same final ranking logic.
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

INDEX_NAME = "ix_resources_search_english_gin"


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "CREATE INDEX ix_resources_search_english_gin ON resources USING GIN ("
            "to_tsvector('english'::regconfig, "
            "coalesce(title, '') || ' ' || coalesce(description, '')))"
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_resources_search_english_gin")
