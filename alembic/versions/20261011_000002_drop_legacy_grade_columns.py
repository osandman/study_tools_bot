"""drop legacy grade columns

Revision ID: 20261011_000002
Revises: 20260430_000001
Create Date: 2026-10-11 12:00:00.000000

Production was created with create_all() by an early version of the models and still carries what
the app no longer has: grades.grade_type, grades.description and a server default 'trimester_1' on
grades.period — a period key the bot does not know, so a row relying on it would be invisible.
Databases built from the migrations never had any of this, hence IF EXISTS.
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "20261011_000002"
down_revision = "20260430_000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE grades DROP COLUMN IF EXISTS grade_type")
    op.execute("ALTER TABLE grades DROP COLUMN IF EXISTS description")
    op.alter_column("grades", "period", server_default=None)


def downgrade() -> None:
    # Nothing the app reads lived in these columns, so there is nothing meaningful to restore.
    pass
