"""add school year

Revision ID: 20261011_000003
Revises: 20261011_000002
Create Date: 2026-10-11 15:00:00.000000

Periods repeat every school year, so grades get the school year they belong to (by the calendar
year it starts in: 2026 is 2026/27). Existing grades are assigned by their date, with the year
starting on September 1st. A period pinned in /settings now remembers its school year and expires
when a new one starts; pins made before this migration have no year and therefore expire at once.
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20261011_000003"
down_revision = "20261011_000002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("grades", sa.Column("school_year", sa.SmallInteger(), nullable=True))
    op.execute(
        """
        UPDATE grades SET school_year = CASE
            WHEN EXTRACT(MONTH FROM date) >= 9 THEN EXTRACT(YEAR FROM date)
            ELSE EXTRACT(YEAR FROM date) - 1
        END
        """
    )
    op.alter_column("grades", "school_year", nullable=False)
    op.create_index("ix_grades_user_year_period", "grades", ["user_id", "school_year", "period"])

    op.add_column("users", sa.Column("active_school_year", sa.SmallInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "active_school_year")
    op.drop_index("ix_grades_user_year_period", table_name="grades")
    op.drop_column("grades", "school_year")
