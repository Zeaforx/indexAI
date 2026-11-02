"""Non-destructive link-health observations, separate from review state.

Revision ID: 0004
Revises: 0003
"""

from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("resources") as batch:
        batch.add_column(sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("last_http_status", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("resources") as batch:
        batch.drop_column("last_http_status")
        batch.drop_column("last_checked_at")
