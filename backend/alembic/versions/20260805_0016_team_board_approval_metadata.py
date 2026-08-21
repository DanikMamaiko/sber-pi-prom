"""Track team-board approval author and timestamp.

Revision ID: 20260805_0016
Revises: 20260729_0015
Create Date: 2026-08-05
"""

from alembic import op


revision = "20260805_0016"
down_revision = "20260729_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("ALTER TABLE initiatives ADD COLUMN IF NOT EXISTS approved_by VARCHAR(200)")
    op.execute("ALTER TABLE initiatives ADD COLUMN IF NOT EXISTS approved_at TIMESTAMPTZ")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("ALTER TABLE initiatives DROP COLUMN IF EXISTS approved_at")
    op.execute("ALTER TABLE initiatives DROP COLUMN IF EXISTS approved_by")
