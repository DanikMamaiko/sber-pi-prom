"""Normalized global backlog board.

Revision ID: 20260727_0002
Revises: 20260727_0001
Create Date: 2026-07-27
"""

from alembic import op

revision = "20260727_0002"
down_revision = "20260727_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from app.db.base import Base
    import app.models  # noqa: F401

    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)
    if bind.dialect.name != "postgresql":
        return

    op.execute("ALTER TABLE backlog_items ADD COLUMN IF NOT EXISTS tribe_id UUID NULL")
    op.execute(
        "ALTER TABLE backlog_items ADD COLUMN IF NOT EXISTS "
        "sort_order INTEGER NOT NULL DEFAULT 0"
    )
    op.execute(
        "ALTER TABLE backlog_items ADD COLUMN IF NOT EXISTS "
        "systems JSONB NOT NULL DEFAULT '[]'::jsonb"
    )
    op.execute(
        "ALTER TABLE backlog_items ADD COLUMN IF NOT EXISTS "
        "sent_to JSONB NOT NULL DEFAULT '[]'::jsonb"
    )
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'fk_backlog_items_tribe_id_tribes'
          ) THEN
            ALTER TABLE backlog_items
              ADD CONSTRAINT fk_backlog_items_tribe_id_tribes
              FOREIGN KEY (tribe_id) REFERENCES tribes(id) ON DELETE SET NULL;
          END IF;
        END $$
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_backlog_items_tribe_sort "
        "ON backlog_items (tribe_id, sort_order)"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_backlog_items_tribe_sort")
        op.execute(
            "ALTER TABLE backlog_items "
            "DROP CONSTRAINT IF EXISTS fk_backlog_items_tribe_id_tribes"
        )
        for column in ("sent_to", "systems", "sort_order", "tribe_id"):
            op.execute(f"ALTER TABLE backlog_items DROP COLUMN IF EXISTS {column}")
    op.execute("DROP TABLE IF EXISTS backlog_board_state")
