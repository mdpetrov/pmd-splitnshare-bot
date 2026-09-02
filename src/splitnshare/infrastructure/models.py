"""Map Splitnshare identities, expenses, debts, and transfers to SQL tables."""

from __future__ import annotations

from datetime import datetime
from enum import Enum as PythonEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from splitnshare.domain.enums import (
    FriendSource,
    GroupRole,
    GroupStatus,
    GuestCreationMethod,
    GuestTransferStatus,
    Language,
    MembershipStatus,
    PersonKind,
    SplitMethod,
    TransferStatus,
)


def enum_type(enum: type[PythonEnum], name: str) -> Enum:
    """Create a portable SQLAlchemy enum storing Python enum values."""
    return Enum(
        enum,
        name=name,
        native_enum=False,
        values_callable=lambda items: [item.value for item in items],
    )


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy declarative models."""
    pass


class TimestampMixin:
    """Add database-managed creation and update timestamps to a model."""
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class PersonModel(TimestampMixin, Base):
    """Persist a stable registered-user or guest participant identity."""
    __tablename__ = "persons"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    kind: Mapped[PersonKind] = mapped_column(enum_type(PersonKind, "person_kind"), nullable=False)
    inactive_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UserAccountModel(Base):
    """Attach authenticated Telegram account metadata to a person."""
    __tablename__ = "user_accounts"

    person_id: Mapped[UUID] = mapped_column(
        ForeignKey("persons.id", ondelete="RESTRICT"), primary_key=True
    )
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    username: Mapped[str | None] = mapped_column(String(64))
    first_name: Mapped[str] = mapped_column(String(64), nullable=False)
    last_name: Mapped[str | None] = mapped_column(String(64))
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class UserSettingsModel(TimestampMixin, Base):
    """Persist currency, language, and timezone preferences for a user."""
    __tablename__ = "user_settings"
    __table_args__ = (
        CheckConstraint("length(default_currency) = 3", name="ck_user_settings_currency_length"),
    )

    person_id: Mapped[UUID] = mapped_column(
        ForeignKey("user_accounts.person_id", ondelete="CASCADE"), primary_key=True
    )
    default_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    language: Mapped[Language] = mapped_column(
        enum_type(Language, "language"), default=Language.ENGLISH, nullable=False
    )
    timezone: Mapped[str | None] = mapped_column(String(64))


class FriendshipModel(TimestampMixin, Base):
    """Persist an owner-scoped, directional friend entry and alias."""
    __tablename__ = "friendships"
    __table_args__ = (
        CheckConstraint(
            "owner_person_id <> friend_person_id", name="ck_friendship_not_self"
        ),
        Index("ix_friendships_friend_person_id", "friend_person_id"),
    )

    owner_person_id: Mapped[UUID] = mapped_column(
        ForeignKey("user_accounts.person_id", ondelete="CASCADE"), primary_key=True
    )
    friend_person_id: Mapped[UUID] = mapped_column(
        ForeignKey("persons.id", ondelete="RESTRICT"), primary_key=True
    )
    source: Mapped[FriendSource] = mapped_column(
        enum_type(FriendSource, "friend_source"), nullable=False
    )
    alias: Mapped[str | None] = mapped_column(String(160))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class GuestProfileModel(Base):
    """Persist guest ownership, Telegram hints, and transfer state."""
    __tablename__ = "guest_profiles"
    __table_args__ = (
        Index(
            "uq_active_guest_owner_suggested_tg",
            "owner_person_id",
            "suggested_telegram_user_id",
            unique=True,
            postgresql_where=text(
                "status = 'active' AND suggested_telegram_user_id IS NOT NULL"
            ),
            sqlite_where=text(
                "status = 'active' AND suggested_telegram_user_id IS NOT NULL"
            ),
        ),
    )

    person_id: Mapped[UUID] = mapped_column(
        ForeignKey("persons.id", ondelete="RESTRICT"), primary_key=True
    )
    owner_person_id: Mapped[UUID] = mapped_column(
        ForeignKey("persons.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    suggested_telegram_user_id: Mapped[int | None] = mapped_column(BigInteger)
    suggested_username: Mapped[str | None] = mapped_column(String(64))
    creation_method: Mapped[GuestCreationMethod] = mapped_column(
        enum_type(GuestCreationMethod, "guest_creation_method"), nullable=False
    )
    status: Mapped[GuestTransferStatus] = mapped_column(
        enum_type(GuestTransferStatus, "guest_transfer_status"),
        default=GuestTransferStatus.ACTIVE,
        nullable=False,
    )
    transferred_to_person_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("persons.id", ondelete="RESTRICT")
    )


class GroupModel(TimestampMixin, Base):
    """Persist an expense group independently of Telegram chat identity."""
    __tablename__ = "groups"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    creator_person_id: Mapped[UUID] = mapped_column(
        ForeignKey("persons.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[GroupStatus] = mapped_column(
        enum_type(GroupStatus, "group_status"), default=GroupStatus.ACTIVE, nullable=False
    )


class GroupMembershipModel(Base):
    """Persist a person's role and lifecycle within an expense group."""
    __tablename__ = "group_memberships"

    group_id: Mapped[UUID] = mapped_column(
        ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True
    )
    person_id: Mapped[UUID] = mapped_column(
        ForeignKey("persons.id", ondelete="RESTRICT"), primary_key=True
    )
    role: Mapped[GroupRole] = mapped_column(
        enum_type(GroupRole, "group_role"), default=GroupRole.MEMBER, nullable=False
    )
    status: Mapped[MembershipStatus] = mapped_column(
        enum_type(MembershipStatus, "membership_status"),
        default=MembershipStatus.ACTIVE,
        nullable=False,
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ExpenseModel(TimestampMixin, Base):
    """Persist the header, payer, amount, context, and deletion state of an expense."""
    __tablename__ = "expenses"
    __table_args__ = (
        CheckConstraint("total_minor > 0", name="ck_expense_positive_total"),
        CheckConstraint("length(currency) = 3", name="ck_expense_currency_length"),
        Index("ix_expenses_created_at_id", "created_at", "id"),
        Index("ix_expenses_occurred_at_id", "occurred_at", "id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    group_id: Mapped[UUID | None] = mapped_column(ForeignKey("groups.id", ondelete="RESTRICT"))
    creator_person_id: Mapped[UUID] = mapped_column(
        ForeignKey("persons.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    payer_person_id: Mapped[UUID] = mapped_column(
        ForeignKey("persons.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    description: Mapped[str] = mapped_column(String(240), nullable=False)
    total_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    split_method: Mapped[SplitMethod] = mapped_column(
        enum_type(SplitMethod, "split_method"), nullable=False
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_by_person_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("persons.id", ondelete="RESTRICT")
    )


class ExpenseSplitModel(Base):
    """Persist one participant's ordered owed share of an expense."""
    __tablename__ = "expense_splits"
    __table_args__ = (
        CheckConstraint("owed_minor >= 0", name="ck_split_nonnegative"),
        UniqueConstraint("expense_id", "position", name="uq_expense_split_position"),
    )

    expense_id: Mapped[UUID] = mapped_column(
        ForeignKey("expenses.id", ondelete="CASCADE"), primary_key=True
    )
    person_id: Mapped[UUID] = mapped_column(
        ForeignKey("persons.id", ondelete="RESTRICT"), primary_key=True
    )
    owed_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)


class DebtModel(Base):
    """Persist an expense-derived obligation from a participant to its payer."""
    __tablename__ = "debts"
    __table_args__ = (
        CheckConstraint("amount_minor > 0", name="ck_debt_positive"),
        CheckConstraint("debtor_person_id <> creditor_person_id", name="ck_debt_not_self"),
        Index("ix_debts_debtor_currency", "debtor_person_id", "currency"),
        Index("ix_debts_creditor_currency", "creditor_person_id", "currency"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    expense_id: Mapped[UUID] = mapped_column(
        ForeignKey("expenses.id", ondelete="CASCADE"), index=True, nullable=False
    )
    debtor_person_id: Mapped[UUID] = mapped_column(
        ForeignKey("persons.id", ondelete="RESTRICT"), nullable=False
    )
    creditor_person_id: Mapped[UUID] = mapped_column(
        ForeignKey("persons.id", ondelete="RESTRICT"), nullable=False
    )
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)


class SettlementModel(TimestampMixin, Base):
    """Persist an immutable payment between participants in one currency."""
    __tablename__ = "settlements"
    __table_args__ = (
        CheckConstraint("amount_minor > 0", name="ck_settlement_positive_amount"),
        CheckConstraint("length(currency) = 3", name="ck_settlement_currency_length"),
        CheckConstraint(
            "payer_person_id <> recipient_person_id",
            name="ck_settlement_distinct_people",
        ),
        Index("ix_settlements_payer_currency", "payer_person_id", "currency"),
        Index("ix_settlements_recipient_currency", "recipient_person_id", "currency"),
        Index("ix_settlements_occurred_at_id", "occurred_at", "id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    group_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("groups.id", ondelete="RESTRICT")
    )
    recorded_by_person_id: Mapped[UUID] = mapped_column(
        ForeignKey("user_accounts.person_id", ondelete="RESTRICT"), nullable=False
    )
    payer_person_id: Mapped[UUID] = mapped_column(
        ForeignKey("persons.id", ondelete="RESTRICT"), nullable=False
    )
    recipient_person_id: Mapped[UUID] = mapped_column(
        ForeignKey("persons.id", ondelete="RESTRICT"), nullable=False
    )
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class GuestTransferModel(Base):
    """Audit a manual or registration-triggered identity transfer."""
    __tablename__ = "guest_transfers"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_guest_person_id: Mapped[UUID] = mapped_column(
        ForeignKey("persons.id", ondelete="RESTRICT"), unique=True, nullable=False
    )
    target_user_person_id: Mapped[UUID] = mapped_column(
        ForeignKey("persons.id", ondelete="RESTRICT"), nullable=False
    )
    initiated_by_person_id: Mapped[UUID] = mapped_column(
        ForeignKey("persons.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[TransferStatus] = mapped_column(
        enum_type(TransferStatus, "transfer_status"), nullable=False
    )
    source_name_snapshot: Mapped[str] = mapped_column(String(160), nullable=False)
    affected_counts: Mapped[dict[str, int]] = mapped_column(JSON, nullable=False)
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
