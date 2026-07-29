"""Program Board atomic command constraints.

Revision ID: 20260729_0015
Revises: 20260729_0014
Create Date: 2026-07-29
"""

from alembic import op


revision = "20260729_0015"
down_revision = "20260729_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(
        """
        DELETE FROM board_connections duplicate
        USING board_connections keeper
        WHERE duplicate.cycle_id = keeper.cycle_id
          AND duplicate.source_kind = keeper.source_kind
          AND duplicate.source_id = keeper.source_id
          AND duplicate.target_kind = keeper.target_kind
          AND duplicate.target_id = keeper.target_id
          AND duplicate.id > keeper.id
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'uq_board_connection_directed_edge'
          ) THEN
            ALTER TABLE board_connections
              ADD CONSTRAINT uq_board_connection_directed_edge
              UNIQUE (cycle_id, source_kind, source_id, target_kind, target_id);
          END IF;
        END $$
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_initiatives_program_board_lane "
        "ON initiatives (cycle_id, on_board, sprint_index, board_sort_order)"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("DROP INDEX IF EXISTS ix_initiatives_program_board_lane")
    op.execute(
        "ALTER TABLE board_connections DROP CONSTRAINT IF EXISTS "
        "uq_board_connection_directed_edge"
    )
