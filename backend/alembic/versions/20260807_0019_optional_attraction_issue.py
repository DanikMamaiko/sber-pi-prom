"""Allow attraction requests for Issue IDs outside the current PI.

Revision ID: 20260807_0019
Revises: 20260806_0018
Create Date: 2026-08-07
"""

from alembic import op


revision = "20260807_0019"
down_revision = "20260806_0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(
        "ALTER TABLE initiative_attractions "
        "ADD COLUMN IF NOT EXISTS issue_key VARCHAR(80)"
    )
    op.execute(
        "UPDATE initiative_attractions AS attraction "
        "SET issue_key = initiative.issue_key "
        "FROM initiatives AS initiative "
        "WHERE attraction.target_initiative_id = initiative.id "
        "AND (attraction.issue_key IS NULL OR attraction.issue_key = '')"
    )
    op.execute(
        "ALTER TABLE initiative_attractions ALTER COLUMN issue_key SET NOT NULL"
    )
    op.execute(
        "ALTER TABLE initiative_attractions "
        "DROP CONSTRAINT IF EXISTS initiative_attractions_target_initiative_id_fkey"
    )
    op.execute(
        "ALTER TABLE initiative_attractions "
        "ALTER COLUMN target_initiative_id DROP NOT NULL"
    )
    op.execute(
        "ALTER TABLE initiative_attractions "
        "ADD CONSTRAINT initiative_attractions_target_initiative_id_fkey "
        "FOREIGN KEY (target_initiative_id) REFERENCES initiatives(id) ON DELETE SET NULL"
    )
    op.execute(
        "ALTER TABLE initiative_attractions "
        "DROP CONSTRAINT IF EXISTS uq_initiative_attraction_target"
    )
    op.execute(
        "ALTER TABLE initiative_attractions "
        "ADD CONSTRAINT uq_initiative_attraction_target "
        "UNIQUE (executor_id, issue_key, target_team_id, sprint_index)"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(
        "DELETE FROM initiative_attractions WHERE target_initiative_id IS NULL"
    )
    op.execute(
        "ALTER TABLE initiative_attractions "
        "DROP CONSTRAINT IF EXISTS uq_initiative_attraction_target"
    )
    op.execute(
        "ALTER TABLE initiative_attractions "
        "ADD CONSTRAINT uq_initiative_attraction_target "
        "UNIQUE (executor_id, target_initiative_id, target_team_id, sprint_index)"
    )
    op.execute(
        "ALTER TABLE initiative_attractions "
        "DROP CONSTRAINT IF EXISTS initiative_attractions_target_initiative_id_fkey"
    )
    op.execute(
        "ALTER TABLE initiative_attractions "
        "ALTER COLUMN target_initiative_id SET NOT NULL"
    )
    op.execute(
        "ALTER TABLE initiative_attractions "
        "ADD CONSTRAINT initiative_attractions_target_initiative_id_fkey "
        "FOREIGN KEY (target_initiative_id) REFERENCES initiatives(id) ON DELETE CASCADE"
    )
    op.execute(
        "ALTER TABLE initiative_attractions DROP COLUMN IF EXISTS issue_key"
    )
