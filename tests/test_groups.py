"""Cover group boundaries, settlements, shared history, and guest ownership transfer."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from splitnshare.application.dto import (
    CreateExpenseCommand,
    ExpenseActivityDTO,
    GroupActivityDTO,
    TelegramIdentity,
    TransferGuestCommand,
)
from splitnshare.application.groups import GroupService
from splitnshare.application.services import (
    ActivityQueryService,
    BalanceQueryService,
    ExpenseService,
    GuestService,
    UserService,
)
from splitnshare.domain.contexts import DirectExpenseContext, GroupExpenseContext
from splitnshare.domain.enums import GroupRole, Language, SplitMethod
from splitnshare.domain.errors import (
    ConflictError,
    PermissionDeniedError,
    UnsettledAccountError,
    ValidationError,
)
from splitnshare.domain.money import Money
from splitnshare.infrastructure.database import create_session_factory
from splitnshare.infrastructure.models import Base, GroupMembershipModel, GroupModel
from splitnshare.infrastructure.unit_of_work import SqlAlchemyUnitOfWorkFactory
from splitnshare.presentation.formatters import activity_text, expense_notification_text
from splitnshare.presentation.keyboards import person_activity_keyboard


@pytest.fixture
async def group_services():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = create_session_factory(engine)
    factory = SqlAlchemyUnitOfWorkFactory(sessions)
    yield SimpleNamespace(
        users=UserService(factory), guests=GuestService(factory), groups=GroupService(factory),
        expenses=ExpenseService(factory), activities=ActivityQueryService(factory),
        balances=BalanceQueryService(factory), sessions=sessions,
    )
    await engine.dispose()


async def register(services, telegram_id, name):
    return await services.users.register_or_update(TelegramIdentity(telegram_id, name))


async def expense(services, owner, participants, group_id=None, payer=None, currency="EUR", date=None):
    return await services.expenses.create(CreateExpenseCommand(
        creator_person_id=owner.id, description="Dinner", total=Money(1200, currency),
        participant_ids=tuple(p.id for p in participants), split_method=SplitMethod.EQUAL,
        payer_person_id=(payer or owner).id,
        context=GroupExpenseContext(group_id) if group_id else DirectExpenseContext(),
        occurred_at=date,
    ))


async def test_groups_require_supported_currency_and_two_distinct_people(group_services):
    s = group_services
    owner = await register(s, 801, "Owner")
    guest = await s.guests.create_manual_guest(owner.id, "Guest")
    with pytest.raises(ValidationError):
        await s.groups.create(owner.id, "Trip", "EUR", (owner.id, owner.id))
    with pytest.raises(ValidationError):
        await s.groups.create(owner.id, "Trip", "ABC", (guest.id,))
    group = await s.groups.create(owner.id, "  Summer   trip ", "eur", (guest.id, guest.id))
    assert group.name == "Summer trip"
    assert group.default_currency == "EUR"
    assert {m.id for m in group.participants} == {owner.id, guest.id}


async def test_group_access_invitation_ownership_and_guest_isolation(group_services):
    s = group_services
    owner = await register(s, 802, "Owner")
    member = await register(s, 803, "Member")
    outsider = await register(s, 804, "Outsider")
    guest = await s.guests.create_manual_guest(outsider.id, "Private guest")
    group = await s.groups.create(owner.id, "Trip", "USD", (member.id,))
    assert await s.groups.list_groups(outsider.id) == ()
    with pytest.raises(PermissionDeniedError):
        await s.groups.summary(outsider.id, group.id)
    with pytest.raises(PermissionDeniedError):
        await s.groups.add_members(member.id, group.id, (outsider.id,))
    with pytest.raises(PermissionDeniedError):
        await s.groups.add_members(owner.id, group.id, (guest.id,))
    _, added = await s.groups.add_members(owner.id, group.id, (outsider.id, member.id))
    assert added == (outsider.id,)
    _, added_again = await s.groups.add_members(owner.id, group.id, (outsider.id,))
    assert added_again == ()


async def test_group_expenses_allow_any_member_as_payer_but_no_outsiders(group_services):
    s = group_services
    owner = await register(s, 805, "Owner")
    other = await register(s, 806, "Other")
    payer = await register(s, 807, "Payer")
    outsider = await register(s, 808, "Outsider")
    group = await s.groups.create(owner.id, "Trip", "EUR", (other.id, payer.id))
    saved = await expense(s, owner, (owner, other), group.id, payer)
    assert payer.id not in {split.person_id for split in saved.splits}
    _, balances = await s.groups.summary(owner.id, group.id)
    assert sum(b.net_minor for b in balances[payer.id]) == 1200
    assert "12.00 EUR" in expense_notification_text(saved, payer.id)
    with pytest.raises(PermissionDeniedError):
        await expense(s, owner, (owner, outsider), group.id)
    with pytest.raises(PermissionDeniedError):
        await expense(s, owner, (owner, other), group.id, outsider)
    with pytest.raises(PermissionDeniedError):
        await expense(s, outsider, (owner, other), group.id, payer)


async def test_exact_group_split_with_nonparticipating_payer(group_services):
    s = group_services
    owner = await register(s, 820, "Owner")
    other = await register(s, 821, "Other")
    payer = await register(s, 822, "Payer")
    group = await s.groups.create(owner.id, "Trip", "EUR", (other.id, payer.id))
    result = await s.expenses.create(CreateExpenseCommand(
        creator_person_id=owner.id, description="Tickets", total=Money(900, "EUR"),
        participant_ids=(owner.id, other.id), payer_person_id=payer.id,
        split_method=SplitMethod.EXACT, context=GroupExpenseContext(group.id),
        exact_amounts_minor={owner.id: 400, other.id: 500},
    ))
    assert [share.owed_minor for share in result.splits] == [400, 500]


async def test_settle_all_only_closes_actors_balances_in_selected_group(group_services):
    s = group_services
    a = await register(s, 810, "A")
    b = await register(s, 811, "B")
    c = await register(s, 812, "C")
    group = await s.groups.create(a.id, "Trip", "EUR", (b.id, c.id))
    second = await s.groups.create(a.id, "Home", "EUR", (b.id,))
    await expense(s, a, (a, b), group.id)
    await expense(s, c, (a, c), group.id, currency="USD")
    await expense(s, b, (b, c), group.id)
    await expense(s, a, (a, b), second.id)
    await expense(s, a, (a, b))
    _, before = await s.groups.summary(a.id, group.id)
    saved = await s.groups.settle(a.id, group.id, before[a.id])
    assert len(saved) == 2
    _, after = await s.groups.summary(a.id, group.id)
    assert after[a.id] == ()
    assert [(x.other_person_id, x.net_minor) for x in after[b.id]] == [(c.id, 600)]
    assert await s.balances.get_balances(a.id, DirectExpenseContext())
    assert await s.balances.get_balances(a.id, GroupExpenseContext(second.id))
    with pytest.raises(ConflictError):
        await s.groups.settle(a.id, group.id, before[a.id])


async def test_changed_settlement_preview_is_rejected_without_partial_payments(group_services):
    s = group_services
    a = await register(s, 813, "A")
    b = await register(s, 814, "B")
    c = await register(s, 815, "C")
    group = await s.groups.create(a.id, "Trip", "EUR", (b.id, c.id))
    await expense(s, a, (a, b), group.id)
    await expense(s, a, (a, c), group.id)
    _, preview = await s.groups.summary(a.id, group.id)
    await expense(s, b, (a, b), group.id)
    with pytest.raises(ConflictError):
        await s.groups.settle(a.id, group.id, preview[a.id])
    _, current = await s.groups.summary(a.id, group.id)
    assert [(x.other_person_id, x.net_minor) for x in current[a.id]] == [(c.id, 600)]
    payments = await s.groups.settle(a.id, group.id, current[a.id], c.id)
    assert len(payments) == 1


async def test_shared_history_collapses_groups_across_pagination(group_services):
    s = group_services
    a = await register(s, 816, "A")
    b = await register(s, 817, "B")
    group = await s.groups.create(a.id, "Trip <2026>", "EUR", (b.id,))
    date = datetime(2026, 9, 1, tzinfo=UTC)
    for days in range(5):
        await expense(s, a, (a, b), group.id, date=date + timedelta(days=days))
    direct = await expense(s, a, (a, b), date=date + timedelta(days=2))
    first = await s.activities.list_for_person(a.id, b.id, limit=1)
    assert len(first.items) == 1
    assert isinstance(first.items[0], GroupActivityDTO)
    assert first.items[0].balances[0].net_minor == 3000
    assert first.next_cursor
    rendered = activity_text(first.items, a.id)
    assert "Trip &lt;2026&gt;" in rendered
    assert "Dinner" not in rendered
    keyboard = person_activity_keyboard(first, b.id, Language.ENGLISH, origin="friend")
    assert all(len(button.callback_data.encode()) <= 64 for row in keyboard.inline_keyboard
               for button in row if button.callback_data)
    second = await s.activities.list_for_person(a.id, b.id, cursor=first.next_cursor, limit=1)
    assert second.next_cursor is None
    assert isinstance(second.items[0], ExpenseActivityDTO)
    assert second.items[0].expense.id == direct.id


async def test_transfer_preserves_group_ownership_when_target_already_member(group_services):
    s = group_services
    inviter = await register(s, 818, "Inviter")
    target = await register(s, 819, "Target")
    guest = await s.guests.create_manual_guest(inviter.id, "Guest")
    group = await s.groups.create(inviter.id, "Trip", "EUR", (guest.id, target.id))
    async with s.sessions.begin() as session:
        model = await session.get(GroupModel, group.id)
        model.creator_person_id = guest.id
        source = await session.get(GroupMembershipModel, (group.id, guest.id))
        source.role = GroupRole.OWNER
        previous = await session.get(GroupMembershipModel, (group.id, inviter.id))
        previous.role = GroupRole.MEMBER
    await s.guests.transfer_guest(TransferGuestCommand(inviter.id, guest.id, target.id))
    transferred = await s.groups.get(target.id, group.id)
    assert transferred.owner_person_id == target.id
    assert {p.id for p in transferred.participants} == {inviter.id, target.id}
    async with s.sessions() as session:
        membership = await session.get(GroupMembershipModel, (group.id, target.id))
        assert membership.role == GroupRole.OWNER


async def test_opposite_group_and_direct_debts_do_not_allow_account_deletion(group_services):
    s = group_services
    a = await register(s, 823, "A")
    b = await register(s, 824, "B")
    group = await s.groups.create(a.id, "Trip", "EUR", (b.id,))
    await expense(s, a, (a, b), group.id)
    await expense(s, b, (a, b))
    assert await s.balances.get_balances(a.id) == ()
    with pytest.raises(UnsettledAccountError):
        await s.users.delete_account(a.id)
