"""Initial identity, expense, debt, group, and guest-transfer schema.

Revision ID: 20260824_0001
Revises:
"""
import sqlalchemy as sa

from alembic import op
from splitnshare.infrastructure.models import Base

revision = "20260824_0001"
down_revision = None
branch_labels = None
depends_on = None

INITIAL_TABLE_NAMES = (
    "persons",
    "user_accounts",
    "groups",
    "group_memberships",
    "expenses",
    "expense_splits",
    "debts",
    "guest_transfers",
)


def _initial_tables():
    """Return only the model tables that belong to the initial revision."""
    return [Base.metadata.tables[name] for name in INITIAL_TABLE_NAMES]


def upgrade() -> None:
    """Create the initial identity, group, expense, debt, and transfer schema."""
    # Keep this revision limited to the tables that existed when it was created.
    # Later model tables and columns belong to their own Alembic revisions.
    Base.metadata.create_all(bind=op.get_bind(), tables=_initial_tables())
    op.create_table(
        "guest_profiles",
        sa.Column("person_id", sa.Uuid(), nullable=False),
        sa.Column("owner_person_id", sa.Uuid(), nullable=False),
        sa.Column("suggested_telegram_user_id", sa.BigInteger(), nullable=True),
        sa.Column("creation_method", sa.String(length=8), nullable=False),
        sa.Column("status", sa.String(length=11), nullable=False),
        sa.Column("transferred_to_person_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["owner_person_id"], ["persons.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["person_id"], ["persons.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["transferred_to_person_id"], ["persons.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("person_id"),
    )
    op.create_index(
        "ix_guest_profiles_owner_person_id",
        "guest_profiles",
        ["owner_person_id"],
    )
    op.create_index(
        "uq_active_guest_owner_suggested_tg",
        "guest_profiles",
        ["owner_person_id", "suggested_telegram_user_id"],
        unique=True,
        postgresql_where=sa.text(
            "status = 'active' AND suggested_telegram_user_id IS NOT NULL"
        ),
        sqlite_where=sa.text(
            "status = 'active' AND suggested_telegram_user_id IS NOT NULL"
        ),
    )


def downgrade() -> None:
    """Drop every table and index introduced by the initial revision."""
    op.drop_index("uq_active_guest_owner_suggested_tg", table_name="guest_profiles")
    op.drop_index("ix_guest_profiles_owner_person_id", table_name="guest_profiles")
    op.drop_table("guest_profiles")
    Base.metadata.drop_all(bind=op.get_bind(), tables=_initial_tables())
