"""Normalized team board stories and work items.

Revision ID: 20260727_0005
Revises: 20260727_0004
Create Date: 2026-07-27
"""

from alembic import op

revision = "20260727_0005"
down_revision = "20260727_0004"
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
        "boards_initialized BOOLEAN NOT NULL DEFAULT FALSE"
    )
    op.execute(
        "ALTER TABLE initiatives ADD COLUMN IF NOT EXISTS "
        "board_sort_order INTEGER NOT NULL DEFAULT 0"
    )
    op.execute("ALTER TABLE stories ADD COLUMN IF NOT EXISTS client_uid VARCHAR(80)")
    op.execute(
        "UPDATE stories SET client_uid = 'story-' || id::text "
        "WHERE client_uid IS NULL OR client_uid = ''"
    )
    op.execute("ALTER TABLE stories ALTER COLUMN client_uid SET NOT NULL")
    op.execute(
        "ALTER TABLE stories ADD COLUMN IF NOT EXISTS "
        "board_sort_order INTEGER NOT NULL DEFAULT 0"
    )
    op.execute("ALTER TABLE work_items ADD COLUMN IF NOT EXISTS client_uid VARCHAR(80)")
    op.execute(
        "UPDATE work_items SET client_uid = 'work-' || id::text "
        "WHERE client_uid IS NULL OR client_uid = ''"
    )
    op.execute("ALTER TABLE work_items ALTER COLUMN client_uid SET NOT NULL")
    op.execute(
        "ALTER TABLE work_items ADD COLUMN IF NOT EXISTS "
        "sort_order INTEGER NOT NULL DEFAULT 0"
    )
    op.execute(
        "ALTER TABLE work_items ADD COLUMN IF NOT EXISTS "
        "board_sort_order INTEGER NOT NULL DEFAULT 0"
    )
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_story_client_uid') THEN
            ALTER TABLE stories ADD CONSTRAINT uq_story_client_uid UNIQUE (initiative_id, client_uid);
          END IF;
          IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_work_item_client_uid') THEN
            ALTER TABLE work_items ADD CONSTRAINT uq_work_item_client_uid UNIQUE (initiative_id, client_uid);
          END IF;
        END $$
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_stories_initiative_board_sort "
        "ON stories (initiative_id, board_sort_order)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_work_items_initiative_board_sort "
        "ON work_items (initiative_id, board_sort_order)"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("DROP INDEX IF EXISTS ix_work_items_initiative_board_sort")
    op.execute("DROP INDEX IF EXISTS ix_stories_initiative_board_sort")
    op.execute("ALTER TABLE work_items DROP CONSTRAINT IF EXISTS uq_work_item_client_uid")
    op.execute("ALTER TABLE stories DROP CONSTRAINT IF EXISTS uq_story_client_uid")
    for column in ("board_sort_order", "sort_order", "client_uid"):
        op.execute(f"ALTER TABLE work_items DROP COLUMN IF EXISTS {column}")
    for column in ("board_sort_order", "client_uid"):
        op.execute(f"ALTER TABLE stories DROP COLUMN IF EXISTS {column}")
    op.execute("ALTER TABLE initiatives DROP COLUMN IF EXISTS board_sort_order")
    op.execute("ALTER TABLE pi_cycles DROP COLUMN IF EXISTS boards_initialized")
