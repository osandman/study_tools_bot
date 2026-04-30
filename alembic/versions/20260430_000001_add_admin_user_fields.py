"""add admin user fields

Revision ID: 20260430_000001
Revises:
Create Date: 2026-04-30 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260430_000001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("is_blocked", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("users", sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True))
    op.alter_column("users", "is_blocked", server_default=None)


def downgrade() -> None:
    op.drop_column("users", "last_seen_at")
    op.drop_column("users", "is_blocked")
