"""Provenance and ingestion metadata.

Revision ID: 0002
Revises: 0001
"""

from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("sources") as batch:
        batch.add_column(sa.Column("ingestion_method", sa.String(30), nullable=False, server_default="manual"))
        batch.add_column(sa.Column("attribution_notice", sa.Text(), nullable=False, server_default=""))
        batch.add_column(sa.Column("policy_checked_at", sa.DateTime(timezone=True), nullable=True))
    with op.batch_alter_table("resources") as batch:
        batch.add_column(sa.Column("author_name", sa.Text(), nullable=False, server_default=""))
        batch.add_column(sa.Column("source_asset_id", sa.String(200), nullable=True))
        batch.add_column(sa.Column("source_tags", sa.JSON(), nullable=False, server_default="[]"))
        batch.add_column(sa.Column("metadata_source", sa.String(40), nullable=False, server_default="manual"))
        batch.add_column(sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("resources") as batch:
        batch.drop_column("last_synced_at")
        batch.drop_column("metadata_source")
        batch.drop_column("source_tags")
        batch.drop_column("source_asset_id")
        batch.drop_column("author_name")
    with op.batch_alter_table("sources") as batch:
        batch.drop_column("policy_checked_at")
        batch.drop_column("attribution_notice")
        batch.drop_column("ingestion_method")
