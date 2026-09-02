"""Define immutable commands and data-transfer objects for application services."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from splitnshare.domain.contexts import ExpenseContext
from splitnshare.domain.enums import (
    FriendSource,
    GuestCreationMethod,
    Language,
    PersonKind,
    SplitMethod,
)
from splitnshare.domain.money import Money
from splitnshare.domain.splitting import Allocation


@dataclass(frozen=True, slots=True)
class TelegramIdentity:
    """Carry authenticated identity data received from a Telegram user."""
    telegram_user_id: int
    first_name: str
    last_name: str | None = None
    username: str | None = None
    language_code: str | None = None

    @property
    def display_name(self) -> str:
        """Build the user's human-readable name from Telegram profile fields."""
        return " ".join(part for part in (self.first_name, self.last_name) if part).strip()


@dataclass(frozen=True, slots=True)
class SharedTelegramUser:
    """Describe a Telegram user selected or shared by another user."""
    telegram_user_id: int
    first_name: str
    last_name: str | None = None
    username: str | None = None

    @property
    def display_name(self) -> str:
        """Build the shared user's human-readable Telegram name."""
        return " ".join(part for part in (self.first_name, self.last_name) if part).strip()


@dataclass(frozen=True, slots=True)
class PersonDTO:
    """Expose a stable participant identity to application callers."""
    id: UUID
    display_name: str
    kind: PersonKind
    registered: bool
    username: str | None = None
    telegram_user_id: int | None = None


@dataclass(frozen=True, slots=True)
class GuestDTO:
    """Describe an active guest and any suggested registered transfer target."""
    person_id: UUID
    display_name: str
    creation_method: GuestCreationMethod
    suggested_telegram_user_id: int | None
    username: str | None = None
    suggested_target_person_id: UUID | None = None
    suggested_target_name: str | None = None
    suggested_target_username: str | None = None


@dataclass(frozen=True, slots=True)
class FriendDTO:
    """Describe an owner-scoped friend entry and its display metadata."""
    person_id: UUID
    display_name: str
    kind: PersonKind
    registered: bool
    source: FriendSource
    username: str | None = None
    telegram_user_id: int | None = None
    alias: str | None = None


@dataclass(frozen=True, slots=True)
class CreateExpenseCommand:
    """Collect validated input needed to create an expense aggregate."""
    creator_person_id: UUID
    description: str
    total: Money
    participant_ids: tuple[UUID, ...]
    split_method: SplitMethod
    context: ExpenseContext
    payer_person_id: UUID | None = None
    exact_amounts_minor: dict[UUID, int] | None = None
    occurred_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class ExpenseSplitDTO:
    """Expose one participant's ordered share of an expense."""
    person_id: UUID
    display_name: str
    username: str | None
    owed_minor: int
    position: int


@dataclass(frozen=True, slots=True)
class ExpenseDTO:
    """Expose an expense together with payer, creator, and split details."""
    id: UUID
    creator_person_id: UUID
    creator_name: str
    creator_username: str | None
    payer_person_id: UUID
    payer_name: str
    payer_username: str | None
    description: str
    total: Money
    split_method: SplitMethod
    group_id: UUID | None
    occurred_at: datetime
    created_at: datetime
    splits: tuple[ExpenseSplitDTO, ...]


@dataclass(frozen=True, slots=True)
class ExpensePage:
    """Contain one cursor-paginated page of active expenses."""
    items: tuple[ExpenseDTO, ...]
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class TransferGuestCommand:
    """Identify the actor, guest, and registered target for a transfer."""
    actor_person_id: UUID
    guest_person_id: UUID
    target_user_person_id: UUID


@dataclass(frozen=True, slots=True)
class TransferPreviewDTO:
    """Summarize records that an explicit guest transfer would affect."""
    guest_person_id: UUID
    guest_name: str
    target_person_id: UUID
    target_name: str
    expense_count: int
    group_count: int
    friendship_count: int
    settlement_count: int
    debt_totals: dict[str, int]
    guest_username: str | None = None
    target_username: str | None = None


@dataclass(frozen=True, slots=True)
class TransferResultDTO:
    """Report a committed transfer with initiator and expense-total details."""
    transfer_id: UUID
    target_person_id: UUID
    target_telegram_user_id: int
    target_name: str
    target_username: str | None
    initiator_person_id: UUID
    initiator_name: str
    initiator_username: str | None
    expense_totals: dict[str, int]
    affected_counts: dict[str, int]


@dataclass(frozen=True, slots=True)
class BalanceDTO:
    """Represent a currency-specific net balance with another person."""
    other_person_id: UUID
    other_name: str
    currency: str
    net_minor: int
    username: str | None = None


@dataclass(frozen=True, slots=True)
class SettleBalanceCommand:
    """Describe a full or partial payment against a current balance."""
    actor_person_id: UUID
    other_person_id: UUID
    amount: Money
    context: ExpenseContext
    occurred_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class SettlementDTO:
    """Expose an immutable payment recorded between two participants."""
    id: UUID
    recorded_by_person_id: UUID
    payer_person_id: UUID
    recipient_person_id: UUID
    amount: Money
    group_id: UUID | None
    occurred_at: datetime
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ExpenseActivityDTO:
    """Wrap an expense for display in a heterogeneous activity feed."""

    expense: ExpenseDTO


@dataclass(frozen=True, slots=True)
class SettlementActivityDTO:
    """Expose a settlement with participant labels for activity display."""

    settlement: SettlementDTO
    recorded_by_name: str
    recorded_by_username: str | None
    payer_name: str
    payer_username: str | None
    recipient_name: str
    recipient_username: str | None


ActivityItemDTO = ExpenseActivityDTO | SettlementActivityDTO


@dataclass(frozen=True, slots=True)
class ActivityPage:
    """Contain one cursor-paginated page of expenses and settlements."""

    items: tuple[ActivityItemDTO, ...]
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class UserSettingsDTO:
    """Expose a registered user's currency, language, and timezone choices."""
    person_id: UUID
    default_currency: str
    language: Language
    timezone: str | None


@dataclass(frozen=True, slots=True)
class UpdateUserSettingsCommand:
    """Carry optional user-setting changes to the settings service."""
    person_id: UUID
    default_currency: str | None = None
    language: Language | None = None
    timezone: str | None = None


@dataclass(frozen=True, slots=True)
class NewExpenseRecord:
    """Combine an expense command with its calculated split allocations."""
    command: CreateExpenseCommand
    payer_person_id: UUID
    allocations: tuple[Allocation, ...]


JsonDict = dict[str, Any]
