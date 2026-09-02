"""Store Telegram username snapshots for guests.

Revision ID: 20260901_0004
Revises: 20260901_0003
"""

import sqlalchemy as sa

from alembic import op

revision = "20260901_0004"
down_revision = "20260901_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add an optional suggested Telegram username to guest profiles."""
    op.add_column(
        "guest_profiles",
        sa.Column("suggested_username", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    """Remove suggested Telegram usernames from guest profiles."""
    op.drop_column("guest_profiles", "suggested_username")
