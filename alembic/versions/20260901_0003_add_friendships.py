"""Add owner-scoped friendships and backfill expense participants.

Revision ID: 20260901_0003
Revises: 20260901_0002
"""

import sqlalchemy as sa

from alembic import op

revision = "20260901_0003"
down_revision = "20260901_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "friendships",
        sa.Column("owner_person_id", sa.Uuid(), nullable=False),
        sa.Column("friend_person_id", sa.Uuid(), nullable=False),
        sa.Column("source", sa.String(length=7), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
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
            "owner_person_id <> friend_person_id", name="ck_friendship_not_self"
        ),
        sa.ForeignKeyConstraint(
            ["friend_person_id"], ["persons.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["owner_person_id"], ["user_accounts.person_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("owner_person_id", "friend_person_id"),
    )
    op.create_index(
        "ix_friendships_friend_person_id",
        "friendships",
        ["friend_person_id"],
    )
    op.execute(
        """
        INSERT INTO friendships (
            owner_person_id,
            friend_person_id,
            source,
            created_at,
            updated_at
        )
        SELECT DISTINCT
            expenses.creator_person_id,
            expense_splits.person_id,
            'expense',
            CURRENT_TIMESTAMP,
            CURRENT_TIMESTAMP
        FROM expenses
        JOIN expense_splits ON expense_splits.expense_id = expenses.id
        WHERE expenses.creator_person_id <> expense_splits.person_id
        ON CONFLICT (owner_person_id, friend_person_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index("ix_friendships_friend_person_id", table_name="friendships")
    op.drop_table("friendships")
