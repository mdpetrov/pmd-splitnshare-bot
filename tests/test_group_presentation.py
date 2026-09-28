"""Cover both group expense entry paths and committed invitation notifications."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup

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
    assert all(
        not isinstance(call.kwargs.get("reply_markup"), ReplyKeyboardMarkup)
        for call in ui.message.answer.await_args_list
    )
    assert any(
        "Current date and time:" in call.args[0]
        for call in ui.message.answer.await_args_list
    )
    keyboard = await expenses.draft_participant_keyboard(ui.state, Language.ENGLISH)
    assert any(button.text == "Choose group members"
               for row in keyboard.inline_keyboard for button in row)
    assert not any(button.text == "Keep"
                   for row in keyboard.inline_keyboard for button in row)
    payers = expenses.draft_payer_keyboard(data, Language.ENGLISH)
    assert any(button.callback_data == f"expense:setpayer:{ui.guest.id}"
               for row in payers.inline_keyboard for button in row)


async def test_late_group_selection_preserves_reviewed_expense(group_ui):
    ui = group_ui
    await ui.state.update_data(
        draft_id=str(uuid4()), creator_id=str(ui.owner.id), description="Dinner",
        total_minor=1250, currency="USD", timezone="UTC",
        occurred_at=datetime.now(UTC).isoformat(),
        payer_id=str(ui.member.id), split_method="exact",
        exact_amounts={str(ui.owner.id): 500, str(ui.member.id): 750},
        participants=[groups._member(ui.owner), groups._member(ui.member)],
    )
    await ui.state.set_state(AddExpenseStates.confirm)
    ui.callback.data = f"eg:select:{uuid_token(ui.group.id)}"
    await expenses.select_expense_group(ui.callback, ui.state, ui.services, Language.ENGLISH)
    data = await ui.state.get_data()
    assert data["currency"] == "USD" and data["total_minor"] == 1250
    assert data["participants"] == [groups._member(ui.owner), groups._member(ui.member)]
    assert data["payer_id"] == str(ui.member.id)
    assert data["exact_amounts"] == {str(ui.owner.id): 500, str(ui.member.id): 750}
    assert await ui.state.get_state() == AddExpenseStates.confirm.state
    assert ui.message.answer.call_args.kwargs["reply_markup"].inline_keyboard
    assert isinstance(ui.message.answer.call_args.kwargs["reply_markup"], InlineKeyboardMarkup)


async def test_late_group_selection_rejects_non_members_without_changing_review(group_ui):
    ui = group_ui
    outsider = person("Outsider", 503)
    await ui.state.update_data(
        creator_id=str(ui.owner.id), payer_id=str(outsider.id),
        participants=[groups._member(ui.owner), groups._member(outsider)],
        total_minor=1250, exact_amounts={str(ui.owner.id): 500, str(outsider.id): 750},
    )
    await ui.state.set_state(AddExpenseStates.confirm)
    ui.callback.data = f"eg:select:{uuid_token(ui.group.id)}"
    await expenses.select_expense_group(ui.callback, ui.state, ui.services, Language.ENGLISH)
    data = await ui.state.get_data()
    assert data.get("group_id") is None
    assert data["payer_id"] == str(outsider.id)
    assert data["exact_amounts"] == {str(ui.owner.id): 500, str(outsider.id): 750}
    assert await ui.state.get_state() == AddExpenseStates.confirm.state


async def test_group_menu_uses_two_columns_and_icons():
    keyboard = groups._keyboard([
        ("Trip", "g:view:one"), ("Create group", "g:new"),
        ("Main menu", "menu:show"),
    ])
    assert [len(row) for row in keyboard.inline_keyboard] == [2, 1]
    assert [button.text.split(" ", 1)[0]
            for row in keyboard.inline_keyboard for button in row] == ["👥", "➕", "🏠"]


async def test_two_person_exact_split_fills_remaining_share(group_ui):
    ui = group_ui
    participants = [groups._member(ui.owner), groups._member(ui.member)]
    await ui.state.update_data(
        draft_id=str(uuid4()), creator_id=str(ui.owner.id),
        description="Dinner", total_minor=1250, currency="USD", timezone="UTC",
        occurred_at=datetime.now(UTC).isoformat(), payer_id=str(ui.owner.id),
        split_method="exact", exact_amounts={}, exact_index=0,
        participants=participants,
    )
    await ui.state.set_state(AddExpenseStates.exact_amount)
    ui.message.text = "5.00"
    await expenses.receive_exact_amount(ui.message, ui.state, Language.ENGLISH)
    data = await ui.state.get_data()
    assert data["exact_amounts"] == {str(ui.owner.id): 500, str(ui.member.id): 750}
    assert await ui.state.get_state() == AddExpenseStates.confirm.state
    assert "How much do you owe?" == expenses._exact_question(
        participants[0], str(ui.owner.id), Language.ENGLISH,
    )


async def test_expense_and_draft_prompts_never_replace_reply_keyboard(group_ui):
    ui = group_ui
    ui.message.text = "Dinner"
    await expenses.begin_expense(ui.message, ui.state, ui.services, Language.ENGLISH)
    await expenses.receive_description(ui.message, ui.state, Language.ENGLISH)
    ui.message.text = "12.50"
    await expenses.receive_total(ui.message, ui.state, ui.services, Language.ENGLISH)
    data = await ui.state.get_data()
    await ui.state.update_data(
        edit_mode=True,
        occurred_at=datetime.now(UTC).isoformat(),
        payer_id=str(ui.owner.id),
        split_method="equal",
        exact_amounts={}, exact_index=0,
        participants=[groups._member(ui.owner), groups._member(ui.member)],
    )
    for step in (
        AddExpenseStates.description, AddExpenseStates.total,
        AddExpenseStates.expense_date, AddExpenseStates.custom_date,
        AddExpenseStates.participants, AddExpenseStates.manual_name,
        AddExpenseStates.payer, AddExpenseStates.split_method,
        AddExpenseStates.exact_amount,
        AddExpenseStates.confirm,
    ):
        await ui.state.set_state(step)
        await expenses.render_expense_draft(ui.message, ui.state, Language.ENGLISH)
    assert data["currency"] == "USD"
    assert all(
        not isinstance(call.kwargs.get("reply_markup"), ReplyKeyboardMarkup)
        for call in ui.message.answer.await_args_list
    )


async def test_cancelling_expense_does_not_replace_reply_keyboard(group_ui):
    ui = group_ui
    await ui.state.set_state(AddExpenseStates.description)
    ui.callback.data = "expense:cancel"
    await expenses.cancel_expense_callback(ui.callback, ui.state, Language.ENGLISH)
    assert await ui.state.get_state() is None
    assert ui.message.answer.call_args.kwargs.get("reply_markup") is None


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
