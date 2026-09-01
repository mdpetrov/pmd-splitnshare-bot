"""Initial identity, expense, debt, group, and guest-transfer schema.

Revision ID: 20260824_0001
Revises:
"""
from alembic import op
from splitnshare.infrastructure.models import Base

revision = "20260824_0001"
down_revision = None
branch_labels = None
depends_on = None

INITIAL_TABLE_NAMES = (
    "persons",
    "user_accounts",
    "guest_profiles",
    "groups",
    "group_memberships",
    "expenses",
    "expense_splits",
    "debts",
    "guest_transfers",
)


def _initial_tables():
    return [Base.metadata.tables[name] for name in INITIAL_TABLE_NAMES]


def upgrade() -> None:
    # Keep this revision limited to the tables that existed when it was created.
    # Later model tables belong to their own Alembic revisions.
    Base.metadata.create_all(bind=op.get_bind(), tables=_initial_tables())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind(), tables=_initial_tables())
