"""Store the normalized Jira source snapshot for imported backlog items.

Revision ID: 20260908_0026
Revises: 20260807_0025
Create Date: 2026-09-08
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260908_0026"
down_revision = "20260807_0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("backlog_items")
    }
    if "jira_issue_data" not in columns:
        op.add_column(
            "backlog_items",
            sa.Column(
                "jira_issue_data",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
        )


def downgrade() -> None:
    op.drop_column("backlog_items", "jira_issue_data")
