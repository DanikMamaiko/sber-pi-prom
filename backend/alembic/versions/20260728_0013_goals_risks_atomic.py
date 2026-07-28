"""Atomic goals and risks commands.

Revision ID: 20260728_0013
Revises: 20260728_0012
Create Date: 2026-07-28
"""

from alembic import op

revision = "20260728_0013"
down_revision = "20260728_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from app.db.base import Base
    import app.models  # noqa: F401

    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)
    if bind.dialect.name != "postgresql":
        return

    op.execute("ALTER TABLE pi_goals ADD COLUMN IF NOT EXISTS owner VARCHAR(220) NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE pi_goals ADD COLUMN IF NOT EXISTS business_value INTEGER")
    op.execute("ALTER TABLE pi_goals ADD COLUMN IF NOT EXISTS status VARCHAR(40) NOT NULL DEFAULT 'planned'")
    op.execute("ALTER TABLE pi_goals ADD COLUMN IF NOT EXISTS category VARCHAR(40) NOT NULL DEFAULT 'committed'")
    op.execute(
        """
        INSERT INTO pi_goal_initiatives (id, goal_id, initiative_id, sort_order)
        SELECT id, id, initiative_id, 0
        FROM pi_goals
        WHERE initiative_id IS NOT NULL
        ON CONFLICT DO NOTHING
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_pi_goal_initiatives_goal_sort "
        "ON pi_goal_initiatives (goal_id, sort_order)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_pi_goal_initiatives_initiative "
        "ON pi_goal_initiatives (initiative_id)"
    )

    op.execute("ALTER TABLE risks ADD COLUMN IF NOT EXISTS tribe_id UUID REFERENCES tribes(id)")
    op.execute("ALTER TABLE risks ADD COLUMN IF NOT EXISTS initiative_id UUID REFERENCES initiatives(id)")
    op.execute("ALTER TABLE risks ADD COLUMN IF NOT EXISTS probability INTEGER NOT NULL DEFAULT 1")
    op.execute("ALTER TABLE risks ADD COLUMN IF NOT EXISTS impact_level INTEGER NOT NULL DEFAULT 1")
    op.execute("ALTER TABLE risks ADD COLUMN IF NOT EXISTS criticality INTEGER NOT NULL DEFAULT 1")
    op.execute("ALTER TABLE risks ADD COLUMN IF NOT EXISTS reaction_due_date DATE")
    op.execute("ALTER TABLE risks ADD COLUMN IF NOT EXISTS treatment_plan TEXT NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE risks ADD COLUMN IF NOT EXISTS status VARCHAR(40) NOT NULL DEFAULT 'open'")
    op.execute("ALTER TABLE risks ADD COLUMN IF NOT EXISTS roam VARCHAR(20)")
    op.execute(
        "UPDATE risks SET criticality = GREATEST(1, probability) * GREATEST(1, impact_level)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_risks_cycle_link_sort "
        "ON risks (cycle_id, tribe_id, team_id, initiative_id, sort_order)"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("DROP INDEX IF EXISTS ix_risks_cycle_link_sort")
    op.execute("ALTER TABLE risks DROP COLUMN IF EXISTS roam")
    op.execute("ALTER TABLE risks DROP COLUMN IF EXISTS status")
    op.execute("ALTER TABLE risks DROP COLUMN IF EXISTS treatment_plan")
    op.execute("ALTER TABLE risks DROP COLUMN IF EXISTS reaction_due_date")
    op.execute("ALTER TABLE risks DROP COLUMN IF EXISTS criticality")
    op.execute("ALTER TABLE risks DROP COLUMN IF EXISTS impact_level")
    op.execute("ALTER TABLE risks DROP COLUMN IF EXISTS probability")
    op.execute("ALTER TABLE risks DROP COLUMN IF EXISTS initiative_id")
    op.execute("ALTER TABLE risks DROP COLUMN IF EXISTS tribe_id")
    op.execute("DROP INDEX IF EXISTS ix_pi_goal_initiatives_initiative")
    op.execute("DROP INDEX IF EXISTS ix_pi_goal_initiatives_goal_sort")
    op.execute("DROP TABLE IF EXISTS pi_goal_initiatives")
    op.execute("ALTER TABLE pi_goals DROP COLUMN IF EXISTS category")
    op.execute("ALTER TABLE pi_goals DROP COLUMN IF EXISTS status")
    op.execute("ALTER TABLE pi_goals DROP COLUMN IF EXISTS business_value")
    op.execute("ALTER TABLE pi_goals DROP COLUMN IF EXISTS owner")
