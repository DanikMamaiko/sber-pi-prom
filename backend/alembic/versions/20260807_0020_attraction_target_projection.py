"""Mark initiatives generated as attraction target projections.

Revision ID: 20260807_0020
Revises: 20260807_0019
Create Date: 2026-08-07
"""

from alembic import op


revision = "20260807_0020"
down_revision = "20260807_0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(
        "ALTER TABLE initiatives "
        "ADD COLUMN IF NOT EXISTS generated_from_attraction BOOLEAN NOT NULL DEFAULT FALSE"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(
        "ALTER TABLE initiatives DROP COLUMN IF EXISTS generated_from_attraction"
    )
