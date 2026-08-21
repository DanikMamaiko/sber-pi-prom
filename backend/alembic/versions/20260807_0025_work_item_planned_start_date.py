"""Add exact planned start date to work items.

Revision ID: 20260807_0025
Revises: 20260807_0024
Create Date: 2026-08-07
"""

from alembic import op
import sqlalchemy as sa


revision = "20260807_0025"
down_revision = "20260807_0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Revision 0001 builds a fresh database from the current SQLAlchemy metadata.
    # Therefore a new installation can already contain this column before Alembic
    # reaches 0025, while an older installation still needs it to be added here.
    columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("work_items")
    }
    if "planned_start_date" not in columns:
        op.add_column(
            "work_items",
            sa.Column("planned_start_date", sa.Date(), nullable=True),
        )


def downgrade() -> None:
    op.drop_column("work_items", "planned_start_date")
