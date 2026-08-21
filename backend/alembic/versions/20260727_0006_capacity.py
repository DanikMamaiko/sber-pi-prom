"""PI-cycle capacity members and calculations.

Revision ID: 20260727_0006
Revises: 20260727_0005
Create Date: 2026-07-27
"""

from alembic import op

revision = "20260727_0006"
down_revision = "20260727_0005"
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
        "capacity_initialized BOOLEAN NOT NULL DEFAULT FALSE"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_cycle_capacity_members_team_sort "
        "ON pi_cycle_capacity_members (cycle_id, team_id, sort_order)"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("DROP INDEX IF EXISTS ix_cycle_capacity_members_team_sort")
    op.execute("DROP TABLE IF EXISTS pi_cycle_capacity_members")
    op.execute("ALTER TABLE pi_cycles DROP COLUMN IF EXISTS capacity_initialized")
