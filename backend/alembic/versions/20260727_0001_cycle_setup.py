"""Baseline schema and normalized PI-cycle setup.

Revision ID: 20260727_0001
Revises:
Create Date: 2026-07-27
"""

from alembic import op

revision = "20260727_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    from app.db.base import Base
    import app.models  # noqa: F401

    bind = op.get_bind()
    # This repository already had an MVP database created with create_all.
    # create_all makes this revision work for both that database and a fresh one.
    Base.metadata.create_all(bind=bind)
    if bind.dialect.name == "postgresql":
        op.execute(
            "ALTER TABLE pi_cycles ADD COLUMN IF NOT EXISTS "
            "snapshot JSONB NOT NULL DEFAULT '{}'::jsonb"
        )
        op.execute(
            "ALTER TABLE pi_cycles ADD COLUMN IF NOT EXISTS "
            "setup_initialized BOOLEAN NOT NULL DEFAULT FALSE"
        )
        op.execute(
            "ALTER TABLE pi_events ADD COLUMN IF NOT EXISTS "
            "sort_order INTEGER NOT NULL DEFAULT 0"
        )


def downgrade() -> None:
    bind = op.get_bind()
    for table_name in (
        "pi_cycle_team_competencies",
        "pi_cycle_tags",
        "pi_cycle_goal_options",
        "pi_cycle_teams",
    ):
        op.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE")
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE pi_events DROP COLUMN IF EXISTS sort_order")
        op.execute("ALTER TABLE pi_cycles DROP COLUMN IF EXISTS setup_initialized")
