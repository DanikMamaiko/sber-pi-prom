"""Harden team-board assignments and position constraints.

Revision ID: 20260729_0014
Revises: 20260728_0013
Create Date: 2026-07-29
"""

from alembic import op


revision = "20260729_0014"
down_revision = "20260728_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("ALTER TABLE work_items ADD COLUMN IF NOT EXISTS assignee_member_id UUID")
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'fk_work_items_assignee_member'
          ) THEN
            ALTER TABLE work_items
              ADD CONSTRAINT fk_work_items_assignee_member
              FOREIGN KEY (assignee_member_id)
              REFERENCES pi_cycle_capacity_members(id)
              ON DELETE SET NULL;
          END IF;
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname = 'ck_initiatives_week_index'
          ) THEN
            ALTER TABLE initiatives ADD CONSTRAINT ck_initiatives_week_index
              CHECK (week_index IS NULL OR week_index IN (0, 1));
          END IF;
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname = 'ck_stories_week_index'
          ) THEN
            ALTER TABLE stories ADD CONSTRAINT ck_stories_week_index
              CHECK (week_index IS NULL OR week_index IN (0, 1));
          END IF;
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname = 'ck_work_items_week_index'
          ) THEN
            ALTER TABLE work_items ADD CONSTRAINT ck_work_items_week_index
              CHECK (week_index IS NULL OR week_index IN (0, 1));
          END IF;
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname = 'ck_capacity_member_rate'
          ) THEN
            ALTER TABLE pi_cycle_capacity_members ADD CONSTRAINT ck_capacity_member_rate
              CHECK (rate >= 0 AND rate <= 1);
          END IF;
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname = 'ck_capacity_member_percentages'
          ) THEN
            ALTER TABLE pi_cycle_capacity_members ADD CONSTRAINT ck_capacity_member_percentages
              CHECK (
                ceremony_percent >= 0 AND ceremony_percent <= 100
                AND risk_percent >= 0 AND risk_percent <= 100
              );
          END IF;
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname = 'ck_capacity_member_efficiency'
          ) THEN
            ALTER TABLE pi_cycle_capacity_members ADD CONSTRAINT ck_capacity_member_efficiency
              CHECK (efficiency IS NULL OR (efficiency >= 0 AND efficiency <= 1));
          END IF;
        END $$
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_work_items_assignee_member "
        "ON work_items (assignee_member_id)"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("DROP INDEX IF EXISTS ix_work_items_assignee_member")
    for constraint, table in (
        ("ck_capacity_member_efficiency", "pi_cycle_capacity_members"),
        ("ck_capacity_member_percentages", "pi_cycle_capacity_members"),
        ("ck_capacity_member_rate", "pi_cycle_capacity_members"),
        ("ck_work_items_week_index", "work_items"),
        ("ck_stories_week_index", "stories"),
        ("ck_initiatives_week_index", "initiatives"),
        ("fk_work_items_assignee_member", "work_items"),
    ):
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {constraint}")
    op.execute("ALTER TABLE work_items DROP COLUMN IF EXISTS assignee_member_id")
