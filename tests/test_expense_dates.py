from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from splitnshare.application.dto import CreateExpenseCommand, ExpenseDTO, TelegramIdentity
from splitnshare.application.services import ExpenseQueryService, ExpenseService, UserService
from splitnshare.domain.contexts import DirectExpenseContext
from splitnshare.domain.enums import Language, SplitMethod
from splitnshare.domain.errors import ValidationError
from splitnshare.domain.money import Money
from splitnshare.infrastructure.database import create_session_factory
from splitnshare.infrastructure.models import Base
from splitnshare.infrastructure.unit_of_work import SqlAlchemyUnitOfWorkFactory
from splitnshare.presentation.datetimes import (
    format_local_date,
    format_local_datetime,
    parse_local_datetime,
)
from splitnshare.presentation.keyboards import expense_date_keyboard, person_history_keyboard


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
    assert format_local_date(
        occurred_at, "Europe/Madrid", Language.ENGLISH
    ) == "2026-09-02"


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


async def test_shared_history_filters_people_paginates_and_excludes_deleted(
    expense_date_services,
) -> None:
    users, expenses, queries = expense_date_services
    owner = await users.register_or_update(
        TelegramIdentity(telegram_user_id=1010, first_name="Owner")
    )
    alice = await users.register_or_update(
        TelegramIdentity(telegram_user_id=1011, first_name="Alice")
    )
    bob = await users.register_or_update(
        TelegramIdentity(telegram_user_id=1012, first_name="Bob")
    )

    async def create(
        description: str,
        participant_ids: tuple[UUID, ...],
        occurred_at: datetime,
    ) -> ExpenseDTO:
        return await expenses.create(
            CreateExpenseCommand(
                creator_person_id=owner.id,
                description=description,
                total=Money(1200, "USD"),
                participant_ids=participant_ids,
                split_method=SplitMethod.EQUAL,
                context=DirectExpenseContext(),
                occurred_at=occurred_at,
            )
        )

    older = await create(
        "Older with Alice",
        (owner.id, alice.id),
        datetime(2026, 9, 1, 18, tzinfo=UTC),
    )
    await create(
        "Only with Bob",
        (owner.id, bob.id),
        datetime(2026, 9, 2, 18, tzinfo=UTC),
    )
    await create(
        "Newer with Alice",
        (owner.id, alice.id, bob.id),
        datetime(2026, 9, 3, 18, tzinfo=UTC),
    )

    first_page = await queries.list_shared(owner.id, alice.id, limit=1)
    assert first_page.next_cursor is not None
    history_keyboard = person_history_keyboard(first_page, alice.id, Language.ENGLISH)
    history_callbacks = [
        button.callback_data
        for row in history_keyboard.inline_keyboard
        for button in row
    ]
    second_page = await queries.list_shared(
        owner.id, alice.id, cursor=first_page.next_cursor, limit=1
    )

    assert [item.description for item in first_page.items] == ["Newer with Alice"]
    assert history_callbacks[0] is not None and history_callbacks[0].startswith("bhv:")
    assert history_callbacks[1] is not None and history_callbacks[1].startswith("bhp:")
    assert all(
        callback is not None and len(callback) <= 64
        for callback in history_callbacks
    )
    assert [item.description for item in second_page.items] == ["Older with Alice"]
    assert second_page.next_cursor is None

    assert await expenses.delete(owner.id, older.id)
    remaining = await queries.list_shared(owner.id, alice.id)
    assert [item.description for item in remaining.items] == ["Newer with Alice"]

    with pytest.raises(ValidationError):
        await queries.list_shared(owner.id, owner.id)
