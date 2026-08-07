"""Allow attraction requests without a sprint.

Revision ID: 20260807_0024
Revises: 20260807_0023
Create Date: 2026-08-07
"""

from alembic import op


revision = "20260807_0024"
down_revision = "20260807_0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("ALTER TABLE initiative_attractions ALTER COLUMN sprint_index DROP NOT NULL")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(
        """
        UPDATE initiative_attractions
        SET sprint_index = target.sprint_index
        FROM initiatives AS target
        WHERE initiative_attractions.target_initiative_id = target.id
          AND initiative_attractions.sprint_index IS NULL
          AND target.sprint_index IS NOT NULL
        """
    )
    op.execute("DELETE FROM initiative_attractions WHERE sprint_index IS NULL")
    op.execute("ALTER TABLE initiative_attractions ALTER COLUMN sprint_index SET NOT NULL")
