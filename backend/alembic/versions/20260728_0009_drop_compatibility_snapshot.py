"""Drop the retired PI cycle compatibility snapshot.

Revision ID: 20260728_0009
Revises: 20260727_0008
Create Date: 2026-07-28
"""

from alembic import op


revision = "20260728_0009"
down_revision = "20260727_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("ALTER TABLE pi_cycles DROP COLUMN IF EXISTS snapshot")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    # A downgrade restores only the schema. Historical JSON content must be
    # restored from the release-A backup when it is actually required.
    op.execute(
        "ALTER TABLE pi_cycles ADD COLUMN IF NOT EXISTS "
        "snapshot JSONB NOT NULL DEFAULT '{}'::jsonb"
    )
    op.execute("ALTER TABLE pi_cycles ALTER COLUMN snapshot DROP DEFAULT")
