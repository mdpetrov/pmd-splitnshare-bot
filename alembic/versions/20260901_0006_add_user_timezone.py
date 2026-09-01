"""Add a timezone to user settings.

Revision ID: 20260901_0006
Revises: 20260901_0005
"""

import sqlalchemy as sa

from alembic import op

revision = "20260901_0006"
down_revision = "20260901_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_settings",
        sa.Column("timezone", sa.String(length=64), nullable=True),
    )
    # Existing users keep their current experience. A NULL value is reserved for
    # newly created accounts that have not completed timezone onboarding yet.
    op.execute("UPDATE user_settings SET timezone = 'UTC'")


def downgrade() -> None:
    op.drop_column("user_settings", "timezone")
