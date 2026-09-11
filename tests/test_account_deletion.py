"""Cover settlement eligibility and changes between deletion request and confirmation."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from splitnshare.application.dto import (
    BalanceDTO,
    CreateExpenseCommand,
    SettleBalanceCommand,
    TelegramIdentity,
)
from splitnshare.application.services import (
    BalanceQueryService,
    ExpenseQueryService,
    ExpenseService,
    GuestService,
    SettlementService,
    UserService,
    UserSettingsService,
)
from splitnshare.domain.contexts import DirectExpenseContext
from splitnshare.domain.enums import Language, SplitMethod
from splitnshare.domain.errors import UnsettledAccountError
from splitnshare.domain.money import Money
from splitnshare.infrastructure.database import create_session_factory
from splitnshare.infrastructure.models import Base
from splitnshare.infrastructure.unit_of_work import SqlAlchemyUnitOfWorkFactory
from splitnshare.presentation.i18n import translate
from splitnshare.presentation.routers.account import (
    confirm_account_deletion,
    request_account_deletion,
)
from splitnshare.presentation.states import DeleteAccountStates


@pytest.fixture
async def account_services():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = SqlAlchemyUnitOfWorkFactory(create_session_factory(engine))
    yield SimpleNamespace(
        users=UserService(factory), expenses=ExpenseService(factory),
        settlements=SettlementService(factory), balances=BalanceQueryService(factory),
        settings=UserSettingsService(factory), guests=GuestService(factory),
        queries=ExpenseQueryService(factory),
    )
    await engine.dispose()


async def _people(services):
    owner = await services.users.register_or_update(
        TelegramIdentity(telegram_user_id=2101, first_name="Owner"),
    )
    friend = await services.users.register_or_update(
        TelegramIdentity(telegram_user_id=2102, first_name="Friend"),
    )
    await services.settings.get_or_create(owner.id)
    return owner, friend


async def _expense(services, payer, other, currency="EUR"):
    return await services.expenses.create(CreateExpenseCommand(
        creator_person_id=payer.id, description="Shared dinner", total=Money(1000, currency),
        participant_ids=(payer.id, other.id), split_method=SplitMethod.EQUAL,
        context=DirectExpenseContext(),
    ))


@pytest.mark.parametrize("role", ["payer", "debtor"])
async def test_deletion_rejects_both_payables_and_receivables(account_services, role):
    owner, friend = await _people(account_services)
    expense = await _expense(account_services, owner, friend)
    target = owner if role == "payer" else friend
    before = await account_services.balances.get_balances(target.id)
    with pytest.raises(UnsettledAccountError):
        await account_services.users.delete_account(target.id)
    assert await account_services.users.find_registered_target(target.telegram_user_id) == target
    assert await account_services.balances.get_balances(target.id) == before
    saved = await account_services.queries.get_details(target.id, expense.id)
    assert saved.total == expense.total
    assert await account_services.settings.find_by_telegram_id(2101) is not None


@pytest.mark.parametrize("offset_kind", ["other_person", "other_currency"])
async def test_deletion_does_not_net_unrelated_balances(account_services, offset_kind):
    owner, friend = await _people(account_services)
    await _expense(account_services, owner, friend)
    if offset_kind == "other_person":
        other = await account_services.users.register_or_update(
            TelegramIdentity(telegram_user_id=2103, first_name="Other"),
        )
        await _expense(account_services, other, owner)
    else:
        await _expense(account_services, friend, owner, "USD")
    balances = await account_services.balances.get_balances(owner.id)
    assert len(balances) == 2
    assert sum(balance.net_minor for balance in balances) == 0
    with pytest.raises(UnsettledAccountError):
        await account_services.users.delete_account(owner.id)


async def test_partial_payment_blocks_deletion_until_fully_settled(account_services):
    owner, friend = await _people(account_services)
    expense = await _expense(account_services, owner, friend)
    await account_services.settlements.settle(SettleBalanceCommand(
        actor_person_id=friend.id, other_person_id=owner.id,
        amount=Money(200, "EUR"), context=DirectExpenseContext(),
    ))
    with pytest.raises(UnsettledAccountError):
        await account_services.users.delete_account(owner.id)
    await account_services.settlements.settle(SettleBalanceCommand(
        actor_person_id=friend.id, other_person_id=owner.id,
        amount=Money(300, "EUR"), context=DirectExpenseContext(),
    ))
    assert await account_services.users.delete_account(owner.id)
    assert await account_services.users.find_registered_target(2101) is None
    assert await account_services.settings.find_by_telegram_id(2101) is None
    saved = await account_services.queries.get_details(friend.id, expense.id)
    assert saved.total == expense.total
    assert await account_services.balances.get_balances(friend.id) == ()
    assert not await account_services.users.delete_account(owner.id)


async def test_deletion_allows_empty_account_and_ignores_deleted_expenses(account_services):
    owner, friend = await _people(account_services)
    expense = await _expense(account_services, owner, friend)
    await account_services.expenses.delete(owner.id, expense.id)
    assert await account_services.users.delete_account(owner.id)
    assert await account_services.users.delete_account(friend.id)


async def test_guest_balance_prevents_account_deletion(account_services):
    owner, _ = await _people(account_services)
    guest = await account_services.guests.create_manual_guest(owner.id, "Guest")
    await _expense(account_services, owner, guest)
    with pytest.raises(UnsettledAccountError):
        await account_services.users.delete_account(owner.id)
    assert len(await account_services.guests.list_owned_guests(owner.id)) == 1


@pytest.mark.parametrize("amount", [-500, 500])
async def test_request_with_balance_never_shows_confirmation(amount):
    message = SimpleNamespace(from_user=SimpleNamespace(id=2101), answer=AsyncMock())
    state = SimpleNamespace(clear=AsyncMock(), set_state=AsyncMock())
    services = SimpleNamespace(
        users=SimpleNamespace(find_registered_target=AsyncMock(
            return_value=SimpleNamespace(id=uuid4()),
        )),
        balances=SimpleNamespace(get_balances=AsyncMock(return_value=(
            BalanceDTO(other_person_id=uuid4(), other_name="Friend", currency="EUR",
                       net_minor=amount),
        ))),
    )
    await request_account_deletion(message, state, services, Language.ENGLISH)
    state.set_state.assert_not_awaited()
    expected = translate(Language.ENGLISH, "delete_account_unsettled")
    assert message.answer.call_args.args[0] == expected


async def test_confirmation_handles_a_balance_added_after_the_prompt(monkeypatch):
    message = SimpleNamespace(edit_reply_markup=AsyncMock(), answer=AsyncMock())
    callback = SimpleNamespace(from_user=SimpleNamespace(id=2101), answer=AsyncMock())
    monkeypatch.setattr(
        "splitnshare.presentation.routers.account.callback_message", lambda _: message,
    )
    state = SimpleNamespace(
        get_state=AsyncMock(return_value=DeleteAccountStates.confirm.state), clear=AsyncMock(),
    )
    services = SimpleNamespace(users=SimpleNamespace(
        find_registered_target=AsyncMock(return_value=SimpleNamespace(id=uuid4())),
        delete_account=AsyncMock(side_effect=UnsettledAccountError()),
    ))
    await confirm_account_deletion(callback, state, services, Language.ENGLISH)
    state.clear.assert_awaited_once()
    message.edit_reply_markup.assert_awaited_once_with(reply_markup=None)
    expected = translate(Language.ENGLISH, "delete_account_unsettled")
    assert message.answer.call_args.args[0] == expected
    callback.answer.assert_awaited_once()
