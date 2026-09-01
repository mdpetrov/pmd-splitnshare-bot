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
from splitnshare.presentation.formatters import balances_text


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
        TelegramIdentity(telegram_user_id=802, first_name="Friend")
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

    assert await expenses.delete(owner.id, usd_expense.id)
    remaining = await balances.get_balances(owner.id)
    assert [(balance.currency, balance.net_minor) for balance in remaining] == [
        ("EUR", -1000)
    ]


def test_balances_text_separates_directions_and_escapes_names() -> None:
    entries = (
        BalanceDTO(uuid4(), "Alice <Admin>", "EUR", -1250),
        BalanceDTO(uuid4(), "Bob & Carol", "USD", 825),
    )

    text = balances_text(entries, Language.ENGLISH)

    assert "<b>You owe</b>:\n• Alice &lt;Admin&gt; — 12.50 EUR" in text
    assert "<b>You are owed</b>:\n• Bob &amp; Carol — 8.25 USD" in text


def test_balances_text_has_an_empty_state() -> None:
    assert "no outstanding balances" in balances_text((), Language.ENGLISH)
