"""Add event_type discriminator and event_end_date to pi_events.

Lets a PI timeline event (ПИР) carry a date range and introduces a second
event kind — regression testing («регрессионное тестирование») — via a
discriminator column. Existing rows are PIRs by default; event_end_date is
NULL for single-day events (end == event_date).

Revision ID: 20260805_0017
Revises: 20260805_0016
Create Date: 2026-08-05
"""

from alembic import op


revision = "20260805_0017"
down_revision = "20260805_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(
        "ALTER TABLE pi_events ADD COLUMN IF NOT EXISTS "
        "event_type VARCHAR(20) NOT NULL DEFAULT 'pir'"
    )
    op.execute("ALTER TABLE pi_events ADD COLUMN IF NOT EXISTS event_end_date DATE")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("ALTER TABLE pi_events DROP COLUMN IF EXISTS event_end_date")
    op.execute("ALTER TABLE pi_events DROP COLUMN IF EXISTS event_type")
