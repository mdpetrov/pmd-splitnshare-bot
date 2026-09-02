"""Add auditable balance settlements.

Revision ID: 20260902_0008
Revises: 20260902_0007
"""

import sqlalchemy as sa

from alembic import op

revision = "20260902_0008"
down_revision = "20260902_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create auditable settlement records and participant lookup indexes."""
    op.create_table(
        "settlements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("group_id", sa.Uuid(), nullable=True),
        sa.Column("recorded_by_person_id", sa.Uuid(), nullable=False),
        sa.Column("payer_person_id", sa.Uuid(), nullable=False),
        sa.Column("recipient_person_id", sa.Uuid(), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
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
            "amount_minor > 0", name="ck_settlement_positive_amount"
        ),
        sa.CheckConstraint(
            "length(currency) = 3", name="ck_settlement_currency_length"
        ),
        sa.CheckConstraint(
            "payer_person_id <> recipient_person_id",
            name="ck_settlement_distinct_people",
        ),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["payer_person_id"], ["persons.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["recipient_person_id"], ["persons.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["recorded_by_person_id"],
            ["user_accounts.person_id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_settlements_payer_currency",
        "settlements",
        ["payer_person_id", "currency"],
    )
    op.create_index(
        "ix_settlements_recipient_currency",
        "settlements",
        ["recipient_person_id", "currency"],
    )
    op.create_index(
        "ix_settlements_occurred_at_id",
        "settlements",
        ["occurred_at", "id"],
    )


def downgrade() -> None:
    """Drop settlement indexes and the settlement table."""
    op.drop_index("ix_settlements_occurred_at_id", table_name="settlements")
    op.drop_index("ix_settlements_recipient_currency", table_name="settlements")
    op.drop_index("ix_settlements_payer_currency", table_name="settlements")
    op.drop_table("settlements")
