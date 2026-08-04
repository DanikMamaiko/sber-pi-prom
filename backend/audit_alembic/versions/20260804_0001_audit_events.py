"""Create the append-only security audit event store.

Revision ID: 20260804_0001
Revises: None
Create Date: 2026-08-04
"""

from alembic import op
import sqlalchemy as sa


revision = "20260804_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_service", sa.String(length=200), nullable=False),
        sa.Column("source_component", sa.String(length=100), nullable=False),
        sa.Column("environment", sa.String(length=50), nullable=False),
        sa.Column("username", sa.String(length=200), nullable=True),
        sa.Column("auth_provider", sa.String(length=100), nullable=True),
        sa.Column("source_ip", sa.String(length=64), nullable=True),
        sa.Column("host_ip", sa.String(length=64), nullable=True),
        sa.Column("host_name", sa.String(length=255), nullable=False),
        sa.Column("operation_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("operation_finished_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_ms", sa.BigInteger(), nullable=False),
        sa.Column("action", sa.String(length=200), nullable=False),
        sa.Column("object_type", sa.String(length=100), nullable=False),
        sa.Column("object_id", sa.String(length=200), nullable=True),
        sa.Column("result", sa.String(length=20), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=True),
        sa.Column("http_method", sa.String(length=10), nullable=False),
        sa.Column("http_route", sa.String(length=500), nullable=False),
        sa.Column("http_path", sa.String(length=1000), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index("ix_audit_events_request_id", "audit_events", ["request_id"])
    op.create_index("ix_audit_events_occurred_at", "audit_events", ["occurred_at"])
    op.create_index(
        "ix_audit_events_username_occurred_at",
        "audit_events",
        ["username", "occurred_at"],
    )
    op.create_index(
        "ix_audit_events_action_occurred_at",
        "audit_events",
        ["action", "occurred_at"],
    )
    op.create_index(
        "ix_audit_events_object",
        "audit_events",
        ["object_type", "object_id"],
    )
    op.create_index(
        "ix_audit_events_result_occurred_at",
        "audit_events",
        ["result", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_table("audit_events")
