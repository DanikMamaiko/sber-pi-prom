"""Normalized general and team risks.

Revision ID: 20260727_0008
Revises: 20260727_0007
Create Date: 2026-07-27
"""

from alembic import op

revision = "20260727_0008"
down_revision = "20260727_0007"
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
        "risks_initialized BOOLEAN NOT NULL DEFAULT FALSE"
    )
    op.execute("ALTER TABLE risks ADD COLUMN IF NOT EXISTS client_uid VARCHAR(80)")
    op.execute(
        "UPDATE risks SET client_uid = 'risk-' || id::text "
        "WHERE client_uid IS NULL OR client_uid = ''"
    )
    op.execute("ALTER TABLE risks ALTER COLUMN client_uid SET NOT NULL")
    op.execute(
        "ALTER TABLE risks ADD COLUMN IF NOT EXISTS "
        "sort_order INTEGER NOT NULL DEFAULT 0"
    )
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname = 'uq_cycle_risk_client_uid'
          ) THEN
            ALTER TABLE risks
              ADD CONSTRAINT uq_cycle_risk_client_uid UNIQUE (cycle_id, client_uid);
          END IF;
        END $$
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_risks_cycle_scope_team_sort "
        "ON risks (cycle_id, scope, team_id, sort_order)"
    )
    op.execute(
        "UPDATE pi_cycles SET risks_initialized = TRUE "
        "WHERE EXISTS (SELECT 1 FROM risks WHERE risks.cycle_id = pi_cycles.id)"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("DROP INDEX IF EXISTS ix_risks_cycle_scope_team_sort")
    op.execute("ALTER TABLE risks DROP CONSTRAINT IF EXISTS uq_cycle_risk_client_uid")
    op.execute("ALTER TABLE risks DROP COLUMN IF EXISTS sort_order")
    op.execute("ALTER TABLE risks DROP COLUMN IF EXISTS client_uid")
    op.execute("ALTER TABLE pi_cycles DROP COLUMN IF EXISTS risks_initialized")
