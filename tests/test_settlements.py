from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from splitnshare.application.dto import (
    CreateExpenseCommand,
    ExpenseActivityDTO,
    SettleBalanceCommand,
    SettlementActivityDTO,
    TelegramIdentity,
    TransferGuestCommand,
)
from splitnshare.application.services import (
    ActivityQueryService,
    BalanceQueryService,
    ExpenseService,
    GuestService,
    SettlementService,
    UserService,
)
from splitnshare.domain.contexts import DirectExpenseContext
from splitnshare.domain.enums import Language, SplitMethod
from splitnshare.domain.errors import ValidationError
from splitnshare.domain.money import Money
from splitnshare.infrastructure.database import create_session_factory
from splitnshare.infrastructure.models import Base
from splitnshare.infrastructure.unit_of_work import SqlAlchemyUnitOfWorkFactory
from splitnshare.presentation.formatters import activity_text
from splitnshare.presentation.keyboards import (
    activity_list_keyboard,
    person_activity_keyboard,
)


@pytest.fixture
async def settlement_services():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = SqlAlchemyUnitOfWorkFactory(create_session_factory(engine))
    yield (
        UserService(factory),
        GuestService(factory),
        ExpenseService(factory),
        SettlementService(factory),
        BalanceQueryService(factory),
        ActivityQueryService(factory),
    )
    await engine.dispose()


async def _register(users: UserService, telegram_id: int, name: str):
    return await users.register_or_update(
        TelegramIdentity(telegram_user_id=telegram_id, first_name=name)
    )


async def _create_debt(expenses, creditor_id, debtor_id, currency: str = "USD"):
    await expenses.create(
        CreateExpenseCommand(
            creator_person_id=creditor_id,
            payer_person_id=creditor_id,
            description="Shared expense",
            total=Money(1000, currency),
            participant_ids=(creditor_id, debtor_id),
            split_method=SplitMethod.EQUAL,
            context=DirectExpenseContext(),
        )
    )


async def test_partial_and_full_settlements_reduce_balance(settlement_services) -> None:
    users, _, expenses, settlements, balances, _ = settlement_services
    creditor = await _register(users, 1101, "Creditor")
    debtor = await _register(users, 1102, "Debtor")
    await _create_debt(expenses, creditor.id, debtor.id)

    partial = await settlements.settle(
        SettleBalanceCommand(
            actor_person_id=debtor.id,
            other_person_id=creditor.id,
            amount=Money(200, "USD"),
            context=DirectExpenseContext(),
            occurred_at=datetime(2026, 9, 2, 12, tzinfo=UTC),
        )
    )

    assert partial.payer_person_id == debtor.id
    assert partial.recipient_person_id == creditor.id
    debtor_balance = await balances.get_balances(debtor.id)
    assert [(item.currency, item.net_minor) for item in debtor_balance] == [
        ("USD", -300)
    ]

    completed = await settlements.settle(
        SettleBalanceCommand(
            actor_person_id=creditor.id,
            other_person_id=debtor.id,
            amount=Money(300, "USD"),
            context=DirectExpenseContext(),
        )
    )

    assert completed.payer_person_id == debtor.id
    assert completed.recipient_person_id == creditor.id
    assert await balances.get_balances(debtor.id) == ()
    assert await balances.get_balances(creditor.id) == ()


async def test_settlement_cannot_exceed_outstanding_balance(
    settlement_services,
) -> None:
    users, _, expenses, settlements, balances, _ = settlement_services
    creditor = await _register(users, 1103, "Creditor")
    debtor = await _register(users, 1104, "Debtor")
    await _create_debt(expenses, creditor.id, debtor.id)

    with pytest.raises(ValidationError):
        await settlements.settle(
            SettleBalanceCommand(
                actor_person_id=debtor.id,
                other_person_id=creditor.id,
                amount=Money(501, "USD"),
                context=DirectExpenseContext(),
            )
        )

    current = await balances.get_balances(debtor.id)
    assert current[0].net_minor == -500


async def test_settlement_changes_only_its_currency(settlement_services) -> None:
    users, _, expenses, settlements, balances, _ = settlement_services
    creditor = await _register(users, 1107, "Creditor")
    debtor = await _register(users, 1108, "Debtor")
    await _create_debt(expenses, creditor.id, debtor.id, "USD")
    await _create_debt(expenses, creditor.id, debtor.id, "EUR")

    await settlements.settle(
        SettleBalanceCommand(
            actor_person_id=debtor.id,
            other_person_id=creditor.id,
            amount=Money(500, "USD"),
            context=DirectExpenseContext(),
        )
    )

    current = await balances.get_balances(debtor.id)
    assert [(item.currency, item.net_minor) for item in current] == [("EUR", -500)]


async def test_guest_transfer_moves_settlement_history(settlement_services) -> None:
    users, guests, expenses, settlements, balances, _ = settlement_services
    owner = await _register(users, 1105, "Owner")
    target = await _register(users, 1106, "Target")
    guest = await guests.create_manual_guest(owner.id, "Temporary")
    await _create_debt(expenses, owner.id, guest.id)
    await settlements.settle(
        SettleBalanceCommand(
            actor_person_id=owner.id,
            other_person_id=guest.id,
            amount=Money(200, "USD"),
            context=DirectExpenseContext(),
        )
    )

    result = await guests.transfer_guest(
        TransferGuestCommand(
            actor_person_id=owner.id,
            guest_person_id=guest.id,
            target_user_person_id=target.id,
        )
    )

    assert result.affected_counts["settlements"] == 1
    owner_balances = await balances.get_balances(owner.id)
    assert [(item.other_person_id, item.net_minor) for item in owner_balances] == [
        (target.id, 300)
    ]


async def test_activity_combines_expenses_and_settlements_with_person_filtering(
    settlement_services,
) -> None:
    users, _, expenses, settlements, _, activities = settlement_services
    creditor = await _register(users, 1121, "Creditor")
    debtor = await _register(users, 1122, "Debtor")
    outsider = await _register(users, 1123, "Outsider")
    expense = await expenses.create(
        CreateExpenseCommand(
            creator_person_id=creditor.id,
            description="Shared lunch",
            total=Money(1000, "USD"),
            participant_ids=(creditor.id, debtor.id),
            split_method=SplitMethod.EQUAL,
            context=DirectExpenseContext(),
            occurred_at=datetime(2026, 9, 1, 12, tzinfo=UTC),
        )
    )
    await expenses.create(
        CreateExpenseCommand(
            creator_person_id=creditor.id,
            description="Unrelated expense",
            total=Money(600, "USD"),
            participant_ids=(creditor.id, outsider.id),
            split_method=SplitMethod.EQUAL,
            context=DirectExpenseContext(),
            occurred_at=datetime(2026, 9, 1, 13, tzinfo=UTC),
        )
    )
    settlement = await settlements.settle(
        SettleBalanceCommand(
            actor_person_id=debtor.id,
            other_person_id=creditor.id,
            amount=Money(200, "USD"),
            context=DirectExpenseContext(),
            occurred_at=datetime(2026, 9, 2, 12, tzinfo=UTC),
        )
    )

    first = await activities.list_for_person(
        creditor.id, other_person_id=debtor.id, limit=1
    )
    assert first.next_cursor is not None
    second = await activities.list_for_person(
        creditor.id,
        other_person_id=debtor.id,
        cursor=first.next_cursor,
        limit=1,
    )

    assert isinstance(first.items[0], SettlementActivityDTO)
    assert first.items[0].settlement.id == settlement.id
    assert isinstance(second.items[0], ExpenseActivityDTO)
    assert second.items[0].expense.id == expense.id
    assert second.next_cursor is None

    creditor_text = activity_text(first.items, creditor.id, Language.ENGLISH)
    debtor_page = await activities.list_for_person(
        debtor.id, other_person_id=creditor.id
    )
    debtor_text = activity_text(debtor_page.items[:1], debtor.id, Language.ENGLISH)
    assert "📅 <b>2026-09-02</b>" in creditor_text
    assert "12:00" not in creditor_text
    assert "🤝 <b>Settlement</b>" in creditor_text
    assert "🟢 ▲ Debtor" in creditor_text
    assert "paid you <b>2.00 USD</b>" in creditor_text
    assert "🔴 ▼ You paid Creditor" in debtor_text

    global_keyboard = activity_list_keyboard(first, Language.ENGLISH)
    person_keyboard = person_activity_keyboard(first, debtor.id, Language.ENGLISH)
    callbacks = [
        button.callback_data
        for keyboard in (global_keyboard, person_keyboard)
        for row in keyboard.inline_keyboard
        for button in row
    ]
    assert all(callback is not None and len(callback) <= 64 for callback in callbacks)

    assert await expenses.delete(creditor.id, expense.id)
    remaining = await activities.list_for_person(
        creditor.id, other_person_id=debtor.id
    )
    assert len(remaining.items) == 1
    assert isinstance(remaining.items[0], SettlementActivityDTO)
