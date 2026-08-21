"""Add canonical order to backlog executors.

Revision ID: 20260728_0011
Revises: 20260728_0010
Create Date: 2026-07-28
"""

from alembic import op


revision = "20260728_0011"
down_revision = "20260728_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(
        "ALTER TABLE backlog_executors ADD COLUMN IF NOT EXISTS "
        "sort_order INTEGER NOT NULL DEFAULT 0"
    )
    op.execute(
        "WITH ranked AS ("
        " SELECT id, row_number() OVER (PARTITION BY backlog_item_id ORDER BY id) - 1 AS position"
        " FROM backlog_executors"
        ") UPDATE backlog_executors AS target SET sort_order = ranked.position"
        " FROM ranked WHERE target.id = ranked.id"
    )
    op.execute("ALTER TABLE backlog_executors ALTER COLUMN sort_order DROP DEFAULT")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_backlog_executors_item_sort "
        "ON backlog_executors (backlog_item_id, sort_order)"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("DROP INDEX IF EXISTS ix_backlog_executors_item_sort")
    op.execute("ALTER TABLE backlog_executors DROP COLUMN IF EXISTS sort_order")
