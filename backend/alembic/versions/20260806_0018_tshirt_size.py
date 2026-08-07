"""Add tshirt_size to backlog_items and initiatives.

«Размер майки» (T-shirt sizing): XS / S / M / L / XL / Megalodon. Поле кумулятивно:
для существующих строк tshirt_size = '' (нет значения).

Revision ID: 20260806_0018
Revises: 20260805_0017
Create Date: 2026-08-06
"""

from alembic import op


revision = "20260806_0018"
down_revision = "20260805_0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(
        "ALTER TABLE backlog_items "
        "ADD COLUMN IF NOT EXISTS tshirt_size VARCHAR(40) NOT NULL DEFAULT ''"
    )
    op.execute(
        "ALTER TABLE initiatives "
        "ADD COLUMN IF NOT EXISTS tshirt_size VARCHAR(40) NOT NULL DEFAULT ''"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("ALTER TABLE initiatives DROP COLUMN IF EXISTS tshirt_size")
    op.execute("ALTER TABLE backlog_items DROP COLUMN IF EXISTS tshirt_size")
