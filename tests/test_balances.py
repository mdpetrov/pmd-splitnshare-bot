from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from splitnshare.application.dto import BalanceDTO, CreateExpenseCommand, TelegramIdentity
from splitnshare.application.services import BalanceQueryService, ExpenseService, UserService
from splitnshare.domain.contexts import DirectExpenseContext
from splitnshare.domain.enums import Language, SplitMethod
from splitnshare.domain.money import Money
from splitnshare.infrastructure.database import create_session_factory
from splitnshare.infrastructure.models import Base
from splitnshare.infrastructure.unit_of_work import SqlAlchemyUnitOfWorkFactory
from splitnshare.presentation.callbacks import uuid_from_token, uuid_token
from splitnshare.presentation.formatters import balances_text, person_balances_text
from splitnshare.presentation.keyboards import balances_keyboard, person_balance_keyboard


@pytest.fixture
async def balance_services():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    uow = SqlAlchemyUnitOfWorkFactory(create_session_factory(engine))
    yield UserService(uow), ExpenseService(uow), BalanceQueryService(uow)
    await engine.dispose()


async def test_balances_keep_currencies_separate_and_exclude_deleted_expenses(
    balance_services,
) -> None:
    users, expenses, balances = balance_services
    owner = await users.register_or_update(
        TelegramIdentity(telegram_user_id=801, first_name="Owner")
    )
    friend = await users.register_or_update(
        TelegramIdentity(
            telegram_user_id=802, first_name="Friend", username="friend_username"
        )
    )
    usd_expense = await expenses.create(
        CreateExpenseCommand(
            creator_person_id=owner.id,
            description="USD expense",
            total=Money(1000, "USD"),
            participant_ids=(owner.id, friend.id),
            split_method=SplitMethod.EQUAL,
            context=DirectExpenseContext(),
        )
    )
    await expenses.create(
        CreateExpenseCommand(
            creator_person_id=friend.id,
            description="EUR expense",
            total=Money(2000, "EUR"),
            participant_ids=(friend.id, owner.id),
            split_method=SplitMethod.EQUAL,
            context=DirectExpenseContext(),
        )
    )

    result = await balances.get_balances(owner.id)

    assert {(balance.currency, balance.net_minor) for balance in result} == {
        ("USD", 500),
        ("EUR", -1000),
    }
    assert {balance.username for balance in result} == {"friend_username"}

    assert await expenses.delete(owner.id, usd_expense.id)
    remaining = await balances.get_balances(owner.id)
    assert [(balance.currency, balance.net_minor) for balance in remaining] == [
        ("EUR", -1000)
    ]


def test_balances_text_separates_directions_and_escapes_names() -> None:
    entries = (
        BalanceDTO(uuid4(), "Alice <Admin>", "EUR", -1250, "alice"),
        BalanceDTO(uuid4(), "Bob & Carol", "USD", 825, "bob"),
    )

    text = balances_text(entries, Language.ENGLISH)

    assert "<b>You owe</b>:\n• 🔴 ▼ Alice &lt;Admin&gt; (@alice) — 12.50 EUR" in text
    assert "<b>You are owed</b>:\n• 🟢 ▲ Bob &amp; Carol (@bob) — 8.25 USD" in text


def test_balances_text_has_an_empty_state() -> None:
    assert "no outstanding balances" in balances_text((), Language.ENGLISH)


def test_balances_keyboard_offers_one_drill_down_per_person() -> None:
    other_id = uuid4()
    entries = (
        BalanceDTO(other_id, "Alice", "EUR", -1250, "alice"),
        BalanceDTO(other_id, "Alice", "USD", 800, "alice"),
    )

    keyboard = balances_keyboard(entries, Language.ENGLISH)

    callback = keyboard.inline_keyboard[0][0].callback_data
    assert callback is not None
    assert callback.startswith("balance:person:")
    assert uuid_from_token(callback.rsplit(":", 1)[1]) == other_id
    assert "Alice (@alice)" in keyboard.inline_keyboard[0][0].text
    assert len(keyboard.inline_keyboard) == 2
    assert keyboard.inline_keyboard[-1][0].callback_data == "menu:show"


def test_person_balance_view_offers_each_currency_and_shared_history() -> None:
    other_id = uuid4()
    entries = (
        BalanceDTO(other_id, "Alice", "EUR", -1250, "alice"),
        BalanceDTO(other_id, "Alice", "USD", 800, "alice"),
    )

    text = person_balances_text(entries, Language.ENGLISH)
    keyboard = person_balance_keyboard(entries, Language.ENGLISH)
    callbacks = [row[0].callback_data for row in keyboard.inline_keyboard]

    assert "Balance with Alice (@alice)" in text
    assert "🔴 ▼ You owe <b>12.50 EUR</b>" in text
    assert "🟢 ▲ You are owed <b>8.00 USD</b>" in text
    assert callbacks == [
        f"settle:select:{other_id}:EUR",
        f"settle:select:{other_id}:USD",
        f"balance:history:{uuid_token(other_id)}",
        "menu:balances",
    ]
    assert all(callback is not None and len(callback) <= 64 for callback in callbacks)


def test_uuid_callback_token_round_trips() -> None:
    value = uuid4()

    token = uuid_token(value)

    assert len(token) == 22
    assert uuid_from_token(token) == value
    with pytest.raises(ValueError):
        uuid_from_token("too-short")
