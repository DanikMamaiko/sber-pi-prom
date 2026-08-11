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
    op.add_column("work_items", sa.Column("planned_start_date", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("work_items", "planned_start_date")
