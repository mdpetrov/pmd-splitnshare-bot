from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove

from splitnshare.application.dto import BalanceDTO, PersonDTO, UserSettingsDTO
from splitnshare.domain.enums import Language, PersonKind
from splitnshare.presentation.routers.start import start
from splitnshare.presentation.states import OnboardingStates


def _message() -> SimpleNamespace:
    return SimpleNamespace(
        from_user=SimpleNamespace(
            id=9001,
            first_name="New",
            last_name="User",
            username="new_user",
            language_code="en",
        ),
        answer=AsyncMock(),
    )


def _services(
    timezone: str | None,
    balances: tuple[BalanceDTO, ...] = (),
) -> SimpleNamespace:
    person = PersonDTO(
        id=uuid4(),
        display_name="New User",
        kind=PersonKind.USER,
        registered=True,
        username="new_user",
        telegram_user_id=9001,
    )
    settings = UserSettingsDTO(
        person_id=person.id,
        default_currency="USD",
        language=Language.ENGLISH,
        timezone=timezone,
    )
    return SimpleNamespace(
        users=SimpleNamespace(register_or_update=AsyncMock(return_value=person)),
        user_settings=SimpleNamespace(get_or_create=AsyncMock(return_value=settings)),
        balances=SimpleNamespace(get_balances=AsyncMock(return_value=balances)),
    )


async def test_new_user_selects_timezone_before_main_menu() -> None:
    message = _message()
    state = SimpleNamespace(clear=AsyncMock(), set_state=AsyncMock())

    await start(message, state, _services(None))

    state.set_state.assert_awaited_once_with(OnboardingStates.timezone)
    assert message.answer.await_count == 2
    first_markup = message.answer.await_args_list[0].kwargs["reply_markup"]
    second_markup = message.answer.await_args_list[1].kwargs["reply_markup"]
    assert isinstance(first_markup, ReplyKeyboardRemove)
    assert isinstance(second_markup, InlineKeyboardMarkup)
    assert "Currency and language can be changed later" in (
        message.answer.await_args_list[0].args[0]
    )


async def test_existing_user_with_timezone_receives_main_menu() -> None:
    message = _message()
    state = SimpleNamespace(clear=AsyncMock(), set_state=AsyncMock())

    await start(message, state, _services("Europe/Madrid"))

    state.set_state.assert_not_awaited()
    assert message.answer.await_count == 2
    quick_markup = message.answer.await_args_list[0].kwargs["reply_markup"]
    menu_markup = message.answer.await_args_list[1].kwargs["reply_markup"]
    assert isinstance(quick_markup, ReplyKeyboardMarkup)
    assert isinstance(menu_markup, InlineKeyboardMarkup)
    assert "Hi, New User!" in message.answer.await_args_list[0].args[0]
    assert "no outstanding balances" in message.answer.await_args_list[0].args[0]


async def test_existing_user_welcome_summarizes_both_balance_directions() -> None:
    message = _message()
    state = SimpleNamespace(clear=AsyncMock(), set_state=AsyncMock())
    other_id = uuid4()
    balances = (
        BalanceDTO(other_id, "Alice", "USD", -500),
        BalanceDTO(uuid4(), "Charlie", "USD", -250),
        BalanceDTO(uuid4(), "Bob", "USD", 1200),
        BalanceDTO(uuid4(), "Dana", "EUR", 300),
    )

    await start(message, state, _services("Europe/Madrid", balances))

    welcome = message.answer.await_args_list[0].args[0]
    assert "🔴 ▼ You owe: <b>7.50 USD</b>" in welcome
    assert "🟢 ▲ You are owed: <b>3.00 EUR, 12.00 USD</b>" in welcome
