"""Add the real-world date and time of an expense.

Revision ID: 20260902_0007
Revises: 20260901_0006
"""

import sqlalchemy as sa

from alembic import op

revision = "20260902_0007"
down_revision = "20260901_0006"
branch_labels = None
depends_on = None


def _column_exists(table_name: str, column_name: str) -> bool:
    return column_name in {
        column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)
    }


def _index_exists(table_name: str, index_name: str) -> bool:
    return index_name in {
        index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)
    }


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # The initial migration uses current model metadata on a brand-new database,
        # so IF NOT EXISTS keeps both fresh installs and upgrades valid.
        op.execute(
            "ALTER TABLE expenses ADD COLUMN IF NOT EXISTS "
            "occurred_at TIMESTAMP WITH TIME ZONE"
        )
    elif not _column_exists("expenses", "occurred_at"):
        op.add_column(
            "expenses",
            sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
        )

    op.execute(
        "UPDATE expenses SET occurred_at = created_at WHERE occurred_at IS NULL"
    )
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE expenses ALTER COLUMN occurred_at SET NOT NULL")
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_expenses_occurred_at_id "
            "ON expenses (occurred_at, id)"
        )
    else:
        with op.batch_alter_table("expenses") as batch_op:
            batch_op.alter_column(
                "occurred_at",
                existing_type=sa.DateTime(timezone=True),
                nullable=False,
            )
        if not _index_exists("expenses", "ix_expenses_occurred_at_id"):
            op.create_index(
                "ix_expenses_occurred_at_id",
                "expenses",
                ["occurred_at", "id"],
            )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_expenses_occurred_at_id")
        op.execute("ALTER TABLE expenses DROP COLUMN IF EXISTS occurred_at")
    else:
        if _index_exists("expenses", "ix_expenses_occurred_at_id"):
            op.drop_index("ix_expenses_occurred_at_id", table_name="expenses")
        if _column_exists("expenses", "occurred_at"):
            with op.batch_alter_table("expenses") as batch_op:
                batch_op.drop_column("occurred_at")
