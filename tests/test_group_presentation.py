"""Cover both group expense entry paths and committed invitation notifications."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from splitnshare.application.dto import GroupDTO, PersonDTO
from splitnshare.domain.enums import Language, PersonKind
from splitnshare.presentation.callbacks import uuid_token
from splitnshare.presentation.routers import expenses, groups
from splitnshare.presentation.states import AddExpenseStates, GroupStates


def person(name, telegram_id=None):
    return PersonDTO(
        id=uuid4(), display_name=name,
        kind=PersonKind.USER if telegram_id else PersonKind.GUEST,
        registered=telegram_id is not None, telegram_user_id=telegram_id,
    )


@pytest.fixture
def group_ui(monkeypatch):
    owner = person("Owner", 501)
    member = person("Member", 502)
    guest = person("Guest")
    group = GroupDTO(uuid4(), "Trip <2026>", "JPY", owner.id, (owner, member, guest))
    services = SimpleNamespace(
        users=SimpleNamespace(
            find_registered_target=AsyncMock(return_value=owner),
            list_registered=AsyncMock(return_value=(member,)),
        ),
        user_settings=SimpleNamespace(
            get_or_create=AsyncMock(return_value=SimpleNamespace(
                default_currency="USD", language=Language.ENGLISH, timezone="UTC",
            )),
        ),
        groups=SimpleNamespace(
            get=AsyncMock(return_value=group), create=AsyncMock(return_value=group),
        ),
    )
    state = FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=501, user_id=501))
    message = SimpleNamespace(
        answer=AsyncMock(),
        edit_text=AsyncMock(),
        from_user=SimpleNamespace(id=501),
    )
    callback = SimpleNamespace(
        from_user=SimpleNamespace(id=501), answer=AsyncMock(),
        data=f"g:expense:{uuid_token(group.id)}",
    )
    monkeypatch.setattr(groups, "callback_message", lambda _: message)
    monkeypatch.setattr(expenses, "callback_message", lambda _: message)
    return SimpleNamespace(
        owner=owner, member=member, guest=guest, group=group,
        services=services, state=state, message=message, callback=callback,
    )


async def test_starting_inside_group_uses_group_currency_and_member_only_keyboard(group_ui):
    ui = group_ui
    await groups.group_expense(ui.callback, ui.state, ui.services, Language.ENGLISH)
    data = await ui.state.get_data()
    assert data["group_id"] == str(ui.group.id)
    assert data["group_currency"] == "JPY"
    assert await ui.state.get_state() == AddExpenseStates.description.state
    ui.message.text = "125"
    await expenses.receive_total(ui.message, ui.state, ui.services, Language.ENGLISH)
    data = await ui.state.get_data()
    assert (data["total_minor"], data["currency"]) == (125, "JPY")
    keyboard = await expenses.draft_participant_keyboard(ui.state, Language.ENGLISH)
    assert not any(button.request_users for row in keyboard.keyboard for button in row)
    assert any(button.text == "Choose group members" for row in keyboard.keyboard for button in row)
    payers = expenses.draft_payer_keyboard(data, Language.ENGLISH)
    assert any(button.callback_data == f"expense:setpayer:{ui.guest.id}"
               for row in payers.inline_keyboard for button in row)


async def test_late_group_selection_preserves_money_and_removes_outsiders(group_ui):
    ui = group_ui
    outsider = person("Outsider", 503)
    await ui.state.update_data(
        draft_id=str(uuid4()), creator_id=str(ui.owner.id), description="Dinner",
        total_minor=1250, currency="USD", payer_id=str(outsider.id), split_method="exact",
        exact_amounts={str(ui.owner.id): 500, str(outsider.id): 750},
        participants=[groups._member(ui.owner), groups._member(outsider)],
    )
    await ui.state.set_state(AddExpenseStates.confirm)
    ui.callback.data = f"eg:select:{uuid_token(ui.group.id)}"
    await expenses.select_expense_group(ui.callback, ui.state, ui.services, Language.ENGLISH)
    data = await ui.state.get_data()
    assert data["currency"] == "USD" and data["total_minor"] == 1250
    assert data["participants"] == [groups._member(ui.owner)]
    assert data["payer_id"] is None and data["exact_amounts"] == {}
    assert await ui.state.get_state() == AddExpenseStates.participants.state


async def test_creation_notifies_registered_invitees_once_after_commit(group_ui):
    ui = group_ui
    await ui.state.update_data(
        token="review", name=ui.group.name, currency="JPY", actor_id=str(ui.owner.id),
        members=[groups._member(m) for m in ui.group.participants],
    )
    await ui.state.set_state(GroupStates.confirm)
    ui.callback.data = "g:save:review"
    bot = SimpleNamespace(send_message=AsyncMock())
    await groups.group_save(ui.callback, ui.state, ui.services, bot, Language.ENGLISH)
    ui.services.groups.create.assert_awaited_once()
    bot.send_message.assert_awaited_once()
    assert bot.send_message.call_args.args[0] == ui.member.telegram_user_id
    assert "Trip &lt;2026&gt;" in bot.send_message.call_args.args[1]
    await groups.group_save(ui.callback, ui.state, ui.services, bot, Language.ENGLISH)
    bot.send_message.assert_awaited_once()
    ui.services.groups.create.assert_awaited_once()
