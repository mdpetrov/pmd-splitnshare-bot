"""Exercise durable drafts, isolation, navigation, and transactional completion."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.types import Chat, Message, Update, User
from sqlalchemy.ext.asyncio import create_async_engine

from splitnshare.application.dto import CreateExpenseCommand, TelegramIdentity
from splitnshare.application.services import ExpenseService, UserService
from splitnshare.domain.contexts import DirectExpenseContext
from splitnshare.domain.enums import Language, SplitMethod
from splitnshare.domain.errors import ConflictError, NotFoundError, ValidationError
from splitnshare.domain.money import Money
from splitnshare.infrastructure.database import create_session_factory
from splitnshare.infrastructure.fsm_storage import SqlAlchemyFSMStorage
from splitnshare.infrastructure.models import Base
from splitnshare.infrastructure.unit_of_work import SqlAlchemyUnitOfWorkFactory
from splitnshare.presentation.middleware import DraftNavigationMiddleware
from splitnshare.presentation.routers.expenses import render_expense_draft
from splitnshare.presentation.states import AddExpenseStates, FriendStates


@pytest.fixture
async def draft_backend(tmp_path):
    url = f"sqlite+aiosqlite:///{(tmp_path / 'drafts.db').as_posix()}"
    engine = create_async_engine(url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = create_session_factory(engine)
    yield SimpleNamespace(
        url=url, engine=engine, factory=factory, storage=SqlAlchemyFSMStorage(factory),
    )
    await engine.dispose()


def _key(user_id=101, bot_id=1):
    return StorageKey(bot_id=bot_id, chat_id=user_id, user_id=user_id)


async def _seed(storage, key, description="Dinner", creator_id=None, other_id=None):
    identifier = uuid4()
    owner = creator_id or uuid4()
    other = other_id or uuid4()
    state = FSMContext(storage=storage, key=key)
    await state.clear()
    await state.update_data(
        draft_id=str(identifier), creator_id=str(owner), description=description,
        total_minor=1000, currency="EUR", timezone="UTC",
        occurred_at=datetime(2026, 9, 11, tzinfo=UTC).isoformat(), payer_id=str(owner),
        participants=[{"id": str(owner), "name": "Owner"}, {"id": str(other), "name": "Friend"}],
        split_method="equal",
    )
    await state.set_state(AddExpenseStates.confirm)
    return identifier, state


async def test_state_and_partial_shares_survive_new_engine(draft_backend):
    identifier, state = await _seed(draft_backend.storage, _key())
    await state.set_state(AddExpenseStates.exact_amount)
    await state.update_data(split_method="exact", exact_amounts={"first": 200}, exact_index=1)
    expected = await state.get_data()
    await draft_backend.engine.dispose()
    restarted_engine = create_async_engine(draft_backend.url)
    try:
        restarted = SqlAlchemyFSMStorage(create_session_factory(restarted_engine))
        assert await restarted.get_state(_key()) == AddExpenseStates.exact_amount.state
        assert await restarted.get_data(_key()) == expected
        saved = await restarted.list_drafts(_key())
        assert saved[0].id == identifier
        assert saved[0].data["exact_amounts"] == {"first": 200}
    finally:
        await restarted_engine.dispose()


async def test_non_expense_form_state_also_survives_new_storage(draft_backend):
    await draft_backend.storage.set_state(_key(), FriendStates.renaming)
    await draft_backend.storage.set_data(_key(), {"friend_id": str(uuid4()), "alias": "New name"})
    restarted = SqlAlchemyFSMStorage(draft_backend.factory)
    assert await restarted.get_state(_key()) == FriendStates.renaming.state
    assert (await restarted.get_data(_key()))["alias"] == "New name"
    assert await restarted.list_drafts(_key()) == ()


async def test_group_expense_context_survives_pausing_and_restarting(draft_backend):
    identifier, state = await _seed(draft_backend.storage, _key())
    group_data = {
        "group_id": str(uuid4()), "group_name": "Trip", "group_currency": "JPY",
        "group_members": (await state.get_data())["participants"],
    }
    await state.update_data(**group_data)
    await state.clear()
    restarted = SqlAlchemyFSMStorage(draft_backend.factory)
    saved = await restarted.resume(_key(), identifier)
    assert all(saved.data[key] == value for key, value in group_data.items())


async def test_starting_another_expense_and_clearing_keeps_both(draft_backend):
    first, _ = await _seed(draft_backend.storage, _key(), "Dinner")
    second, state = await _seed(draft_backend.storage, _key(), "Taxi")
    await state.clear()
    assert await state.get_state() is None
    saved_ids = {draft.id for draft in await draft_backend.storage.list_drafts(_key())}
    assert saved_ids == {first, second}
    await draft_backend.storage.resume(_key(), first)
    assert (await state.get_data())["description"] == "Dinner"
    await state.update_data(description="Edited dinner")
    await draft_backend.storage.resume(_key(), second)
    assert (await state.get_data())["description"] == "Taxi"
    restored = await draft_backend.storage.resume(_key(), first)
    assert restored.data["description"] == "Edited dinner"


@pytest.mark.parametrize("other_key", [_key(102), _key(bot_id=2)])
async def test_other_users_and_bots_cannot_access_drafts(draft_backend, other_key):
    identifier, _ = await _seed(draft_backend.storage, _key())
    assert await draft_backend.storage.list_drafts(other_key) == ()
    with pytest.raises(NotFoundError):
        await draft_backend.storage.resume(other_key, identifier)
    with pytest.raises(NotFoundError):
        await draft_backend.storage.discard(other_key, identifier)
    assert len(await draft_backend.storage.list_drafts(_key())) == 1


async def test_explicit_discard_removes_only_selected_draft(draft_backend):
    first, _ = await _seed(draft_backend.storage, _key())
    second, state = await _seed(draft_backend.storage, _key())
    await draft_backend.storage.discard(_key(), first)
    assert (await state.get_data())["draft_id"] == str(second)
    await draft_backend.storage.discard(_key(), second)
    assert await state.get_state() is None
    assert await state.get_data() == {}
    assert await draft_backend.storage.list_drafts(_key()) == ()


async def test_save_consumes_draft_atomically_and_prevents_retry(draft_backend):
    uow = SqlAlchemyUnitOfWorkFactory(draft_backend.factory)
    users, expenses = UserService(uow), ExpenseService(uow)
    owner = await users.register_or_update(
        TelegramIdentity(telegram_user_id=101, first_name="Owner")
    )
    friend = await users.register_or_update(
        TelegramIdentity(telegram_user_id=102, first_name="Friend")
    )
    identifier, state = await _seed(
        draft_backend.storage, _key(), creator_id=owner.id, other_id=friend.id,
    )
    command = CreateExpenseCommand(
        creator_person_id=owner.id, description="Dinner", total=Money(1000, "EUR"),
        participant_ids=(owner.id, friend.id), split_method=SplitMethod.EQUAL,
        context=DirectExpenseContext(), draft_id=identifier,
    )
    expense = await expenses.create(command)
    assert expense.total == Money(1000, "EUR")
    # No presentation-layer clear is needed to survive a crash immediately after commit.
    assert await state.get_state() is None
    assert await state.get_data() == {}
    assert await draft_backend.storage.list_drafts(_key()) == ()
    with pytest.raises(ConflictError):
        await expenses.create(command)


async def test_failed_save_keeps_the_draft(draft_backend):
    uow = SqlAlchemyUnitOfWorkFactory(draft_backend.factory)
    users, expenses = UserService(uow), ExpenseService(uow)
    owner = await users.register_or_update(
        TelegramIdentity(telegram_user_id=101, first_name="Owner")
    )
    missing_person = uuid4()
    identifier, state = await _seed(
        draft_backend.storage, _key(), creator_id=owner.id, other_id=missing_person,
    )
    with pytest.raises(NotFoundError):
        await expenses.create(CreateExpenseCommand(
            creator_person_id=owner.id, description="Dinner", total=Money(1000, "EUR"),
            participant_ids=(owner.id, missing_person), split_method=SplitMethod.EQUAL,
            context=DirectExpenseContext(), draft_id=identifier,
        ))
    assert await state.get_state() == AddExpenseStates.confirm.state
    assert (await draft_backend.storage.list_drafts(_key()))[0].id == identifier


async def test_account_deletion_purges_drafts_without_recreating_identity(draft_backend):
    users = UserService(SqlAlchemyUnitOfWorkFactory(draft_backend.factory))
    owner = await users.register_or_update(
        TelegramIdentity(telegram_user_id=101, first_name="Owner")
    )
    _, state = await _seed(draft_backend.storage, _key(), creator_id=owner.id)
    assert await users.delete_account(owner.id)
    await state.clear()
    assert await draft_backend.storage.get_state(_key()) is None
    assert await draft_backend.storage.list_drafts(_key()) == ()


async def test_navigation_does_not_overwrite_expense_description(draft_backend):
    identifier, state = await _seed(draft_backend.storage, _key())
    await state.set_state(AddExpenseStates.description)
    event = Update(update_id=1, message=Message(
        message_id=1, date=datetime.now(UTC), chat=Chat(id=101, type="private"),
        from_user=User(id=101, is_bot=False, first_name="Owner"), text="👥 Friends",
    ))
    handler = AsyncMock()
    data = {"state": state, "raw_state": AddExpenseStates.description.state}
    await DraftNavigationMiddleware()(handler, event, data)
    assert data["raw_state"] is None
    assert await state.get_state() is None
    saved = await draft_backend.storage.resume(_key(), identifier)
    assert saved.data["description"] == "Dinner"
    handler.assert_awaited_once()


async def test_last_share_checkpoint_recovers_review_without_reentry(draft_backend):
    _, state = await _seed(draft_backend.storage, _key())
    participants = (await state.get_data())["participants"]
    await state.set_state(AddExpenseStates.exact_amount)
    await state.update_data(
        split_method="exact", exact_index=2,
        exact_amounts={participants[0]["id"]: 400, participants[1]["id"]: 600},
    )
    message = SimpleNamespace(answer=AsyncMock())
    await render_expense_draft(message, state, Language.ENGLISH)
    assert await state.get_state() == AddExpenseStates.confirm.state
    assert "10.00 EUR" in message.answer.call_args.args[0]


async def test_unrecognized_draft_step_does_not_destroy_data(draft_backend):
    _, state = await _seed(draft_backend.storage, _key())
    await state.set_state("AddExpenseStates:future_step")
    before = await state.get_data()
    with pytest.raises(ValidationError):
        await render_expense_draft(SimpleNamespace(answer=AsyncMock()), state, Language.ENGLISH)
    assert await state.get_data() == before
