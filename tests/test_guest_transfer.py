from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine

from splitnshare.application.dto import (
    CreateExpenseCommand,
    SharedTelegramUser,
    TelegramIdentity,
    TransferGuestCommand,
)
from splitnshare.application.services import (
    ExpenseQueryService,
    ExpenseService,
    GuestService,
    UserService,
)
from splitnshare.domain.contexts import DirectExpenseContext
from splitnshare.domain.enums import (
    GroupRole,
    GuestTransferStatus,
    MembershipStatus,
    SplitMethod,
)
from splitnshare.domain.errors import PermissionDeniedError
from splitnshare.domain.money import Money
from splitnshare.infrastructure.database import create_session_factory
from splitnshare.infrastructure.models import (
    Base,
    DebtModel,
    GroupMembershipModel,
    GroupModel,
    GuestProfileModel,
    PersonModel,
)
from splitnshare.infrastructure.unit_of_work import SqlAlchemyUnitOfWorkFactory


@pytest.fixture
async def app_services():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = create_session_factory(engine)
    uow = SqlAlchemyUnitOfWorkFactory(factory)
    yield (
        factory,
        UserService(uow),
        GuestService(uow),
        ExpenseService(uow),
        ExpenseQueryService(uow),
    )
    await engine.dispose()


async def _register(users: UserService, telegram_id: int, name: str):
    return await users.register_or_update(
        TelegramIdentity(telegram_user_id=telegram_id, first_name=name)
    )


async def test_registration_does_not_merge_matching_telegram_guest(app_services) -> None:
    factory, users, guests, _, _ = app_services
    owner = await _register(users, 1, "Owner")
    guest = await guests.get_or_create_telegram_guest(
        owner.id, SharedTelegramUser(telegram_user_id=2, first_name="Future User")
    )

    registered = await _register(users, 2, "Future User")

    assert registered.id != guest.id
    async with factory() as session:
        profile = await session.get(GuestProfileModel, guest.id)
        person = await session.get(PersonModel, guest.id)
        assert profile is not None and profile.status is GuestTransferStatus.ACTIVE
        assert person is not None and person.inactive_at is None


async def test_telegram_guest_is_reused_only_within_one_owners_address_book(
    app_services,
) -> None:
    _, users, guests, _, _ = app_services
    owner_a = await _register(users, 3, "Owner A")
    owner_b = await _register(users, 4, "Owner B")
    shared = SharedTelegramUser(telegram_user_id=999, first_name="Same Hint")

    first = await guests.get_or_create_telegram_guest(owner_a.id, shared)
    repeated = await guests.get_or_create_telegram_guest(owner_a.id, shared)
    other_owner = await guests.get_or_create_telegram_guest(owner_b.id, shared)

    assert repeated.id == first.id
    assert other_owner.id != first.id


async def test_manual_names_are_never_merged(app_services) -> None:
    _, users, guests, _, _ = app_services
    owner = await _register(users, 5, "Owner")

    first = await guests.create_manual_guest(owner.id, "Alex")
    second = await guests.create_manual_guest(owner.id, "Alex")

    assert first.id != second.id


async def test_transfer_consolidates_splits_debts_and_membership(app_services) -> None:
    factory, users, guests, expenses, queries = app_services
    owner = await _register(users, 10, "Owner")
    target = await _register(users, 20, "Target")
    guest = await guests.create_manual_guest(owner.id, "Guest Target")
    command = CreateExpenseCommand(
        creator_person_id=owner.id,
        description="Dinner",
        total=Money(1000, "USD"),
        participant_ids=(owner.id, guest.id, target.id),
        split_method=SplitMethod.EXACT,
        context=DirectExpenseContext(),
        payer_person_id=guest.id,
        exact_amounts_minor={owner.id: 500, guest.id: 200, target.id: 300},
    )
    expense = await expenses.create(command)

    group_id = uuid4()
    async with factory() as session:
        session.add(GroupModel(id=group_id, name="Trip", creator_person_id=owner.id))
        session.add_all(
            [
                GroupMembershipModel(
                    group_id=group_id,
                    person_id=guest.id,
                    role=GroupRole.MEMBER,
                    status=MembershipStatus.ACTIVE,
                ),
                GroupMembershipModel(
                    group_id=group_id,
                    person_id=target.id,
                    role=GroupRole.ADMIN,
                    status=MembershipStatus.ACTIVE,
                ),
            ]
        )
        await session.commit()

    result = await guests.transfer_guest(
        TransferGuestCommand(owner.id, guest.id, target.id)
    )
    assert result.affected_counts["expenses"] == 1
    assert result.affected_counts["overlapping_splits"] == 1
    assert result.affected_counts["duplicate_memberships"] == 1

    transferred = await queries.get_details(target.id, expense.id)
    assert sum(split.owed_minor for split in transferred.splits) == 1000
    assert {split.person_id: split.owed_minor for split in transferred.splits} == {
        owner.id: 500,
        target.id: 500,
    }
    assert transferred.payer_person_id == target.id
    async with factory() as session:
        debts = (await session.execute(select(DebtModel))).scalars().all()
        assert len(debts) == 1
        assert debts[0].debtor_person_id == owner.id
        assert debts[0].creditor_person_id == target.id
        assert debts[0].amount_minor == 500
        memberships = (
            await session.execute(
                select(GroupMembershipModel).where(GroupMembershipModel.group_id == group_id)
            )
        ).scalars().all()
        assert len(memberships) == 1
        assert memberships[0].person_id == target.id
        assert memberships[0].role is GroupRole.ADMIN


async def test_only_owner_can_transfer_guest(app_services) -> None:
    _, users, guests, _, _ = app_services
    owner = await _register(users, 101, "Owner")
    attacker = await _register(users, 102, "Attacker")
    target = await _register(users, 103, "Target")
    guest = await guests.create_manual_guest(owner.id, "Guest")

    with pytest.raises(PermissionDeniedError):
        await guests.transfer_guest(TransferGuestCommand(attacker.id, guest.id, target.id))
