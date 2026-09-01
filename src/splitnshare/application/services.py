from collections.abc import Sequence
from uuid import UUID

from splitnshare.application.dto import (
    BalanceDTO,
    CreateExpenseCommand,
    ExpenseDTO,
    ExpensePage,
    GuestDTO,
    NewExpenseRecord,
    PersonDTO,
    SharedTelegramUser,
    TelegramIdentity,
    TransferGuestCommand,
    TransferPreviewDTO,
    TransferResultDTO,
    UpdateUserSettingsCommand,
    UserSettingsDTO,
)
from splitnshare.application.ports import UnitOfWorkFactory
from splitnshare.domain.contexts import ExpenseContext
from splitnshare.domain.enums import Language, SplitMethod
from splitnshare.domain.errors import NotFoundError, ValidationError
from splitnshare.domain.splitting import EqualSplitStrategy, ExactSplitStrategy


class UserService:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def register_or_update(self, identity: TelegramIdentity) -> PersonDTO:
        # Intentionally talks only to UserRepository. Registration must never inspect guests.
        async with self._uow_factory() as uow:
            person = await uow.users.register_or_update(identity)
            await uow.commit()
            return person

    async def find_registered_target(self, telegram_user_id: int) -> PersonDTO | None:
        async with self._uow_factory() as uow:
            return await uow.users.find_registered_by_telegram_id(telegram_user_id)


class UserSettingsService:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        *,
        default_currency: str = "USD",
        default_language: Language = Language.ENGLISH,
    ) -> None:
        self._uow_factory = uow_factory
        self._default_currency = _normalize_currency(default_currency)
        self._default_language = default_language

    async def get_or_create(
        self, person_id: UUID, *, preferred_language: str | None = None
    ) -> UserSettingsDTO:
        async with self._uow_factory() as uow:
            current = await uow.user_settings.get(person_id)
            if current is not None:
                return current
            language = _supported_language(preferred_language) or self._default_language
            created = await uow.user_settings.create(
                person_id, self._default_currency, language.value
            )
            await uow.commit()
            return created

    async def find_by_telegram_id(self, telegram_user_id: int) -> UserSettingsDTO | None:
        async with self._uow_factory() as uow:
            return await uow.user_settings.find_by_telegram_id(telegram_user_id)

    async def update(self, command: UpdateUserSettingsCommand) -> UserSettingsDTO:
        if command.default_currency is None and command.language is None:
            raise ValidationError("At least one setting must be changed.")
        currency = (
            _normalize_currency(command.default_currency)
            if command.default_currency is not None
            else None
        )
        async with self._uow_factory() as uow:
            if await uow.user_settings.get(command.person_id) is None:
                raise NotFoundError("User settings not found.")
            updated = await uow.user_settings.update(
                command.person_id,
                default_currency=currency,
                language=command.language.value if command.language is not None else None,
            )
            await uow.commit()
            return updated


class GuestService:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def get_or_create_telegram_guest(
        self, owner_person_id: UUID, shared: SharedTelegramUser
    ) -> PersonDTO:
        async with self._uow_factory() as uow:
            registered = await uow.users.find_registered_by_telegram_id(shared.telegram_user_id)
            if registered is not None:
                return registered
            guest = await uow.guests.get_or_create_telegram_guest(owner_person_id, shared)
            await uow.commit()
            return guest

    async def create_manual_guest(self, owner_person_id: UUID, display_name: str) -> PersonDTO:
        display_name = " ".join(display_name.split())
        if not 1 <= len(display_name) <= 160:
            raise ValidationError("Guest name must contain between 1 and 160 characters.")
        async with self._uow_factory() as uow:
            guest = await uow.guests.create_manual_guest(owner_person_id, display_name)
            await uow.commit()
            return guest

    async def list_owned_guests(self, owner_person_id: UUID) -> Sequence[GuestDTO]:
        async with self._uow_factory() as uow:
            return await uow.guests.list_owned(owner_person_id)

    async def preview_transfer(self, command: TransferGuestCommand) -> TransferPreviewDTO:
        async with self._uow_factory() as uow:
            return await uow.guests.preview_transfer(
                command.actor_person_id, command.guest_person_id, command.target_user_person_id
            )

    async def transfer_guest(self, command: TransferGuestCommand) -> TransferResultDTO:
        async with self._uow_factory() as uow:
            result = await uow.guests.transfer_all(
                command.actor_person_id, command.guest_person_id, command.target_user_person_id
            )
            await uow.commit()
            return result


class ExpenseService:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def create(self, command: CreateExpenseCommand) -> ExpenseDTO:
        description = " ".join(command.description.split())
        if not 1 <= len(description) <= 240:
            raise ValidationError("Description must contain between 1 and 240 characters.")
        payer_id = command.payer_person_id or command.creator_person_id
        if payer_id not in command.participant_ids:
            raise ValidationError("The payer must be included in the participants.")

        if command.split_method is SplitMethod.EQUAL:
            allocations = EqualSplitStrategy().allocate(
                command.total.minor, command.participant_ids
            )
        elif command.split_method is SplitMethod.EXACT:
            if command.exact_amounts_minor is None:
                raise ValidationError("Exact split amounts are required.")
            allocations = ExactSplitStrategy().allocate(
                command.total.minor,
                command.participant_ids,
                command.exact_amounts_minor,
                payer_id,
            )
        else:
            raise ValidationError("Unsupported split method.")

        record = NewExpenseRecord(
            command=CreateExpenseCommand(
                creator_person_id=command.creator_person_id,
                description=description,
                total=command.total,
                participant_ids=command.participant_ids,
                split_method=command.split_method,
                context=command.context,
                payer_person_id=payer_id,
                exact_amounts_minor=command.exact_amounts_minor,
            ),
            payer_person_id=payer_id,
            allocations=tuple(allocations),
        )
        async with self._uow_factory() as uow:
            expense = await uow.expenses.create(record)
            await uow.commit()
            return expense

    async def delete(self, actor_person_id: UUID, expense_id: UUID) -> bool:
        async with self._uow_factory() as uow:
            changed = await uow.expenses.soft_delete(actor_person_id, expense_id)
            await uow.commit()
            return changed


class ExpenseQueryService:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def get_details(self, viewer_person_id: UUID, expense_id: UUID) -> ExpenseDTO:
        async with self._uow_factory() as uow:
            return await uow.expenses.get(viewer_person_id, expense_id)

    async def list_for_person(
        self,
        person_id: UUID,
        context: ExpenseContext | None = None,
        cursor: str | None = None,
        limit: int = 10,
    ) -> ExpensePage:
        if not 1 <= limit <= 50:
            raise ValidationError("Page size must be between 1 and 50.")
        async with self._uow_factory() as uow:
            return await uow.expenses.list_for_person(person_id, context, cursor, limit)

    async def list_recent_people(self, person_id: UUID, limit: int = 10) -> Sequence[PersonDTO]:
        if not 1 <= limit <= 20:
            raise ValidationError("Recent-people limit must be between 1 and 20.")
        async with self._uow_factory() as uow:
            return await uow.expenses.recent_people(person_id, limit)


class BalanceQueryService:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def get_balances(
        self, person_id: UUID, context: ExpenseContext | None = None
    ) -> Sequence[BalanceDTO]:
        async with self._uow_factory() as uow:
            return await uow.expenses.balances(person_id, context)


def _normalize_currency(value: str) -> str:
    currency = value.strip().upper()
    if len(currency) != 3 or not currency.isalpha() or not currency.isascii():
        raise ValidationError("Currency must be a three-letter ISO code.")
    return currency


def _supported_language(value: str | None) -> Language | None:
    if not value:
        return None
    normalized = value.split("-", 1)[0].split("_", 1)[0].lower()
    try:
        return Language(normalized)
    except ValueError:
        return None
