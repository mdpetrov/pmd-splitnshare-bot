"""Persist active conversations and unfinished expense drafts.

Revision ID: 20260911_0011
Revises: 20260908_0010
"""

import sqlalchemy as sa

from alembic import op

revision = "20260911_0011"
down_revision = "20260908_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create durable FSM sessions and independent expense snapshots."""
    op.create_table(
        "conversation_states",
        sa.Column("key", sa.String(512), primary_key=True),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("state", sa.String(100), nullable=True),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_conversation_states_telegram_user_id", "conversation_states", ["telegram_user_id"]
    )
    op.create_table(
        "expense_drafts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("conversation_key", sa.String(512),
                  sa.ForeignKey("conversation_states.key", ondelete="CASCADE"), nullable=False),
        sa.Column("state", sa.String(100), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_expense_drafts_conversation_key", "expense_drafts", ["conversation_key"])


def downgrade() -> None:
    """Remove saved drafts and conversation state without changing the ledger."""
    op.drop_table("expense_drafts")
    op.drop_table("conversation_states")
