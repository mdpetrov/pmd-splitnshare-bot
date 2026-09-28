"""Cover durable inline message rendering and backward expense navigation."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import EditMessageText
from aiogram.types import CallbackQuery, Chat, InlineKeyboardMarkup, Message, Update, User

from splitnshare.domain.enums import Language
from splitnshare.presentation.flow_messages import (
    VIEW_KEY,
    FlowMessageMiddleware,
    FlowView,
    html_pages,
    show,
)
from splitnshare.presentation.keyboards import (
    add_friend_keyboard,
    cancel_keyboard,
    participant_keyboard,
    transfer_target_keyboard,
)
from splitnshare.presentation.routers.expenses import exact_back, review_back
from splitnshare.presentation.states import AddExpenseStates, FriendStates


def _state():
    return FSMContext(MemoryStorage(), StorageKey(bot_id=1, chat_id=7, user_id=7))


def _message(identifier=40):
    return Message(
        message_id=identifier, date=datetime.now(UTC), chat=Chat(id=7, type="private"),
        from_user=User(id=7, is_bot=False, first_name="Alice"), text="Dinner",
    )


def _bot():
    return SimpleNamespace(
        send_message=AsyncMock(return_value=_message(81)), edit_message_text=AsyncMock(),
    )


@pytest.mark.parametrize("factory", [
    add_friend_keyboard, cancel_keyboard, participant_keyboard, transfer_target_keyboard,
])
def test_form_keyboards_never_replace_bottom_menu(factory):
    assert isinstance(factory(Language.ENGLISH), InlineKeyboardMarkup)


async def test_typed_reply_edits_original_message_after_new_middleware_instance():
    state, bot = _state(), _bot()
    await state.set_state(FriendStates.manual_name)
    markup = cancel_keyboard(Language.ENGLISH)
    initial = FlowView(bot, state, 7, Language.ENGLISH, None, {})
    await initial.publish(["Name?"], markup)
    bot.send_message.reset_mock()

    async def handler(event, data):
        await show(event.message, "Added Alice", reply_markup=markup)

    await FlowMessageMiddleware()(
        handler, Update(update_id=1, message=_message()),
        {"state": state, "bot": bot, "language": Language.ENGLISH},
    )

    bot.send_message.assert_not_awaited()
    assert bot.edit_message_text.await_args.kwargs["message_id"] == 81
    assert (await state.get_data())[VIEW_KEY]["message_id"] == 81


async def test_callback_coalesces_status_and_prompt_into_one_edit():
    state, bot = _state(), _bot()
    callback = CallbackQuery(
        id="q", from_user=_message().from_user, chat_instance="c",
        message=_message(81), data="menu:add_expense",
    )

    async def handler(event, data):
        await state.clear()
        await show(event.callback_query.message, "Saved value")
        await show(event.callback_query.message, "Next step", reply_markup=cancel_keyboard())

    await FlowMessageMiddleware()(
        handler, Update(update_id=1, callback_query=callback),
        {"state": state, "bot": bot, "language": Language.ENGLISH},
    )

    bot.send_message.assert_not_awaited()
    bot.edit_message_text.assert_awaited_once()
    assert bot.edit_message_text.await_args.kwargs["text"] == "Saved value\n\nNext step"


async def test_missing_message_is_replaced_and_new_id_persisted():
    state, bot = _state(), _bot()
    bot.edit_message_text.side_effect = TelegramBadRequest(
        method=EditMessageText(text="Next"), message="Bad Request: message to edit not found",
    )
    view = FlowView(bot, state, 7, Language.ENGLISH, 80, {})
    await view.publish(["Next"], cancel_keyboard())
    bot.send_message.assert_awaited_once()
    assert (await state.get_data())[VIEW_KEY]["message_id"] == 81


async def test_repeated_identical_render_does_not_send_another_message():
    state, bot = _state(), _bot()
    bot.edit_message_text.side_effect = TelegramBadRequest(
        method=EditMessageText(text="Next"), message="Bad Request: message is not modified",
    )
    await FlowView(bot, state, 7, Language.ENGLISH, 80, {}).publish(["Next"], cancel_keyboard())
    bot.send_message.assert_not_awaited()
    assert (await state.get_data())[VIEW_KEY]["message_id"] == 80


async def test_obsolete_button_cannot_mutate_the_current_step(monkeypatch):
    state, bot = _state(), _bot()
    await FlowView(bot, state, 7, Language.ENGLISH, 81, {}).publish(["Name?"], cancel_keyboard())
    answer = AsyncMock()
    monkeypatch.setattr(CallbackQuery, "answer", answer)
    callback = CallbackQuery(
        id="q", from_user=_message().from_user, chat_instance="c", message=_message(81),
        data="guest:confirm",
    )
    handler = AsyncMock()
    await FlowMessageMiddleware()(
        handler, Update(update_id=2, callback_query=callback),
        {"state": state, "bot": bot, "language": Language.ENGLISH},
    )
    handler.assert_not_awaited()
    assert answer.call_args.kwargs["show_alert"] is True


def test_long_views_preserve_html_and_all_text():
    text = "Alice & Bob " * 1000
    pages = html_pages("<b>" + text.replace("&", "&amp;") + "</b>")
    assert len(pages) > 1
    assert all(len(page) <= 3400 for page in pages)
    assert all(page.startswith("<b>") and page.endswith("</b>") for page in pages)
    assert "".join(page[3:-4] for page in pages) == text.replace("&", "&amp;")


async def test_exact_back_discards_previous_share_and_later_values():
    state = _state()
    await state.set_state(AddExpenseStates.exact_amount)
    await state.update_data(
        participants=[{"id": p, "name": p} for p in ("a", "b", "c")],
        creator_id="a", exact_index=2, exact_amounts={"a": 100, "b": 200, "c": 300},
    )
    message = SimpleNamespace(answer=AsyncMock())
    await exact_back(message, state, Language.ENGLISH)
    data = await state.get_data()
    assert data["exact_index"] == 1
    assert data["exact_amounts"] == {"a": 100}
    assert await state.get_state() == AddExpenseStates.exact_amount.state


async def test_review_back_reopens_first_share_for_automatic_two_person_split(monkeypatch):
    state = _state()
    await state.set_state(AddExpenseStates.confirm)
    await state.update_data(
        participants=[{"id": p, "name": p} for p in ("a", "b")], creator_id="a",
        split_method="exact", exact_index=2, exact_amounts={"a": 100, "b": 200},
    )
    message = SimpleNamespace(answer=AsyncMock())
    monkeypatch.setattr("splitnshare.presentation.routers.expenses.callback_message", lambda _: message)
    await review_back(SimpleNamespace(answer=AsyncMock()), state, Language.ENGLISH)
    data = await state.get_data()
    assert data["exact_index"] == 0
    assert data["exact_amounts"] == {}
    assert await state.get_state() == AddExpenseStates.exact_amount.state
