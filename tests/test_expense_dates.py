from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from splitnshare.application.dto import CreateExpenseCommand, TelegramIdentity
from splitnshare.application.services import ExpenseQueryService, ExpenseService, UserService
from splitnshare.domain.contexts import DirectExpenseContext
from splitnshare.domain.enums import Language, SplitMethod
from splitnshare.domain.errors import ValidationError
from splitnshare.domain.money import Money
from splitnshare.infrastructure.database import create_session_factory
from splitnshare.infrastructure.models import Base
from splitnshare.infrastructure.unit_of_work import SqlAlchemyUnitOfWorkFactory
from splitnshare.presentation.datetimes import format_local_datetime, parse_local_datetime
from splitnshare.presentation.keyboards import expense_date_keyboard


def test_expense_date_keyboard_contains_presets_and_custom_option() -> None:
    keyboard = expense_date_keyboard(Language.ENGLISH)
    callbacks = {
        button.callback_data
        for row in keyboard.inline_keyboard
        for button in row
    }

    assert {
        "expense:date:now",
        "expense:date:minus_30m",
        "expense:date:minus_1h",
        "expense:date:minus_2h",
        "expense:date:minus_3h",
        "expense:date:custom",
        "expense:date:back",
        "expense:cancel",
    } == callbacks


def test_custom_local_datetime_is_converted_to_utc_and_formatted_back() -> None:
    occurred_at = parse_local_datetime("02.09.2026 18:30", "Europe/Madrid")

    assert occurred_at == datetime(2026, 9, 2, 16, 30, tzinfo=UTC)
    assert format_local_datetime(
        occurred_at, "Europe/Madrid", Language.ENGLISH
    ) == "2026-09-02 18:30 CEST"


def test_custom_datetime_can_omit_current_year() -> None:
    occurred_at = parse_local_datetime(
        "02.09 18:30",
        "Europe/Madrid",
        now=datetime(2026, 1, 10, tzinfo=UTC),
    )

    assert occurred_at == datetime(2026, 9, 2, 16, 30, tzinfo=UTC)


def test_nonexistent_daylight_saving_time_is_rejected() -> None:
    with pytest.raises(ValidationError):
        parse_local_datetime("29.03.2026 02:30", "Europe/Madrid")


@pytest.fixture
async def expense_date_services():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = SqlAlchemyUnitOfWorkFactory(create_session_factory(engine))
    yield UserService(factory), ExpenseService(factory), ExpenseQueryService(factory)
    await engine.dispose()


async def test_expenses_are_listed_by_occurred_date(expense_date_services) -> None:
    users, expenses, queries = expense_date_services
    owner = await users.register_or_update(
        TelegramIdentity(telegram_user_id=1001, first_name="Owner")
    )
    friend = await users.register_or_update(
        TelegramIdentity(telegram_user_id=1002, first_name="Friend")
    )

    async def create(description: str, occurred_at: datetime) -> None:
        await expenses.create(
            CreateExpenseCommand(
                creator_person_id=owner.id,
                description=description,
                total=Money(1000, "USD"),
                participant_ids=(owner.id, friend.id),
                split_method=SplitMethod.EQUAL,
                context=DirectExpenseContext(),
                occurred_at=occurred_at,
            )
        )

    await create("Later occurrence", datetime(2026, 9, 2, 18, tzinfo=UTC))
    await create("Earlier occurrence", datetime(2026, 9, 1, 18, tzinfo=UTC))

    page = await queries.list_for_person(owner.id)

    assert [expense.description for expense in page.items] == [
        "Later occurrence",
        "Earlier occurrence",
    ]
    assert page.items[0].occurred_at == datetime(2026, 9, 2, 18, tzinfo=UTC)


async def test_expense_rejects_naive_datetime(expense_date_services) -> None:
    users, expenses, _ = expense_date_services
    owner = await users.register_or_update(
        TelegramIdentity(telegram_user_id=1003, first_name="Owner")
    )
    friend = await users.register_or_update(
        TelegramIdentity(telegram_user_id=1004, first_name="Friend")
    )

    with pytest.raises(ValidationError):
        await expenses.create(
            CreateExpenseCommand(
                creator_person_id=owner.id,
                description="Naive time",
                total=Money(1000, "USD"),
                participant_ids=(owner.id, friend.id),
                split_method=SplitMethod.EQUAL,
                context=DirectExpenseContext(),
                occurred_at=datetime(2026, 9, 2, 18),
            )
        )
