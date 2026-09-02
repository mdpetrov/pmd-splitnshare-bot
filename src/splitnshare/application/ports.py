"""Declare persistence and transaction boundaries used by application services."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from types import TracebackType
from typing import Protocol
from uuid import UUID

from splitnshare.application.dto import (
    ActivityPage,
    BalanceDTO,
    ExpenseDTO,
    ExpensePage,
    FriendDTO,
    GuestDTO,
    NewExpenseRecord,
    PersonDTO,
    SettlementDTO,
    SharedTelegramUser,
    TelegramIdentity,
    TransferPreviewDTO,
    TransferResultDTO,
    UserSettingsDTO,
)
from splitnshare.domain.contexts import ExpenseContext
from splitnshare.domain.enums import FriendSource


class UserRepository(Protocol):
    """Persist and retrieve registered Telegram-backed identities."""

    async def register_or_update(self, identity: TelegramIdentity) -> PersonDTO:
        """Persist the account row before application-level profile transfer."""
        ...

    async def find_registered_by_telegram_id(self, telegram_user_id: int) -> PersonDTO | None:
        """Find a registered person by authenticated Telegram user ID."""
        ...

    async def get_registered(self, person_id: UUID, *, for_update: bool = False) -> PersonDTO:
        """Load a registered person, optionally taking a database lock."""
        ...

    async def list_registered(
        self, person_ids: Sequence[UUID]
    ) -> Sequence[PersonDTO]:
        """Return registered accounts among the supplied participant IDs."""
        ...


class UserSettingsRepository(Protocol):
    """Persist locale, currency, and timezone settings for registered users."""

    async def get(self, person_id: UUID) -> UserSettingsDTO | None:
        """Return settings for a person when they exist."""
        ...

    async def find_by_telegram_id(self, telegram_user_id: int) -> UserSettingsDTO | None:
        """Find settings through a registered Telegram user ID."""
        ...

    async def create(
        self,
        person_id: UUID,
        default_currency: str,
        language: str,
        timezone: str | None,
    ) -> UserSettingsDTO:
        """Create the initial settings row for a registered user."""
        ...

    async def update(
        self,
        person_id: UUID,
        *,
        default_currency: str | None,
        language: str | None,
        timezone: str | None,
    ) -> UserSettingsDTO:
        """Apply supplied changes to an existing settings row."""
        ...


class GuestRepository(Protocol):
    """Persist guests and perform manual or registration-triggered transfers."""

    async def find_active_telegram_guest(
        self, owner_person_id: UUID, shared: SharedTelegramUser
    ) -> PersonDTO | None:
        """Find and refresh an owner's active Telegram-hinted guest."""
        ...

    async def get_or_create_telegram_guest(
        self, owner_person_id: UUID, shared: SharedTelegramUser
    ) -> PersonDTO:
        """Reuse or create the owner's guest for a shared Telegram identity."""
        ...

    async def create_manual_guest(self, owner_person_id: UUID, display_name: str) -> PersonDTO:
        """Create a distinct guest identified only by a display name."""
        ...

    async def list_owned(self, owner_person_id: UUID) -> Sequence[GuestDTO]:
        """List active guests managed by one owner."""
        ...

    async def preview_transfer(
        self, actor_person_id: UUID, guest_person_id: UUID, target_person_id: UUID
    ) -> TransferPreviewDTO:
        """Summarize everything that a proposed transfer would change."""
        ...

    async def transfer_all(
        self, actor_person_id: UUID, guest_person_id: UUID, target_person_id: UUID
    ) -> TransferResultDTO:
        """Atomically replace a guest with a registered participant."""
        ...

    async def transfer_matching_registration(
        self, target_person_id: UUID
    ) -> Sequence[TransferResultDTO]:
        """Transfer active Telegram-hinted guests matching a registered account."""
        ...


class FriendRepository(Protocol):
    """Persist private, directional friend-list entries."""

    async def add(
        self, owner_person_id: UUID, friend_person_id: UUID, source: FriendSource
    ) -> FriendDTO:
        """Add or reactivate one person in an owner's friends list."""
        ...

    async def list_active(self, owner_person_id: UUID) -> Sequence[FriendDTO]:
        """List an owner's currently active friends."""
        ...

    async def archive(self, owner_person_id: UUID, friend_person_id: UUID) -> bool:
        """Archive a private friend entry without deleting shared history."""
        ...

    async def rename(
        self, owner_person_id: UUID, friend_person_id: UUID, alias: str
    ) -> FriendDTO:
        """Set the owner's private display alias for a friend."""
        ...


class ExpenseRepository(Protocol):
    """Persist expense aggregates and query their derived balances."""

    async def create(self, record: NewExpenseRecord) -> ExpenseDTO:
        """Persist an expense, its splits, and its generated debts."""
        ...

    async def soft_delete(self, actor_person_id: UUID, expense_id: UUID) -> bool:
        """Soft-delete an expense when the actor is its creator."""
        ...

    async def get(self, viewer_person_id: UUID, expense_id: UUID) -> ExpenseDTO:
        """Load an active expense visible to the requesting participant."""
        ...

    async def list_for_person(
        self,
        person_id: UUID,
        context: ExpenseContext | None,
        cursor: str | None,
        limit: int,
    ) -> ExpensePage:
        """Return a cursor-paginated expense history for one participant."""
        ...

    async def list_shared(
        self,
        person_id: UUID,
        other_person_id: UUID,
        context: ExpenseContext | None,
        cursor: str | None,
        limit: int,
    ) -> ExpensePage:
        """Return expenses in which both specified people participate."""
        ...

    async def count_shared(
        self,
        person_id: UUID,
        other_person_id: UUID,
        context: ExpenseContext | None,
    ) -> int:
        """Count active expenses shared by two specified participants."""
        ...

    async def balances(
        self, person_id: UUID, context: ExpenseContext | None
    ) -> Sequence[BalanceDTO]:
        """Calculate net balances from active debts and settlements."""
        ...

    async def recent_people(self, person_id: UUID, limit: int) -> Sequence[PersonDTO]:
        """Return recently encountered active expense participants."""
        ...


class SettlementRepository(Protocol):
    """Persist payments made against calculated balances."""

    async def create_for_balance(
        self,
        actor_person_id: UUID,
        other_person_id: UUID,
        amount_minor: int,
        currency: str,
        context: ExpenseContext,
        occurred_at: datetime,
    ) -> SettlementDTO:
        """Validate a current balance and record a payment against it."""
        ...


class ActivityRepository(Protocol):
    """Read a unified chronological feed of expenses and settlements."""

    async def list_for_person(
        self,
        person_id: UUID,
        other_person_id: UUID | None,
        context: ExpenseContext | None,
        cursor: str | None,
        limit: int,
    ) -> ActivityPage:
        """Return activity optionally restricted to one counterparty."""
        ...


class UnitOfWork(Protocol):
    """Group repositories behind one atomic database transaction."""

    users: UserRepository
    user_settings: UserSettingsRepository
    guests: GuestRepository
    friends: FriendRepository
    expenses: ExpenseRepository
    settlements: SettlementRepository
    activities: ActivityRepository

    async def __aenter__(self) -> UnitOfWork:
        """Open the transactional repository scope."""
        ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Roll back uncommitted work and close the scope."""
        ...

    async def commit(self) -> None:
        """Commit every change made through this unit of work."""
        ...


class UnitOfWorkFactory(Protocol):
    """Create independent unit-of-work instances on demand."""

    def __call__(self) -> UnitOfWork:
        """Return a new transactional unit of work."""
        ...
