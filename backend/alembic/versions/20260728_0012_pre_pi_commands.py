"""Normalize Pre PI attraction requests and canonical block order.

Revision ID: 20260728_0012
Revises: 20260728_0011
Create Date: 2026-07-28
"""

from alembic import op


revision = "20260728_0012"
down_revision = "20260728_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from app.db.base import Base
    import app.models  # noqa: F401

    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)
    if bind.dialect.name != "postgresql":
        return

    # Only exact, valid historical references are migrated. The former JSONB
    # column is intentionally retained so no malformed user value is erased;
    # repairing such rows belongs in an explicit audited data migration.
    op.execute(
        """
        INSERT INTO initiative_attractions (
            id, executor_id, issue_key, target_initiative_id, target_team_id,
            sprint_index, approval_status, sort_order
        )
        SELECT md5(executor.id::text || target.id::text || target_team.id::text ||
                   (entry.value->>'sprint_index'))::uuid,
               executor.id, target.issue_key, target.id, target_team.id,
               (entry.value->>'sprint_index')::integer,
               CASE WHEN target.agreed THEN 'approved' ELSE 'pending' END,
               entry.ordinality - 1
        FROM initiative_executors AS executor
        JOIN initiatives AS source ON source.id = executor.initiative_id
        CROSS JOIN LATERAL jsonb_array_elements(executor.attractions)
             WITH ORDINALITY AS entry(value, ordinality)
        JOIN initiatives AS target
          ON target.cycle_id = source.cycle_id
         AND target.issue_key = entry.value->>'issue_key'
        JOIN teams AS target_team ON target_team.name = entry.value->>'team'
        JOIN pi_cycle_teams AS cycle_team
          ON cycle_team.cycle_id = source.cycle_id
         AND cycle_team.team_id = target_team.id
        WHERE jsonb_typeof(executor.attractions) = 'array'
          AND entry.value ? 'issue_key'
          AND entry.value ? 'team'
          AND entry.value ? 'sprint_index'
          AND (entry.value->>'sprint_index') ~ '^[0-9]+$'
          AND target.id <> source.id
          AND (SELECT count(*) FROM teams AS candidate
               JOIN pi_cycle_teams AS candidate_cycle
                 ON candidate_cycle.team_id = candidate.id
                AND candidate_cycle.cycle_id = source.cycle_id
               WHERE candidate.name = entry.value->>'team') = 1
        ON CONFLICT ON CONSTRAINT uq_initiative_attraction_target DO NOTHING
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_initiative_attractions_executor_sort "
        "ON initiative_attractions (executor_id, sort_order)"
    )
    op.execute(
        "WITH ranked AS ("
        " SELECT id, row_number() OVER (PARTITION BY cycle_id, pre_planned "
        " ORDER BY sort_order, created_at, id) - 1 AS position FROM initiatives"
        ") UPDATE initiatives AS target SET sort_order = ranked.position "
        "FROM ranked WHERE target.id = ranked.id"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_initiative_attractions_executor_sort")
    op.drop_table("initiative_attractions")
