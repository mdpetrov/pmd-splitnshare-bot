"""Provide shared Telegram identity, callback, and money parsing helpers."""

from decimal import Decimal, InvalidOperation

from aiogram.types import CallbackQuery, Message, User

from splitnshare.application.dto import PersonDTO, TelegramIdentity
from splitnshare.domain.errors import PermissionDeniedError, ValidationError
from splitnshare.domain.money import Money
from splitnshare.presentation.container import Services


def telegram_identity(user: User) -> TelegramIdentity:
    """Convert an aiogram user into the application's Telegram identity DTO."""
    return TelegramIdentity(
        telegram_user_id=user.id,
        first_name=user.first_name,
        last_name=user.last_name,
        username=user.username,
        language_code=user.language_code,
    )


def callback_payload(callback: CallbackQuery) -> tuple[str, Message]:
    """Return usable callback data and message or reject an expired action."""
    if callback.data is None or not isinstance(callback.message, Message):
        raise ValidationError("This action is no longer available.")
    return callback.data, callback.message


def callback_message(callback: CallbackQuery) -> Message:
    """Return the concrete message attached to a callback query."""
    if not isinstance(callback.message, Message):
        raise ValidationError("This action is no longer available.")
    return callback.message


async def current_person(message: Message, services: Services) -> PersonDTO:
    """Resolve the registered person sending a private Telegram message."""
    if message.from_user is None:
        raise PermissionDeniedError("A Telegram user is required.")
    person = await services.users.find_registered_target(message.from_user.id)
    if person is None:
        raise PermissionDeniedError("Please use /start before using the bot.")
    return person


def parse_total(text: str, default_currency: str) -> Money:
    """Parse an amount with an optional currency, falling back to a default."""
    parts = text.upper().split()
    if len(parts) == 1:
        return Money.parse(parts[0], default_currency)
    if len(parts) == 2:
        return Money.parse(parts[0], parts[1])
    raise ValidationError("Use an amount such as 12.50 or 12.50 USD.")


def parse_share_minor(text: str, total: Money) -> int:
    """Parse one participant share into integer minor units, allowing zero."""
    if text.strip() in {"0", "0.0", "0.00", "0.000"}:
        return 0
    return Money.parse(text, total.currency).minor


def format_minor(minor: int, currency: str) -> str:
    """Format the absolute value of a signed minor-unit amount."""
    return Money(abs(minor), currency).format()


def as_decimal_string(minor: int, currency: str) -> str:
    """Return a raw decimal string reserved for future locale formatting."""
    # Retained for future locale-aware formatters.
    try:
        return str(Decimal(minor))
    except InvalidOperation:
        return str(minor)
