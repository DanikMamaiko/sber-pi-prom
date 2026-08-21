"""Normalized Program Board connections and geometry.

Revision ID: 20260727_0007
Revises: 20260727_0006
Create Date: 2026-07-27
"""

from alembic import op

revision = "20260727_0007"
down_revision = "20260727_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from app.db.base import Base
    import app.models  # noqa: F401

    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)
    if bind.dialect.name != "postgresql":
        return
    op.execute(
        "ALTER TABLE pi_cycles ADD COLUMN IF NOT EXISTS "
        "program_board_initialized BOOLEAN NOT NULL DEFAULT FALSE"
    )
    op.execute("ALTER TABLE board_connections ADD COLUMN IF NOT EXISTS client_uid VARCHAR(80)")
    op.execute(
        "UPDATE board_connections SET client_uid = 'connection-' || id::text "
        "WHERE client_uid IS NULL OR client_uid = ''"
    )
    op.execute("ALTER TABLE board_connections ALTER COLUMN client_uid SET NOT NULL")
    op.execute("ALTER TABLE board_connections ADD COLUMN IF NOT EXISTS bend_dx DOUBLE PRECISION")
    op.execute("ALTER TABLE board_connections ADD COLUMN IF NOT EXISTS bend_dy DOUBLE PRECISION")
    op.execute(
        "ALTER TABLE board_connections ADD COLUMN IF NOT EXISTS "
        "sort_order INTEGER NOT NULL DEFAULT 0"
    )
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname = 'uq_board_connection_client_uid'
          ) THEN
            ALTER TABLE board_connections
              ADD CONSTRAINT uq_board_connection_client_uid UNIQUE (cycle_id, client_uid);
          END IF;
        END $$
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_board_connections_cycle_sort "
        "ON board_connections (cycle_id, sort_order)"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("DROP INDEX IF EXISTS ix_board_connections_cycle_sort")
    op.execute(
        "ALTER TABLE board_connections DROP CONSTRAINT IF EXISTS "
        "uq_board_connection_client_uid"
    )
    for column in ("sort_order", "bend_dy", "bend_dx", "client_uid"):
        op.execute(f"ALTER TABLE board_connections DROP COLUMN IF EXISTS {column}")
    op.execute("ALTER TABLE pi_cycles DROP COLUMN IF EXISTS program_board_initialized")
