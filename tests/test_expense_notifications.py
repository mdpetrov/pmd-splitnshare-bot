from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from splitnshare.application.dto import CreateExpenseCommand, TelegramIdentity
from splitnshare.application.services import (
    ExpenseService,
    GuestService,
    UserService,
    UserSettingsService,
)
from splitnshare.domain.contexts import DirectExpenseContext
from splitnshare.domain.enums import Language, SplitMethod
from splitnshare.domain.money import Money
from splitnshare.infrastructure.database import create_session_factory
from splitnshare.infrastructure.models import Base
from splitnshare.infrastructure.unit_of_work import SqlAlchemyUnitOfWorkFactory
from splitnshare.presentation.formatters import expense_notification_text
from splitnshare.presentation.routers.expenses import _notify_expense_participants


@pytest.fixture
async def notification_services():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = SqlAlchemyUnitOfWorkFactory(create_session_factory(engine))
    yield (
        UserService(factory),
        UserSettingsService(factory),
        GuestService(factory),
        ExpenseService(factory),
    )
    await engine.dispose()


async def test_expense_notification_reaches_only_registered_non_creator(
    notification_services,
) -> None:
    users, settings, guests, expenses = notification_services
    creator = await users.register_or_update(
        TelegramIdentity(
            telegram_user_id=1101,
            first_name="John",
            username="johndoe",
        )
    )
    recipient = await users.register_or_update(
        TelegramIdentity(telegram_user_id=1102, first_name="Maria")
    )
    guest = await guests.create_manual_guest(creator.id, "Offline guest")
    await settings.get_or_create(recipient.id, preferred_language="en")
    expense = await expenses.create(
        CreateExpenseCommand(
            creator_person_id=creator.id,
            description="Dinner <night>",
            total=Money(1200, "USD"),
            participant_ids=(creator.id, recipient.id, guest.id),
            split_method=SplitMethod.EQUAL,
            context=DirectExpenseContext(),
        )
    )
    bot = SimpleNamespace(send_message=AsyncMock())
    services = SimpleNamespace(users=users, user_settings=settings)

    await _notify_expense_participants(bot, services, expense)

    bot.send_message.assert_awaited_once()
    telegram_id, text = bot.send_message.await_args.args
    assert telegram_id == 1102
    assert "John (@johndoe)" in text
    assert "Dinner &lt;night&gt;" in text
    assert "🔴 ▼ You owe <b>4.00 USD</b>" in text


async def test_expense_notification_uses_payer_effect(notification_services) -> None:
    users, _, _, expenses = notification_services
    creator = await users.register_or_update(
        TelegramIdentity(telegram_user_id=1111, first_name="John")
    )
    payer = await users.register_or_update(
        TelegramIdentity(telegram_user_id=1112, first_name="Payer")
    )
    expense = await expenses.create(
        CreateExpenseCommand(
            creator_person_id=creator.id,
            payer_person_id=payer.id,
            description="Tickets",
            total=Money(1000, "EUR"),
            participant_ids=(creator.id, payer.id),
            split_method=SplitMethod.EQUAL,
            context=DirectExpenseContext(),
        )
    )

    text = expense_notification_text(expense, payer.id, Language.ENGLISH)

    assert "John (#" in text
    assert "🟢 ▲ You are owed <b>5.00 EUR</b>" in text
    with pytest.raises(ValueError):
        expense_notification_text(expense, creator.id, Language.ENGLISH)
