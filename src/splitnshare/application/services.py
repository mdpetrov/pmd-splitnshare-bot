"""Coordinate domain validation and transactional application use cases."""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from splitnshare.application.dto import (
    BalanceDTO,
    CreateExpenseCommand,
    ExpenseDTO,
    ExpensePage,
    FriendDTO,
    GuestDTO,
    NewExpenseRecord,
    PersonDTO,
    SettleBalanceCommand,
    SettlementDTO,
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
from splitnshare.domain.enums import FriendSource, Language, SplitMethod
from splitnshare.domain.errors import NotFoundError, ValidationError
from splitnshare.domain.splitting import EqualSplitStrategy, ExactSplitStrategy
from splitnshare.domain.timezones import SUPPORTED_TIMEZONES


class UserService:
    """Register and locate authenticated Telegram users without claiming guests."""

    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        """Initialize the service with a transactional unit-of-work factory."""
        self._uow_factory = uow_factory

    async def register_or_update(self, identity: TelegramIdentity) -> PersonDTO:
        """Create or refresh a registered user while leaving all guests untouched."""
        # Intentionally talks only to UserRepository. Registration must never inspect guests.
        async with self._uow_factory() as uow:
            person = await uow.users.register_or_update(identity)
            await uow.commit()
            return person

    async def find_registered_target(self, telegram_user_id: int) -> PersonDTO | None:
        """Find a registered transfer or friendship target by Telegram ID."""
        async with self._uow_factory() as uow:
            return await uow.users.find_registered_by_telegram_id(telegram_user_id)


class UserSettingsService:
    """Create, validate, and update per-user interface defaults."""

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        *,
        default_currency: str = "USD",
        default_language: Language = Language.ENGLISH,
    ) -> None:
        """Initialize the service with validated application defaults."""
        self._uow_factory = uow_factory
        self._default_currency = _normalize_currency(default_currency)
        self._default_language = default_language

    async def get_or_create(
        self, person_id: UUID, *, preferred_language: str | None = None
    ) -> UserSettingsDTO:
        """Return settings or create defaults for a newly registered user."""
        async with self._uow_factory() as uow:
            current = await uow.user_settings.get(person_id)
            if current is not None:
                return current
            language = _supported_language(preferred_language) or self._default_language
            created = await uow.user_settings.create(
                person_id, self._default_currency, language.value, None
            )
            await uow.commit()
            return created

    async def find_by_telegram_id(self, telegram_user_id: int) -> UserSettingsDTO | None:
        """Look up settings for middleware without registering the user."""
        async with self._uow_factory() as uow:
            return await uow.user_settings.find_by_telegram_id(telegram_user_id)

    async def update(self, command: UpdateUserSettingsCommand) -> UserSettingsDTO:
        """Validate and persist at least one requested settings change."""
        if (
            command.default_currency is None
            and command.language is None
            and command.timezone is None
        ):
            raise ValidationError("At least one setting must be changed.")
        currency = (
            _normalize_currency(command.default_currency)
            if command.default_currency is not None
            else None
        )
        timezone = (
            _normalize_timezone(command.timezone)
            if command.timezone is not None
            else None
        )
        async with self._uow_factory() as uow:
            if await uow.user_settings.get(command.person_id) is None:
                raise NotFoundError("User settings not found.")
            updated = await uow.user_settings.update(
                command.person_id,
                default_currency=currency,
                language=command.language.value if command.language is not None else None,
                timezone=timezone,
            )
            await uow.commit()
            return updated


class GuestService:
    """Manage temporary participant identities and explicit transfers."""

    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        """Initialize the service with a transactional unit-of-work factory."""
        self._uow_factory = uow_factory

    async def get_or_create_telegram_guest(
        self, owner_person_id: UUID, shared: SharedTelegramUser
    ) -> PersonDTO:
        """Resolve a shared Telegram person to a user or owner-specific guest."""
        async with self._uow_factory() as uow:
            registered = await uow.users.find_registered_by_telegram_id(shared.telegram_user_id)
            if registered is not None:
                return registered
            guest = await uow.guests.get_or_create_telegram_guest(owner_person_id, shared)
            await uow.commit()
            return guest

    async def create_manual_guest(self, owner_person_id: UUID, display_name: str) -> PersonDTO:
        """Create a separately identified, manually named guest."""
        display_name = " ".join(display_name.split())
        if not 1 <= len(display_name) <= 160:
            raise ValidationError("Friend name must contain between 1 and 160 characters.")
        async with self._uow_factory() as uow:
            guest = await uow.guests.create_manual_guest(owner_person_id, display_name)
            await uow.commit()
            return guest

    async def list_owned_guests(self, owner_person_id: UUID) -> Sequence[GuestDTO]:
        """List active guest identities controlled by an owner."""
        async with self._uow_factory() as uow:
            return await uow.guests.list_owned(owner_person_id)

    async def preview_transfer(self, command: TransferGuestCommand) -> TransferPreviewDTO:
        """Return counts and amounts affected by a proposed guest transfer."""
        async with self._uow_factory() as uow:
            return await uow.guests.preview_transfer(
                command.actor_person_id, command.guest_person_id, command.target_user_person_id
            )

    async def transfer_guest(self, command: TransferGuestCommand) -> TransferResultDTO:
        """Atomically transfer a complete guest history to a registered user."""
        async with self._uow_factory() as uow:
            result = await uow.guests.transfer_all(
                command.actor_person_id, command.guest_person_id, command.target_user_person_id
            )
            await uow.commit()
            return result


class FriendService:
    """Manage each user's private list of registered and guest friends."""

    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        """Initialize the service with a transactional unit-of-work factory."""
        self._uow_factory = uow_factory

    async def add_shared_user(
        self, owner_person_id: UUID, shared: SharedTelegramUser
    ) -> FriendDTO:
        """Add a Telegram-selected user or guest to the owner's friend list."""
        async with self._uow_factory() as uow:
            person = await uow.users.find_registered_by_telegram_id(shared.telegram_user_id)
            if person is None:
                person = await uow.guests.get_or_create_telegram_guest(
                    owner_person_id, shared
                )
            friend = await uow.friends.add(
                owner_person_id, person.id, FriendSource.DIRECT
            )
            await uow.commit()
            return friend

    async def add_manual_guest(
        self, owner_person_id: UUID, display_name: str
    ) -> FriendDTO:
        """Create a named guest and add it to the owner's friend list."""
        display_name = " ".join(display_name.split())
        if not 1 <= len(display_name) <= 160:
            raise ValidationError("Friend name must contain between 1 and 160 characters.")
        async with self._uow_factory() as uow:
            guest = await uow.guests.create_manual_guest(owner_person_id, display_name)
            friend = await uow.friends.add(
                owner_person_id, guest.id, FriendSource.DIRECT
            )
            await uow.commit()
            return friend

    async def list_friends(self, owner_person_id: UUID) -> Sequence[FriendDTO]:
        """Return all active friend entries visible to one owner."""
        async with self._uow_factory() as uow:
            return await uow.friends.list_active(owner_person_id)

    async def remove_friend(
        self, owner_person_id: UUID, friend_person_id: UUID
    ) -> bool:
        """Archive a friend entry while preserving expenses and balances."""
        async with self._uow_factory() as uow:
            changed = await uow.friends.archive(owner_person_id, friend_person_id)
            await uow.commit()
            return changed

    async def rename_friend(
        self, owner_person_id: UUID, friend_person_id: UUID, alias: str
    ) -> FriendDTO:
        """Set a normalized private alias without changing global identity."""
        alias = " ".join(alias.split())
        if not 1 <= len(alias) <= 160:
            raise ValidationError("Friend name must contain between 1 and 160 characters.")
        async with self._uow_factory() as uow:
            friend = await uow.friends.rename(
                owner_person_id, friend_person_id, alias
            )
            await uow.commit()
            return friend


class ExpenseService:
    """Validate expense commands, allocate shares, and persist aggregates."""

    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        """Initialize the service with a transactional unit-of-work factory."""
        self._uow_factory = uow_factory

    async def create(self, command: CreateExpenseCommand) -> ExpenseDTO:
        """Create an expense, its splits, debts, and inferred friendships atomically."""
        description = " ".join(command.description.split())
        if not 1 <= len(description) <= 240:
            raise ValidationError("Description must contain between 1 and 240 characters.")
        payer_id = command.payer_person_id or command.creator_person_id
        if payer_id not in command.participant_ids:
            raise ValidationError("The payer must be included in the participants.")
        occurred_at = command.occurred_at or datetime.now(UTC)
        if occurred_at.tzinfo is None or occurred_at.utcoffset() is None:
            raise ValidationError("Expense date and time must include a timezone.")
        occurred_at = occurred_at.astimezone(UTC)

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
                occurred_at=occurred_at,
            ),
            payer_person_id=payer_id,
            allocations=tuple(allocations),
        )
        async with self._uow_factory() as uow:
            expense = await uow.expenses.create(record)
            for participant_id in command.participant_ids:
                if participant_id != command.creator_person_id:
                    await uow.friends.add(
                        command.creator_person_id,
                        participant_id,
                        FriendSource.EXPENSE,
                    )
            await uow.commit()
            return expense

    async def delete(self, actor_person_id: UUID, expense_id: UUID) -> bool:
        """Soft-delete an expense as its original creator."""
        async with self._uow_factory() as uow:
            changed = await uow.expenses.soft_delete(actor_person_id, expense_id)
            await uow.commit()
            return changed


class ExpenseQueryService:
    """Provide read-only access to expense details and history."""

    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        """Initialize the query service with a unit-of-work factory."""
        self._uow_factory = uow_factory

    async def get_details(self, viewer_person_id: UUID, expense_id: UUID) -> ExpenseDTO:
        """Return an active expense when it is visible to the viewer."""
        async with self._uow_factory() as uow:
            return await uow.expenses.get(viewer_person_id, expense_id)

    async def list_for_person(
        self,
        person_id: UUID,
        context: ExpenseContext | None = None,
        cursor: str | None = None,
        limit: int = 10,
    ) -> ExpensePage:
        """Return one validated cursor page of a person's expense history."""
        if not 1 <= limit <= 50:
            raise ValidationError("Page size must be between 1 and 50.")
        async with self._uow_factory() as uow:
            return await uow.expenses.list_for_person(person_id, context, cursor, limit)

    async def list_shared(
        self,
        person_id: UUID,
        other_person_id: UUID,
        context: ExpenseContext | None = None,
        cursor: str | None = None,
        limit: int = 10,
    ) -> ExpensePage:
        """Return a page of active expenses shared by two different people."""
        if person_id == other_person_id:
            raise ValidationError("Shared history requires two different people.")
        if not 1 <= limit <= 50:
            raise ValidationError("Page size must be between 1 and 50.")
        async with self._uow_factory() as uow:
            return await uow.expenses.list_shared(
                person_id, other_person_id, context, cursor, limit
            )

    async def list_recent_people(self, person_id: UUID, limit: int = 10) -> Sequence[PersonDTO]:
        """Return active people recently sharing expenses with the person."""
        if not 1 <= limit <= 20:
            raise ValidationError("Recent-people limit must be between 1 and 20.")
        async with self._uow_factory() as uow:
            return await uow.expenses.recent_people(person_id, limit)


class SettlementService:
    """Validate and record full or partial payments against balances."""

    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        """Initialize the service with a transactional unit-of-work factory."""
        self._uow_factory = uow_factory

    async def settle(self, command: SettleBalanceCommand) -> SettlementDTO:
        """Record a timezone-aware payment without exceeding the live balance."""
        if command.actor_person_id == command.other_person_id:
            raise ValidationError("A balance cannot be settled with yourself.")
        if command.amount.minor <= 0:
            raise ValidationError("Settlement amount must be greater than zero.")
        occurred_at = command.occurred_at or datetime.now(UTC)
        if occurred_at.tzinfo is None or occurred_at.utcoffset() is None:
            raise ValidationError("Settlement date and time must include a timezone.")
        async with self._uow_factory() as uow:
            settlement = await uow.settlements.create_for_balance(
                command.actor_person_id,
                command.other_person_id,
                command.amount.minor,
                command.amount.currency,
                command.context,
                occurred_at.astimezone(UTC),
            )
            await uow.commit()
            return settlement


class BalanceQueryService:
    """Expose currency-separated net balances for a person and context."""

    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        """Initialize the query service with a unit-of-work factory."""
        self._uow_factory = uow_factory

    async def get_balances(
        self, person_id: UUID, context: ExpenseContext | None = None
    ) -> Sequence[BalanceDTO]:
        """Calculate balances from active expense debts and settlements."""
        async with self._uow_factory() as uow:
            return await uow.expenses.balances(person_id, context)


def _normalize_currency(value: str) -> str:
    """Normalize and validate a three-letter ASCII currency code."""
    currency = value.strip().upper()
    if len(currency) != 3 or not currency.isalpha() or not currency.isascii():
        raise ValidationError("Currency must be a three-letter ISO code.")
    return currency


def _supported_language(value: str | None) -> Language | None:
    """Map a Telegram locale string to a supported interface language."""
    if not value:
        return None
    normalized = value.split("-", 1)[0].split("_", 1)[0].lower()
    try:
        return Language(normalized)
    except ValueError:
        return None


def _normalize_timezone(value: str) -> str:
    """Validate a timezone against the application's supported choices."""
    timezone = value.strip()
    if timezone not in SUPPORTED_TIMEZONES:
        raise ValidationError("Unsupported timezone.")
    return timezone
