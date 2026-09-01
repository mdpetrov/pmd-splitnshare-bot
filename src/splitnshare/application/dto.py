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
    telegram_user_id: int
    first_name: str
    last_name: str | None = None
    username: str | None = None
    language_code: str | None = None

    @property
    def display_name(self) -> str:
        return " ".join(part for part in (self.first_name, self.last_name) if part).strip()


@dataclass(frozen=True, slots=True)
class SharedTelegramUser:
    telegram_user_id: int
    first_name: str
    last_name: str | None = None
    username: str | None = None

    @property
    def display_name(self) -> str:
        return " ".join(part for part in (self.first_name, self.last_name) if part).strip()


@dataclass(frozen=True, slots=True)
class PersonDTO:
    id: UUID
    display_name: str
    kind: PersonKind
    registered: bool
    username: str | None = None
    telegram_user_id: int | None = None


@dataclass(frozen=True, slots=True)
class GuestDTO:
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
    creator_person_id: UUID
    description: str
    total: Money
    participant_ids: tuple[UUID, ...]
    split_method: SplitMethod
    context: ExpenseContext
    payer_person_id: UUID | None = None
    exact_amounts_minor: dict[UUID, int] | None = None


@dataclass(frozen=True, slots=True)
class ExpenseSplitDTO:
    person_id: UUID
    display_name: str
    username: str | None
    owed_minor: int
    position: int


@dataclass(frozen=True, slots=True)
class ExpenseDTO:
    id: UUID
    creator_person_id: UUID
    payer_person_id: UUID
    payer_name: str
    payer_username: str | None
    description: str
    total: Money
    split_method: SplitMethod
    group_id: UUID | None
    created_at: datetime
    splits: tuple[ExpenseSplitDTO, ...]


@dataclass(frozen=True, slots=True)
class ExpensePage:
    items: tuple[ExpenseDTO, ...]
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class TransferGuestCommand:
    actor_person_id: UUID
    guest_person_id: UUID
    target_user_person_id: UUID


@dataclass(frozen=True, slots=True)
class TransferPreviewDTO:
    guest_person_id: UUID
    guest_name: str
    target_person_id: UUID
    target_name: str
    expense_count: int
    group_count: int
    friendship_count: int
    debt_totals: dict[str, int]
    guest_username: str | None = None
    target_username: str | None = None


@dataclass(frozen=True, slots=True)
class TransferResultDTO:
    transfer_id: UUID
    target_person_id: UUID
    target_telegram_user_id: int
    target_name: str
    target_username: str | None
    affected_counts: dict[str, int]


@dataclass(frozen=True, slots=True)
class BalanceDTO:
    other_person_id: UUID
    other_name: str
    currency: str
    net_minor: int
    username: str | None = None


@dataclass(frozen=True, slots=True)
class UserSettingsDTO:
    person_id: UUID
    default_currency: str
    language: Language
    timezone: str | None


@dataclass(frozen=True, slots=True)
class UpdateUserSettingsCommand:
    person_id: UUID
    default_currency: str | None = None
    language: Language | None = None
    timezone: str | None = None


@dataclass(frozen=True, slots=True)
class NewExpenseRecord:
    command: CreateExpenseCommand
    payer_person_id: UUID
    allocations: tuple[Allocation, ...]


JsonDict = dict[str, Any]
