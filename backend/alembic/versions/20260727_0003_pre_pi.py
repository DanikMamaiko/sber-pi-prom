"""Normalized Pre PI Planning aggregate.

Revision ID: 20260727_0003
Revises: 20260727_0002
Create Date: 2026-07-27
"""

from alembic import op

revision = "20260727_0003"
down_revision = "20260727_0002"
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
        "initiatives_initialized BOOLEAN NOT NULL DEFAULT FALSE"
    )
    op.execute(
        "ALTER TABLE initiatives ADD COLUMN IF NOT EXISTS "
        "customer_priority VARCHAR(40) NOT NULL DEFAULT ''"
    )
    op.execute(
        "ALTER TABLE initiatives ADD COLUMN IF NOT EXISTS "
        "team_priority VARCHAR(40) NOT NULL DEFAULT ''"
    )
    op.execute(
        "ALTER TABLE initiatives ADD COLUMN IF NOT EXISTS "
        "estimate VARCHAR(120) NOT NULL DEFAULT ''"
    )
    op.execute(
        "ALTER TABLE initiatives ADD COLUMN IF NOT EXISTS "
        "comment TEXT NOT NULL DEFAULT ''"
    )
    for column in ("pre_planned", "on_board", "agreed"):
        op.execute(
            f"ALTER TABLE initiatives ADD COLUMN IF NOT EXISTS "
            f"{column} BOOLEAN NOT NULL DEFAULT FALSE"
        )
    op.execute(
        "ALTER TABLE initiatives ADD COLUMN IF NOT EXISTS "
        "tags JSONB NOT NULL DEFAULT '[]'::jsonb"
    )
    op.execute(
        "ALTER TABLE initiative_executors ADD COLUMN IF NOT EXISTS "
        "attractions JSONB NOT NULL DEFAULT '[]'::jsonb"
    )
    op.execute(
        "ALTER TABLE initiative_executors ADD COLUMN IF NOT EXISTS "
        "sort_order INTEGER NOT NULL DEFAULT 0"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_initiatives_cycle_sort "
        "ON initiatives (cycle_id, sort_order)"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("DROP INDEX IF EXISTS ix_initiatives_cycle_sort")
    for column in ("sort_order", "attractions"):
        op.execute(
            f"ALTER TABLE initiative_executors DROP COLUMN IF EXISTS {column}"
        )
    for column in (
        "tags",
        "agreed",
        "on_board",
        "pre_planned",
        "comment",
        "estimate",
        "team_priority",
        "customer_priority",
    ):
        op.execute(f"ALTER TABLE initiatives DROP COLUMN IF EXISTS {column}")
    op.execute(
        "ALTER TABLE pi_cycles DROP COLUMN IF EXISTS initiatives_initialized"
    )
