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


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())

