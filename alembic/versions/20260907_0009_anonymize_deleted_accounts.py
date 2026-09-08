"""Allow Telegram identities to be removed from deleted accounts.

Revision ID: 20260907_0009
Revises: 20260902_0008
"""

import sqlalchemy as sa

from alembic import op

revision = "20260907_0009"
down_revision = "20260902_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Permit account anonymization while preserving referenced account rows."""
    with op.batch_alter_table("user_accounts") as batch_op:
        batch_op.alter_column(
            "telegram_user_id",
            existing_type=sa.BigInteger(),
            nullable=True,
        )


def downgrade() -> None:
    """Assign anonymous negative IDs before restoring the non-null constraint."""
    connection = op.get_bind()
    accounts = sa.table(
        "user_accounts",
        sa.column("person_id", sa.Uuid()),
        sa.column("telegram_user_id", sa.BigInteger()),
    )
    used_ids = set(
        connection.scalars(
            sa.select(accounts.c.telegram_user_id).where(
                accounts.c.telegram_user_id.is_not(None)
            )
        )
    )
    next_anonymous_id = -1
    deleted_person_ids = tuple(
        connection.scalars(
            sa.select(accounts.c.person_id).where(
                accounts.c.telegram_user_id.is_(None)
            )
        )
    )
    for person_id in deleted_person_ids:
        while next_anonymous_id in used_ids:
            next_anonymous_id -= 1
        connection.execute(
            accounts.update()
            .where(accounts.c.person_id == person_id)
            .values(telegram_user_id=next_anonymous_id)
        )
        used_ids.add(next_anonymous_id)
        next_anonymous_id -= 1

    with op.batch_alter_table("user_accounts") as batch_op:
        batch_op.alter_column(
            "telegram_user_id",
            existing_type=sa.BigInteger(),
            nullable=False,
        )
