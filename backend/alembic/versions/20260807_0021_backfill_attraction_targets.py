"""Create target-team Pre PI projections for saved attraction requests.

Revision ID: 20260807_0021
Revises: 20260807_0020
Create Date: 2026-08-07
"""

from alembic import op


revision = "20260807_0021"
down_revision = "20260807_0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute(
        """
        UPDATE initiative_attractions AS attraction
        SET target_initiative_id = target.id
        FROM initiative_executors AS executor,
             initiatives AS source,
             initiatives AS target
        WHERE attraction.target_initiative_id IS NULL
          AND executor.id = attraction.executor_id
          AND source.id = executor.initiative_id
          AND target.cycle_id = source.cycle_id
          AND lower(target.issue_key) = lower(attraction.issue_key)
          AND (target.owner_team_id IS NULL
               OR target.owner_team_id = attraction.target_team_id)
        """
    )
    op.execute(
        """
        WITH candidates AS (
            SELECT DISTINCT ON (source.cycle_id, lower(attraction.issue_key))
                   md5(source.cycle_id::text || ':' ||
                       lower(attraction.issue_key))::uuid AS id,
                   source.cycle_id,
                   attraction.issue_key,
                   attraction.target_team_id,
                   source.owner_team_id AS source_owner_team_id,
                   attraction.sprint_index
            FROM initiative_attractions AS attraction
            JOIN initiative_executors AS executor
              ON executor.id = attraction.executor_id
            JOIN initiatives AS source
              ON source.id = executor.initiative_id
            WHERE attraction.target_initiative_id IS NULL
              AND NOT EXISTS (
                  SELECT 1
                  FROM initiatives AS existing
                  WHERE existing.cycle_id = source.cycle_id
                    AND lower(existing.issue_key) = lower(attraction.issue_key)
              )
            ORDER BY source.cycle_id, lower(attraction.issue_key),
                     attraction.sort_order, attraction.id
        ), ordered AS (
            SELECT candidates.*,
                   coalesce((
                       SELECT max(existing.sort_order) + 1
                       FROM initiatives AS existing
                       WHERE existing.cycle_id = candidates.cycle_id
                   ), 0)
                   + row_number() OVER (
                       PARTITION BY candidates.cycle_id
                       ORDER BY lower(candidates.issue_key)
                   ) - 1 AS target_sort_order
            FROM candidates
        )
        INSERT INTO initiatives (
            id, cycle_id, issue_key, title, description, product,
            owner_team_id, initiative_type, tshirt_size, status,
            goal_text, metric, current_value, target_value, hypothesis,
            redesign, customer_priority, team_priority, estimate, comment,
            generated_from_attraction, pre_planned, on_board, agreed, tags,
            sprint_index, week_index, sort_order, board_sort_order
        )
        SELECT id, cycle_id, issue_key, issue_key, '', '',
               source_owner_team_id, '', '',
               'backlog',
               '', '', '', '', '', '', '', '', '', '',
               TRUE, FALSE, FALSE, FALSE, '[]'::jsonb,
               sprint_index, NULL, target_sort_order, 0
        FROM ordered
        ON CONFLICT (cycle_id, issue_key) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO initiative_executors (
            id, initiative_id, team_id, effort_by_competency,
            attractions, sort_order
        )
        SELECT DISTINCT ON (initiative.id)
               md5(initiative.id::text || '_executor')::uuid,
               initiative.id, attraction.target_team_id, '{}'::jsonb,
               '[]'::jsonb, 0
        FROM initiatives AS initiative
        JOIN initiative_attractions AS attraction ON TRUE
        JOIN initiative_executors AS source_executor
          ON source_executor.id = attraction.executor_id
        JOIN initiatives AS source
          ON source.id = source_executor.initiative_id
         AND source.cycle_id = initiative.cycle_id
         AND lower(attraction.issue_key) = lower(initiative.issue_key)
        WHERE initiative.generated_from_attraction
          AND NOT EXISTS (
              SELECT 1
              FROM initiative_executors AS executor
              WHERE executor.initiative_id = initiative.id
          )
        ORDER BY initiative.id, attraction.sort_order, attraction.id
        ON CONFLICT DO NOTHING
        """
    )
    op.execute(
        """
        UPDATE initiative_attractions AS attraction
        SET target_initiative_id = target.id
        FROM initiative_executors AS executor,
             initiatives AS source,
             initiatives AS target
        WHERE attraction.target_initiative_id IS NULL
          AND executor.id = attraction.executor_id
          AND source.id = executor.initiative_id
          AND target.cycle_id = source.cycle_id
          AND lower(target.issue_key) = lower(attraction.issue_key)
          AND target.owner_team_id = attraction.target_team_id
        """
    )


def downgrade() -> None:
    # Generated targets can already be edited or published by users. A downgrade
    # must not erase such business data; the nullable links remain valid on 0020.
    pass
