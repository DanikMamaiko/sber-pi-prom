"""Keep generated attraction targets in the target team's Pre PI backlog.

Revision ID: 20260807_0022
Revises: 20260807_0021
Create Date: 2026-08-07
"""

from alembic import op


revision = "20260807_0022"
down_revision = "20260807_0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(
        "UPDATE initiatives "
        "SET pre_planned = FALSE, status = 'backlog' "
        "WHERE generated_from_attraction = TRUE AND on_board = FALSE"
    )


def downgrade() -> None:
    # The source initiative's current planning state cannot be reconstructed
    # safely, so a downgrade leaves user-visible backlog placement unchanged.
    pass
