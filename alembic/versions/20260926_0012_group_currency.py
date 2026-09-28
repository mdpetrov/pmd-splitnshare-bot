"""Add a default currency to groups, using each owner's saved preference."""

import sqlalchemy as sa

from alembic import op

revision = "20260926_0012"
down_revision = "20260911_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Backfill existing groups before requiring a default currency."""
    op.add_column("groups", sa.Column("default_currency", sa.String(3), nullable=True))
    op.execute(
        sa.text(
            "UPDATE groups SET default_currency = COALESCE("
            "(SELECT default_currency FROM user_settings "
            "WHERE person_id = groups.creator_person_id), 'USD')"
        )
    )
    with op.batch_alter_table("groups") as batch:
        batch.alter_column("default_currency", existing_type=sa.String(3), nullable=False)


def downgrade() -> None:
    """Remove the group currency preference without changing transactions."""
    with op.batch_alter_table("groups") as batch:
        batch.drop_column("default_currency")
