from __future__ import annotations

from collections.abc import Sequence
from types import TracebackType
from typing import Protocol
from uuid import UUID

from splitnshare.application.dto import (
    BalanceDTO,
    ExpenseDTO,
    ExpensePage,
    GuestDTO,
    NewExpenseRecord,
    PersonDTO,
    SharedTelegramUser,
    TelegramIdentity,
    TransferPreviewDTO,
    TransferResultDTO,
)
from splitnshare.domain.contexts import ExpenseContext


class UserRepository(Protocol):
    async def register_or_update(self, identity: TelegramIdentity) -> PersonDTO: ...

    async def find_registered_by_telegram_id(self, telegram_user_id: int) -> PersonDTO | None: ...

    async def get_registered(self, person_id: UUID, *, for_update: bool = False) -> PersonDTO: ...


class GuestRepository(Protocol):
    async def get_or_create_telegram_guest(
        self, owner_person_id: UUID, shared: SharedTelegramUser
    ) -> PersonDTO: ...

    async def create_manual_guest(self, owner_person_id: UUID, display_name: str) -> PersonDTO: ...

    async def list_owned(self, owner_person_id: UUID) -> Sequence[GuestDTO]: ...

    async def preview_transfer(
        self, actor_person_id: UUID, guest_person_id: UUID, target_person_id: UUID
    ) -> TransferPreviewDTO: ...

    async def transfer_all(
        self, actor_person_id: UUID, guest_person_id: UUID, target_person_id: UUID
    ) -> TransferResultDTO: ...


class ExpenseRepository(Protocol):
    async def create(self, record: NewExpenseRecord) -> ExpenseDTO: ...

    async def soft_delete(self, actor_person_id: UUID, expense_id: UUID) -> bool: ...

    async def get(self, viewer_person_id: UUID, expense_id: UUID) -> ExpenseDTO: ...

    async def list_for_person(
        self,
        person_id: UUID,
        context: ExpenseContext | None,
        cursor: str | None,
        limit: int,
    ) -> ExpensePage: ...

    async def balances(
        self, person_id: UUID, context: ExpenseContext | None
    ) -> Sequence[BalanceDTO]: ...

    async def recent_people(self, person_id: UUID, limit: int) -> Sequence[PersonDTO]: ...


class UnitOfWork(Protocol):
    users: UserRepository
    guests: GuestRepository
    expenses: ExpenseRepository

    async def __aenter__(self) -> UnitOfWork: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...


class UnitOfWorkFactory(Protocol):
    def __call__(self) -> UnitOfWork: ...
