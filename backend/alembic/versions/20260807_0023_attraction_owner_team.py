"""Keep the source team as owner of generated attraction tasks.

Revision ID: 20260807_0023
Revises: 20260807_0022
Create Date: 2026-08-07
"""

from alembic import op


revision = "20260807_0023"
down_revision = "20260807_0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(
        """
        WITH source_owners AS (
            SELECT DISTINCT ON (target.id)
                   target.id AS target_id,
                   source.owner_team_id
            FROM initiatives AS target
            JOIN initiative_attractions AS attraction
              ON attraction.target_initiative_id = target.id
            JOIN initiative_executors AS source_executor
              ON source_executor.id = attraction.executor_id
            JOIN initiatives AS source
              ON source.id = source_executor.initiative_id
            WHERE target.generated_from_attraction = TRUE
              AND source.owner_team_id IS NOT NULL
            ORDER BY target.id, attraction.sort_order, attraction.id
        )
        UPDATE initiatives AS target
        SET owner_team_id = source_owners.owner_team_id
        FROM source_owners
        WHERE target.id = source_owners.target_id
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(
        """
        UPDATE initiatives AS target
        SET owner_team_id = executor.team_id
        FROM initiative_executors AS executor
        WHERE target.generated_from_attraction = TRUE
          AND executor.initiative_id = target.id
          AND executor.sort_order = 0
        """
    )
