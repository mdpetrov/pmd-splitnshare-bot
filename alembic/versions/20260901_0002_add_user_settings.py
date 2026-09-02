"""Add per-user currency and language settings.

Revision ID: 20260901_0002
Revises: 20260824_0001
"""

import sqlalchemy as sa

from alembic import op

revision = "20260901_0002"
down_revision = "20260824_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create user settings and backfill defaults for existing accounts."""
    op.create_table(
        "user_settings",
        sa.Column("person_id", sa.Uuid(), nullable=False),
        sa.Column("default_currency", sa.String(length=3), nullable=False),
        sa.Column("language", sa.String(length=2), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(default_currency) = 3",
            name="ck_user_settings_currency_length",
        ),
        sa.ForeignKeyConstraint(
            ["person_id"], ["user_accounts.person_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("person_id"),
    )


def downgrade() -> None:
    """Remove the user-settings table and its constraints."""
    op.drop_table("user_settings")
