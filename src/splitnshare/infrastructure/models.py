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
    return Enum(
        enum,
        name=name,
        native_enum=False,
        values_callable=lambda items: [item.value for item in items],
    )


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class PersonModel(TimestampMixin, Base):
    __tablename__ = "persons"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    kind: Mapped[PersonKind] = mapped_column(enum_type(PersonKind, "person_kind"), nullable=False)
    inactive_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UserAccountModel(Base):
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


class GuestProfileModel(Base):
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
    __tablename__ = "expenses"
    __table_args__ = (
        CheckConstraint("total_minor > 0", name="ck_expense_positive_total"),
        CheckConstraint("length(currency) = 3", name="ck_expense_currency_length"),
        Index("ix_expenses_created_at_id", "created_at", "id"),
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
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_by_person_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("persons.id", ondelete="RESTRICT")
    )


class ExpenseSplitModel(Base):
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


class GuestTransferModel(Base):
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
