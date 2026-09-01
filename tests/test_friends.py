from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import create_async_engine

from splitnshare.application.dto import (
    CreateExpenseCommand,
    ExpensePage,
    SharedTelegramUser,
    TelegramIdentity,
    TransferGuestCommand,
)
from splitnshare.application.services import (
    BalanceQueryService,
    ExpenseQueryService,
    ExpenseService,
    FriendService,
    GuestService,
    UserService,
)
from splitnshare.domain.contexts import DirectExpenseContext
from splitnshare.domain.enums import FriendSource, SplitMethod
from splitnshare.domain.errors import ValidationError
from splitnshare.domain.money import Money
from splitnshare.infrastructure.database import create_session_factory
from splitnshare.infrastructure.models import Base, FriendshipModel
from splitnshare.infrastructure.unit_of_work import SqlAlchemyUnitOfWorkFactory
from splitnshare.presentation.formatters import expense_text
from splitnshare.presentation.keyboards import expense_list_keyboard


@pytest.fixture
async def friend_services():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = create_session_factory(engine)
    uow = SqlAlchemyUnitOfWorkFactory(factory)
    yield (
        factory,
        UserService(uow),
        GuestService(uow),
        FriendService(uow),
        ExpenseService(uow),
    )
    await engine.dispose()


async def _register(users: UserService, telegram_id: int, name: str):
    return await users.register_or_update(
        TelegramIdentity(telegram_user_id=telegram_id, first_name=name)
    )


async def _equal_expense(
    expenses: ExpenseService, creator_id: UUID, participant_id: UUID
) -> None:
    await expenses.create(
        CreateExpenseCommand(
            creator_person_id=creator_id,
            description="Friendship expense",
            total=Money(1000, "USD"),
            participant_ids=(creator_id, participant_id),
            split_method=SplitMethod.EQUAL,
            context=DirectExpenseContext(),
        )
    )


async def test_adding_friend_is_private_asymmetric_and_idempotent(friend_services) -> None:
    _, users, _, friends, _ = friend_services
    owner = await _register(users, 601, "Owner")
    target = await _register(users, 602, "Target")
    shared = SharedTelegramUser(telegram_user_id=602, first_name="Target")

    first = await friends.add_shared_user(owner.id, shared)
    repeated = await friends.add_shared_user(owner.id, shared)

    assert first.person_id == target.id
    assert repeated.person_id == target.id
    assert first.source is FriendSource.DIRECT
    assert len(await friends.list_friends(owner.id)) == 1
    assert await friends.list_friends(target.id) == ()


async def test_user_cannot_add_themselves(friend_services) -> None:
    _, users, _, friends, _ = friend_services
    owner = await _register(users, 603, "Owner")

    with pytest.raises(ValidationError):
        await friends.add_shared_user(
            owner.id,
            SharedTelegramUser(telegram_user_id=603, first_name="Owner"),
        )


async def test_telegram_guest_username_is_stored_and_refreshed(friend_services) -> None:
    _, users, guests, friends, _ = friend_services
    owner = await _register(users, 611, "Owner")

    created = await friends.add_shared_user(
        owner.id,
        SharedTelegramUser(
            telegram_user_id=612,
            first_name="Guest",
            username="original_name",
        ),
    )
    refreshed = await friends.add_shared_user(
        owner.id,
        SharedTelegramUser(
            telegram_user_id=612,
            first_name="Guest",
            username="updated_name",
        ),
    )

    assert created.username == "original_name"
    assert refreshed.username == "updated_name"
    assert (await guests.list_owned_guests(owner.id))[0].username == "updated_name"


async def test_transaction_views_include_registered_and_guest_usernames(
    friend_services,
) -> None:
    _, users, guests, _, expenses = friend_services
    owner = await users.register_or_update(
        TelegramIdentity(
            telegram_user_id=613,
            first_name="Owner",
            username="expense_owner",
        )
    )
    guest = await guests.get_or_create_telegram_guest(
        owner.id,
        SharedTelegramUser(
            telegram_user_id=614,
            first_name="Guest",
            username="expense_guest",
        ),
    )

    expense = await expenses.create(
        CreateExpenseCommand(
            creator_person_id=owner.id,
            description="Named participants",
            total=Money(1000, "USD"),
            participant_ids=(owner.id, guest.id),
            split_method=SplitMethod.EQUAL,
            context=DirectExpenseContext(),
        )
    )

    details = expense_text(expense)
    list_keyboard = expense_list_keyboard(ExpensePage((expense,), None))
    assert "Owner (@expense_owner)" in details
    assert "Guest (@expense_guest)" in details
    assert "Owner (@expense_owner)" in list_keyboard.inline_keyboard[0][0].text


async def test_friend_removal_is_owner_scoped_idempotent_and_keeps_guest(
    friend_services,
) -> None:
    _, users, guests, friends, _ = friend_services
    owner = await _register(users, 615, "Owner")
    other_user = await _register(users, 616, "Other")
    guest = await friends.add_manual_guest(owner.id, "Removable guest")

    assert not await friends.remove_friend(other_user.id, guest.person_id)
    assert await friends.remove_friend(owner.id, guest.person_id)
    assert not await friends.remove_friend(owner.id, guest.person_id)
    assert await friends.list_friends(owner.id) == ()
    assert [item.person_id for item in await guests.list_owned_guests(owner.id)] == [
        guest.person_id
    ]


async def test_expenses_and_balances_survive_removal_and_new_expense_reactivates_friend(
    friend_services,
) -> None:
    factory, users, _, friends, expenses = friend_services
    owner = await _register(users, 617, "Owner")
    target = await _register(users, 618, "Target")
    expense = await expenses.create(
        CreateExpenseCommand(
            creator_person_id=owner.id,
            description="Before removal",
            total=Money(1000, "USD"),
            participant_ids=(owner.id, target.id),
            split_method=SplitMethod.EQUAL,
            context=DirectExpenseContext(),
        )
    )

    assert await friends.remove_friend(owner.id, target.id)
    uow = SqlAlchemyUnitOfWorkFactory(factory)
    assert (await ExpenseQueryService(uow).get_details(owner.id, expense.id)).id == expense.id
    balances = await BalanceQueryService(uow).get_balances(owner.id)
    assert [(balance.other_person_id, balance.net_minor) for balance in balances] == [
        (target.id, 500)
    ]

    await _equal_expense(expenses, owner.id, target.id)
    assert [friend.person_id for friend in await friends.list_friends(owner.id)] == [
        target.id
    ]


async def test_expense_automatically_adds_participants_as_friends(friend_services) -> None:
    factory, users, _, friends, expenses = friend_services
    owner = await _register(users, 604, "Owner")
    target = await _register(users, 605, "Target")

    await _equal_expense(expenses, owner.id, target.id)
    await _equal_expense(expenses, owner.id, target.id)

    listed = await friends.list_friends(owner.id)
    assert len(listed) == 1
    assert listed[0].person_id == target.id
    assert listed[0].source is FriendSource.EXPENSE
    async with factory() as session:
        count = await session.scalar(select(func.count()).select_from(FriendshipModel))
        assert count == 1


async def test_guest_transfer_deduplicates_friendships(friend_services) -> None:
    _, users, guests, friends, expenses = friend_services
    owner = await _register(users, 606, "Owner")
    target = await _register(users, 607, "Target")
    guest = await guests.create_manual_guest(owner.id, "Target guest")

    await _equal_expense(expenses, owner.id, guest.id)
    await _equal_expense(expenses, owner.id, target.id)
    result = await guests.transfer_guest(
        TransferGuestCommand(owner.id, guest.id, target.id)
    )

    listed = await friends.list_friends(owner.id)
    assert [friend.person_id for friend in listed] == [target.id]
    assert result.affected_counts["friendships"] == 1
    assert result.affected_counts["duplicate_friendships"] == 1


async def test_guest_transfer_updates_every_owners_friend_list(friend_services) -> None:
    _, users, guests, friends, expenses = friend_services
    owner = await _register(users, 608, "Owner")
    target = await _register(users, 609, "Target")
    observer = await _register(users, 610, "Observer")
    guest = await guests.create_manual_guest(owner.id, "Target guest")

    await _equal_expense(expenses, observer.id, guest.id)
    await _equal_expense(expenses, target.id, guest.id)
    preview = await guests.preview_transfer(
        TransferGuestCommand(owner.id, guest.id, target.id)
    )
    result = await guests.transfer_guest(
        TransferGuestCommand(owner.id, guest.id, target.id)
    )

    assert preview.friendship_count == 2
    assert [friend.person_id for friend in await friends.list_friends(observer.id)] == [
        target.id
    ]
    assert await friends.list_friends(target.id) == ()
    assert result.affected_counts["friendships"] == 2
    assert result.affected_counts["self_friendships"] == 1
