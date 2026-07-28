"""Add aggregate versions for optimistic locking.

Revision ID: 20260728_0010
Revises: 20260728_0009
Create Date: 2026-07-28
"""

from alembic import op


revision = "20260728_0010"
down_revision = "20260728_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(
        "ALTER TABLE pi_cycles ADD COLUMN IF NOT EXISTS "
        "version INTEGER NOT NULL DEFAULT 0"
    )
    op.execute(
        "ALTER TABLE backlog_board_state ADD COLUMN IF NOT EXISTS "
        "version INTEGER NOT NULL DEFAULT 0"
    )
    op.execute(
        "INSERT INTO backlog_board_state (id, initialized, version) "
        "VALUES (1, FALSE, 0) ON CONFLICT (id) DO NOTHING"
    )
    op.execute("ALTER TABLE pi_cycles ALTER COLUMN version DROP DEFAULT")
    op.execute("ALTER TABLE backlog_board_state ALTER COLUMN version DROP DEFAULT")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("ALTER TABLE backlog_board_state DROP COLUMN IF EXISTS version")
    op.execute("ALTER TABLE pi_cycles DROP COLUMN IF EXISTS version")
