"""Add owner-specific friend aliases.

Revision ID: 20260901_0005
Revises: 20260901_0004
"""

import sqlalchemy as sa

from alembic import op

revision = "20260901_0005"
down_revision = "20260901_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "friendships",
        sa.Column("alias", sa.String(length=160), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("friendships", "alias")
