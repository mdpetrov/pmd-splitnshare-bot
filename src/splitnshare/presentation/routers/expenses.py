"""Handle expense creation, transaction history, details, and deletion flows."""

from __future__ import annotations


from datetime import UTC, datetime, timedelta
from html import escape
from typing import Any
from uuid import UUID, uuid4

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from splitnshare.application.dto import (
    CreateExpenseCommand,
    ExpenseDTO,
    SharedTelegramUser,
)
from splitnshare.domain.contexts import DirectExpenseContext, GroupExpenseContext
from splitnshare.domain.enums import Language, SplitMethod
from splitnshare.domain.errors import DomainError, ValidationError
from splitnshare.domain.money import Money
from splitnshare.domain.splitting import EqualSplitStrategy
from splitnshare.presentation.callbacks import uuid_from_token, uuid_token
from splitnshare.presentation.container import Services
from splitnshare.presentation.datetimes import format_local_datetime, parse_local_datetime
from splitnshare.presentation.flow_messages import show, show_markup
from splitnshare.presentation.formatters import (
    activity_text,
    expense_notification_text,
    expense_text,
)
from splitnshare.presentation.helpers import (
    callback_message,
    callback_payload,
    current_person,
    parse_share_minor,
    parse_total,
)
from splitnshare.presentation.i18n import button_values, translate
from splitnshare.presentation.keyboards import (
    activity_list_keyboard,
    back_to_main_menu_keyboard,
    delete_confirm_keyboard,
    expense_confirm_keyboard,
    expense_date_keyboard,
    expense_details_keyboard,
    expense_friends_keyboard,
    expense_payer_keyboard,
    remove_participant_keyboard,
    split_method_keyboard,
)
from splitnshare.presentation.labels import friend_label, participant_label
from splitnshare.presentation.routers.groups import _keyboard, _member
from splitnshare.presentation.states import AddExpenseStates

router = Router(name="expenses")
router.message.filter(F.chat.type == "private")
router.callback_query.filter(F.message.chat.type == "private")


def _expense_navigation(
    language: Language, *, back: str | None = None, keep: bool = False,
) -> InlineKeyboardMarkup:
    """Offer flow navigation without replacing the user's persistent main keyboard."""
    row = []
    if back is not None:
        row.append(InlineKeyboardButton(text=translate(language, "back"), callback_data=back))
    if keep:
        row.append(InlineKeyboardButton(text=translate(language, "keep"), callback_data="expense:keep"))
    row.append(InlineKeyboardButton(text=translate(language, "cancel"), callback_data="expense:cancel"))
    return InlineKeyboardMarkup(inline_keyboard=[row])


async def draft_participant_keyboard(state: FSMContext, language: Language) -> InlineKeyboardMarkup:
    """Build inline participant actions without a redundant Keep button."""
    data = await state.get_data()
    rows = []
    if data.get("group_id"):
        rows.append([InlineKeyboardButton(
            text=translate(language, "group_expense_members"), callback_data="expense:participants:friends",
        )])
    else:
        rows.append([
            InlineKeyboardButton(text=translate(language, "add_manual"), callback_data="expense:participants:manual"),
            InlineKeyboardButton(text=translate(language, "add_from_friends"), callback_data="expense:participants:friends"),
        ])
    if not data.get("group_id"):
        rows.append([InlineKeyboardButton(
            text=translate(language, "choose_telegram_users"),
            callback_data="expense:participants:contact",
        )])
    rows.append([
        InlineKeyboardButton(text=translate(language, "remove_participant"), callback_data="expense:participants:remove"),
        InlineKeyboardButton(text=translate(language, "done"), callback_data="expense:participants:done"),
    ])
    rows.append([
        InlineKeyboardButton(text=translate(language, "back"), callback_data="expense:participants:back"),
        InlineKeyboardButton(text=translate(language, "cancel"), callback_data="expense:cancel"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data.startswith("expense:nav:"))
async def navigate_expense(
    callback: CallbackQuery, state: FSMContext, language: Language,
) -> None:
    """Move backward through text-entry steps using inline controls."""
    destinations = {
        "description": (AddExpenseStates.total, AddExpenseStates.description),
        "date": (AddExpenseStates.custom_date, AddExpenseStates.expense_date),
        "participants": (AddExpenseStates.manual_name, AddExpenseStates.participants),
        "split": (AddExpenseStates.exact_amount, AddExpenseStates.split_method),
    }
    key = (callback.data or "").rsplit(":", 1)[1]
    if key == "split" and await state.get_state() == AddExpenseStates.exact_amount.state:
        await exact_back(callback_message(callback), state, language)
        await callback.answer()
        return
    if key not in destinations or await state.get_state() != destinations[key][0].state:
        await callback.answer(translate(language, "draft_expired"), show_alert=True)
        return
    await state.set_state(destinations[key][1])
    await render_expense_draft(callback_message(callback), state, language)
    await callback.answer()


@router.callback_query(AddExpenseStates.participants, F.data.startswith("expense:participants:"))
async def participant_action(
    callback: CallbackQuery, state: FSMContext, services: Services, language: Language,
) -> None:
    """Dispatch participant actions from the draft's inline keyboard."""
    action = (callback.data or "").rsplit(":", 1)[1]
    message = callback_message(callback)
    data = await state.get_data()
    if action == "manual":
        if data.get("group_id"):
            await callback.answer(translate(language, "group_member_only"), show_alert=True)
            return
        await state.set_state(AddExpenseStates.manual_name)
        await render_expense_draft(message, state, language)
    elif action == "friends":
        if data.get("group_id"):
            await _group_member_choices(message, state, services, language, 0)
        else:
            owner = await services.users.find_registered_target(callback.from_user.id)
            if owner is None:
                await callback.answer(translate(language, "use_start"), show_alert=True)
                return
            friends = list(await services.friends.list_friends(owner.id))
            if friends:
                await show(message,
                    translate(language, "choose_friend"),
                    reply_markup=expense_friends_keyboard(friends, language),
                )
            else:
                await show(message, translate(language, "no_friends"))
    elif action == "remove":
        await choose_participant_to_remove(message, state, language)
    elif action == "home":
        await render_expense_draft(message, state, language)
    elif action == "contact":
        await show(message, translate(language, "share_contact_hint"),
                   reply_markup=_expense_navigation(language, back="expense:participants:home"))
    elif action == "done":
        await participants_done(message, state, services, language)
    elif action == "back":
        await state.set_state(AddExpenseStates.expense_date)
        await render_expense_draft(message, state, language)
    else:
        await callback.answer(translate(language, "draft_expired"), show_alert=True)
        return
    await callback.answer()


def _expense_date_prompt(data: dict[str, Any], language: Language) -> str:
    """Show the current time in the selected timezone beside the date question."""
    current = format_local_datetime(datetime.now(UTC), data.get("timezone", "UTC"), language)
    return translate(language, "choose_expense_date") + "\n" + translate(
        language, "current_expense_datetime", date=escape(current)
    )


def _exact_question(participant: dict[str, str], creator_id: str, language: Language) -> str:
    """Address the creator directly while identifying every other participant."""
    if participant["id"] == creator_id:
        return translate(language, "owes_you")
    return translate(language, "owes_next", name=escape(participant["name"]))


def draft_payer_keyboard(
    data: dict[str, Any],
    language: Language,
    page: int = 0,
) -> InlineKeyboardMarkup:
    """Page every group member as a possible payer, including non-beneficiaries."""
    members = data.get("group_members") or data.get("participants", [])
    markup = expense_payer_keyboard(
        members[page * 20:(page + 1) * 20], data["creator_id"], language,
        include_keep=bool(data.get("edit_mode") and data.get("payer_id")),
    )
    if len(members) > (page + 1) * 20:
        markup.inline_keyboard.insert(-1, [InlineKeyboardButton(
            text=translate(language, "more"), callback_data=f"eg:payers:{page + 1}",
        )])
    if page:
        markup.inline_keyboard.insert(-1, [InlineKeyboardButton(
            text="←", callback_data=f"eg:payers:{page - 1}",
        )])
    return markup


@router.callback_query(AddExpenseStates.payer, F.data.startswith("eg:payers:"))
async def payer_page(callback: CallbackQuery, state: FSMContext, language: Language) -> None:
    """Display the next page of eligible group payers."""
    page = max(0, int((callback.data or "").rsplit(":", 1)[1]))
    await show_markup(callback_message(callback),
        reply_markup=draft_payer_keyboard(await state.get_data(), language, page)
    )
    await callback.answer()


async def _group_member_choices(
    message: Message,
    state: FSMContext,
    services: Services,
    language: Language,
    page: int,
) -> None:
    """Refresh group membership before displaying a bounded participant picker."""
    data = await state.get_data()
    group = await services.groups.get(UUID(data["creator_id"]), UUID(data["group_id"]))
    members = [_member(m) for m in group.participants]
    await state.update_data(group_members=members, group_name=group.name)
    choices = [
        (m["name"], f"eg:member:{uuid_token(UUID(m['id']))}")
        for m in members[page * 20:(page + 1) * 20]
    ]
    if len(members) > (page + 1) * 20:
        choices.append((translate(language, "more"), f"eg:members:{page + 1}"))
    if page:
        choices.append(("←", f"eg:members:{page - 1}"))
    choices.append((translate(language, "back"), "expense:participants:home"))
    await show(message,
        translate(language, "group_expense_members"), reply_markup=_keyboard(choices)
    )


@router.callback_query(AddExpenseStates.participants, F.data.startswith("eg:members:"))
async def group_member_page(
    callback: CallbackQuery,
    state: FSMContext,
    services: Services,
    language: Language,
) -> None:
    """Page the current group's participant picker."""
    page = max(0, int((callback.data or "").rsplit(":", 1)[1]))
    await _group_member_choices(callback_message(callback), state, services, language, page)
    await callback.answer()


@router.callback_query(AddExpenseStates.participants, F.data.startswith("eg:member:"))
async def add_group_member(
    callback: CallbackQuery,
    state: FSMContext,
    services: Services,
    language: Language,
) -> None:
    """Add a currently active group member to the expense allocation."""
    data = await state.get_data()
    group = await services.groups.get(UUID(data["creator_id"]), UUID(data["group_id"]))
    person_id = uuid_from_token((callback.data or "").rsplit(":", 1)[1])
    member = next((m for m in group.participants if m.id == person_id), None)
    if member is None:
        raise ValidationError("This participant is no longer in the group.")
    participants = data["participants"]
    if str(person_id) not in {p["id"] for p in participants}:
        if len(participants) >= 10:
            raise ValidationError(translate(language, "participant_limit"))
        participants.append(_member(member))
    await state.update_data(
        participants=participants, group_members=[_member(m) for m in group.participants],
        exact_amounts={}, exact_index=0,
    )
    await show(callback_message(callback),
        _participant_summary(participants, language),
        reply_markup=await draft_participant_keyboard(state, language),
    )
    await callback.answer()


@router.callback_query(AddExpenseStates.confirm, F.data.startswith("eg:list:"))
async def expense_group_choices(
    callback: CallbackQuery,
    state: FSMContext,
    services: Services,
    language: Language,
) -> None:
    """Offer attaching the reviewed expense to any of the creator's groups."""
    data = await state.get_data()
    groups = await services.groups.list_groups(UUID(data["creator_id"]))
    page = max(0, int((callback.data or "").rsplit(":", 1)[1]))
    choices = [(g.name, f"eg:select:{uuid_token(g.id)}") for g in groups[page * 20:(page + 1) * 20]]
    if len(groups) > (page + 1) * 20:
        choices.append((translate(language, "more"), f"eg:list:{page + 1}"))
    choices.append((translate(language, "group_none"), "eg:select:none"))
    if page:
        choices.append(("←", f"eg:list:{page - 1}"))
    choices.append((translate(language, "back"), "eg:review"))
    await show(callback_message(callback),
        translate(language, "group_choose"), reply_markup=_keyboard(choices)
    )
    await callback.answer()


@router.callback_query(AddExpenseStates.confirm, F.data.startswith("eg:select:"))
async def select_expense_group(
    callback: CallbackQuery,
    state: FSMContext,
    services: Services,
    language: Language,
) -> None:
    """Attach a group without discarding the reviewed payer and allocations."""
    data = await state.get_data()
    token = (callback.data or "").rsplit(":", 1)[1]
    if token == "none":
        if data["payer_id"] not in {p["id"] for p in data["participants"]}:
            await callback.answer(translate(language, "person_unavailable"), show_alert=True)
            return
        await state.update_data(
            group_id=None, group_name=None, group_currency=None, group_members=None
        )
        name = translate(language, "group_none")
    else:
        group = await services.groups.get(UUID(data["creator_id"]), uuid_from_token(token))
        allowed = {str(m.id) for m in group.participants}
        required = {p["id"] for p in data["participants"]} | {
            data["creator_id"], data["payer_id"],
        }
        if not required <= allowed:
            await callback.answer(
                translate(language, "group_expense_members_required"), show_alert=True
            )
            return
        await state.update_data(
            group_id=str(group.id), group_name=group.name, group_currency=group.default_currency,
            group_members=[_member(m) for m in group.participants],
        )
        name = group.name
    await show(callback_message(callback),
        translate(language, "group_selected", name=escape(name))
    )
    await render_expense_draft(callback_message(callback), state, language)
    await callback.answer()


@router.callback_query(AddExpenseStates.confirm, F.data == "eg:edit")
async def edit_expense_members(
    callback: CallbackQuery,
    state: FSMContext,
    language: Language,
) -> None:
    """Reopen the full expense editor from its first field."""
    await state.update_data(edit_mode=True, edit_origin="review")
    await state.set_state(AddExpenseStates.description)
    await render_expense_draft(callback_message(callback), state, language)
    await callback.answer()


@router.callback_query(F.data == "expense:keep")
async def keep_inline_expense_value(
    callback: CallbackQuery, state: FSMContext, language: Language
) -> None:
    """Retain a saved draft field using inline navigation."""
    data = await state.get_data()
    step = await state.get_state()
    if not data.get("edit_mode"):
        await callback.answer(translate(language, "draft_expired"), show_alert=True)
        return
    target_message = callback_message(callback)
    if step == AddExpenseStates.description.state and data.get("description"):
        await state.set_state(AddExpenseStates.total)
        await render_expense_draft(target_message, state, language)
    elif step == AddExpenseStates.total.state and "total_minor" in data:
        await state.set_state(AddExpenseStates.expense_date)
        await render_expense_draft(target_message, state, language)
    elif step == AddExpenseStates.custom_date.state and data.get("occurred_at"):
        await state.set_state(AddExpenseStates.participants)
        await render_expense_draft(target_message, state, language)
    elif step == AddExpenseStates.exact_amount.state:
        participants = data.get("participants", [])
        index = int(data.get("exact_index", 0))
        exact = data.get("exact_amounts", {})
        if index >= len(participants) or participants[index]["id"] not in exact:
            await callback.answer(translate(language, "draft_expired"), show_alert=True)
            return
        index += 1
        await state.update_data(exact_index=index)
        if index == len(participants) and _exact_complete(data):
            await state.set_state(AddExpenseStates.confirm)
        await render_expense_draft(target_message, state, language)
    elif step == AddExpenseStates.expense_date.state and data.get("occurred_at"):
        await state.set_state(AddExpenseStates.participants)
        await show(target_message,
            translate(
                language, "date_selected",
                date=escape(format_local_datetime(
                    datetime.fromisoformat(data["occurred_at"]),
                    data.get("timezone", "UTC"), language,
                )),
            )
        )
        await show(target_message,
            _participant_summary(data.get("participants", []), language),
            reply_markup=await draft_participant_keyboard(state, language),
        )
    elif step == AddExpenseStates.payer.state and data.get("payer_id"):
        await state.set_state(AddExpenseStates.split_method)
        await show(target_message,
            translate(language, "split_how"),
            reply_markup=split_method_keyboard(
                language, include_keep=bool(data.get("split_method"))
            ),
        )
    elif step == AddExpenseStates.split_method.state and data.get("split_method"):
        await show(target_message,
            translate(
                language, "split_choice_saved",
                method=translate(
                    language,
                    "split_equally" if data["split_method"] == SplitMethod.EQUAL.value
                    else "exact_amounts",
                ),
            )
        )
        if data["split_method"] == SplitMethod.EXACT.value and not _exact_complete(data):
            await state.update_data(exact_index=0)
            await state.set_state(AddExpenseStates.exact_amount)
            await render_expense_draft(target_message, state, language)
        else:
            await state.set_state(AddExpenseStates.confirm)
            await render_expense_draft(target_message, state, language)
    else:
        await callback.answer(translate(language, "draft_expired"), show_alert=True)
        return
    await callback.answer()


@router.message(AddExpenseStates.description, F.text.in_(button_values("keep")))
@router.message(AddExpenseStates.total, F.text.in_(button_values("keep")))
@router.message(AddExpenseStates.custom_date, F.text.in_(button_values("keep")))
@router.message(AddExpenseStates.participants, F.text.in_(button_values("keep")))
@router.message(AddExpenseStates.exact_amount, F.text.in_(button_values("keep")))
async def keep_text_expense_value(
    message: Message, state: FSMContext, services: Services, language: Language
) -> None:
    """Advance the editor without replacing an already saved field."""
    data = await state.get_data()
    step = await state.get_state()
    if not data.get("edit_mode"):
        await show(message, translate(language, "draft_expired"))
        return
    if step == AddExpenseStates.description.state and data.get("description"):
        await state.set_state(AddExpenseStates.total)
        await render_expense_draft(message, state, language)
    elif step == AddExpenseStates.total.state and "total_minor" in data:
        await state.set_state(AddExpenseStates.expense_date)
        await show(message,
            translate(
                language, "total",
                total=Money(data["total_minor"], data["currency"]).format(),
            ),
        )
        await render_expense_draft(message, state, language)
    elif step == AddExpenseStates.custom_date.state and data.get("occurred_at"):
        await state.set_state(AddExpenseStates.participants)
        await render_expense_draft(message, state, language)
    elif step == AddExpenseStates.participants.state and len(data.get("participants", [])) >= 2:
        await participants_done(message, state, services, language)
    elif step == AddExpenseStates.exact_amount.state:
        participants = data.get("participants", [])
        index = int(data.get("exact_index", 0))
        exact = data.get("exact_amounts", {})
        if index < len(participants) and participants[index]["id"] in exact:
            index += 1
            await state.update_data(exact_index=index)
            if index == len(participants) and _exact_complete(data):
                await state.set_state(AddExpenseStates.confirm)
                await render_expense_draft(message, state, language)
            else:
                await render_expense_draft(message, state, language)
        else:
            await show(message, translate(language, "draft_expired"))
    else:
        await show(message, translate(language, "draft_expired"))


def _exact_complete(data: dict[str, Any]) -> bool:
    """Check that every saved exact share still matches the current participants."""
    participants = data.get("participants", [])
    amounts = data.get("exact_amounts") or {}
    return (
        2 <= len(participants) <= 10
        and set(amounts) == {person["id"] for person in participants}
        and all(
            amounts[person["id"]] >= (0 if person["id"] == data.get("payer_id") else 1)
            for person in participants
        )
        and sum(amounts[person["id"]] for person in participants)
        == data.get("total_minor")
    )


async def render_expense_draft(message: Message, state: FSMContext, language: Language) -> None:
    """Recreate the current expense prompt from persisted values without resetting them."""
    step = await state.get_state()
    data = await state.get_data()
    participants = data.get("participants", [])
    editing = bool(data.get("edit_mode"))
    markup = _expense_navigation(language, back="expense:nav:participants")
    if step == AddExpenseStates.exact_amount.state:
        index = int(data.get("exact_index", 0))
        if index >= len(participants):
            if _exact_complete(data):
                await state.set_state(AddExpenseStates.confirm)
                step = AddExpenseStates.confirm.state
            else:
                await state.update_data(exact_amounts={}, exact_index=0)
                data["exact_index"] = 0
                data["exact_amounts"] = {}
    if step == AddExpenseStates.description.state:
        text = translate(language, "expense_for")
        if data.get("description"):
            text += "\n\n" + translate(
                language, "draft_current_description", value=escape(data["description"])
            )
        markup = _expense_navigation(
            language, back="expense:origin", keep=editing and bool(data.get("description")),
        )
    elif step == AddExpenseStates.total.state:
        text = translate(language, "enter_total")
        if "total_minor" in data:
            text += "\n\n" + Money(data["total_minor"], data["currency"]).format()
        markup = _expense_navigation(
            language, back="expense:nav:description",
            keep=editing and "total_minor" in data,
        )
    elif step == AddExpenseStates.expense_date.state:
        text, markup = _expense_date_prompt(data, language), expense_date_keyboard(
            language, include_keep=editing and bool(data.get("occurred_at"))
        )
    elif step == AddExpenseStates.custom_date.state:
        text = translate(language, "enter_custom_date")
        markup = _expense_navigation(
            language, back="expense:nav:date",
            keep=editing and bool(data.get("occurred_at")),
        )
    elif step == AddExpenseStates.participants.state:
        text = _participant_summary(participants, language)
        markup = await draft_participant_keyboard(state, language)
    elif step == AddExpenseStates.manual_name.state:
        text = translate(language, "guest_name")
        markup = _expense_navigation(language, back="expense:nav:participants")
    elif step == AddExpenseStates.payer.state:
        text = translate(language, "choose_payer")
        markup = draft_payer_keyboard(data, language)
    elif step == AddExpenseStates.split_method.state:
        text, markup = translate(language, "split_how"), split_method_keyboard(
            language, include_keep=editing and bool(data.get("split_method"))
        )
    elif step == AddExpenseStates.exact_amount.state:
        index = int(data.get("exact_index", 0))
        if not participants:
            raise ValidationError("Draft participants are missing. Edit the draft to continue.")
        text = _exact_question(participants[index], data["creator_id"], language)
        markup = _expense_navigation(
            language, back="expense:nav:split",
            keep=editing and participants[index]["id"] in data.get("exact_amounts", {}),
        )
    elif step == AddExpenseStates.confirm.state:
        if data["split_method"] == SplitMethod.EQUAL.value:
            allocations = EqualSplitStrategy().allocate(
                data["total_minor"], [UUID(item["id"]) for item in participants]
            )
            amounts = {str(item.person_id): item.owed_minor for item in allocations}
        else:
            amounts = data["exact_amounts"]
        text = _review_text(data, participants, amounts, language)
        markup = expense_confirm_keyboard(language, data["draft_id"])
    else:
        raise ValidationError("This draft step is unavailable. Edit the draft to continue.")
    await show(message, text, reply_markup=markup)


@router.message(F.text.in_(button_values("add_expense")))
async def begin_expense(
    message: Message, state: FSMContext, services: Services, language: Language
) -> None:
    """Start expense creation and seed the creator as a participant."""
    person = await current_person(message, services)
    await state.clear()
    await state.update_data(
        draft_id=str(uuid4()),
        creator_id=str(person.id),
        participants=[
            {
                "id": str(person.id),
                "name": participant_label(person.display_name, person.id, person.username),
            }
        ],
    )
    await state.set_state(AddExpenseStates.description)
    await render_expense_draft(message, state, language)


@router.callback_query(F.data == "menu:add_expense")
async def begin_expense_callback(
    callback: CallbackQuery,
    state: FSMContext,
    services: Services,
    language: Language,
) -> None:
    """Start expense creation from the inline main menu."""
    if callback.from_user is None:
        return
    target_message = callback_message(callback)
    person = await services.users.find_registered_target(callback.from_user.id)
    if person is None:
        await callback.answer(translate(language, "use_start"), show_alert=True)
        return
    await state.clear()
    await state.update_data(
        draft_id=str(uuid4()),
        creator_id=str(person.id),
        participants=[
            {
                "id": str(person.id),
                "name": participant_label(
                    person.display_name, person.id, person.username
                ),
            }
        ],
    )
    await state.set_state(AddExpenseStates.description)
    await render_expense_draft(target_message, state, language)
    await callback.answer()


@router.message(AddExpenseStates.description, F.text.in_(button_values("back")))
async def description_back(
    message: Message, state: FSMContext, language: Language
) -> None:
    """Leave description entry and return to the main menu."""
    await state.clear()
    await show(message, translate(language, "back_main"))


@router.message(AddExpenseStates.description)
async def receive_description(
    message: Message, state: FSMContext, language: Language
) -> None:
    """Validate the expense description and request its total."""
    text = (message.text or "").strip()
    if not 1 <= len(text) <= 240:
        await show(message, translate(language, "description_invalid"))
        return
    await state.update_data(description=text)
    await state.set_state(AddExpenseStates.total)
    await render_expense_draft(message, state, language)


@router.message(AddExpenseStates.total, F.text.in_(button_values("back")))
async def total_back(message: Message, state: FSMContext, language: Language) -> None:
    """Return from total entry to the description step."""
    await state.set_state(AddExpenseStates.description)
    await render_expense_draft(message, state, language)


@router.message(AddExpenseStates.total)
async def receive_total(
    message: Message, state: FSMContext, services: Services, language: Language
) -> None:
    """Parse the expense total and request its transaction time."""
    person = await current_person(message, services)
    settings = await services.user_settings.get_or_create(person.id)
    try:
        data = await state.get_data()
        total = parse_total(
            message.text or "", data.get("group_currency") or settings.default_currency
        )
    except DomainError as exc:
        await show(message, str(exc))
        return
    timezone = settings.timezone or "UTC"
    changes: dict[str, Any] = dict(
        total_minor=total.minor,
        currency=total.currency,
        timezone=timezone,
    )
    if (data.get("total_minor"), data.get("currency")) != (
        total.minor, total.currency
    ):
        changes.update(exact_amounts={}, exact_index=0)
    await state.update_data(**changes)
    await state.set_state(AddExpenseStates.expense_date)
    await show(message, translate(language, "total", total=total.format()))
    await show(message,
        _expense_date_prompt({**data, "timezone": timezone}, language),
        reply_markup=expense_date_keyboard(
            language, include_keep=bool(data.get("edit_mode") and data.get("occurred_at"))
        ),
    )


@router.callback_query(
    F.data.in_(
        {
            "expense:date:now",
            "expense:date:minus_30m",
            "expense:date:minus_1h",
            "expense:date:minus_2h",
            "expense:date:minus_3h",
        }
    )
)
async def choose_expense_date(
    callback: CallbackQuery, state: FSMContext, language: Language
) -> None:
    """Apply a relative time preset and continue to participants."""
    if await state.get_state() != AddExpenseStates.expense_date.state:
        await callback.answer(translate(language, "draft_expired"), show_alert=True)
        return
    payload, target_message = callback_payload(callback)
    offsets = {
        "now": timedelta(),
        "minus_30m": timedelta(minutes=30),
        "minus_1h": timedelta(hours=1),
        "minus_2h": timedelta(hours=2),
        "minus_3h": timedelta(hours=3),
    }
    occurred_at = datetime.now(UTC) - offsets[payload.rsplit(":", 1)[1]]
    data = await state.get_data()
    timezone = str(data["timezone"])
    await state.update_data(occurred_at=occurred_at.isoformat())
    await state.set_state(AddExpenseStates.participants)
    await show(target_message,
        translate(
            language,
            "date_selected",
            date=escape(format_local_datetime(occurred_at, timezone, language)),
        )
    )
    await show(target_message,
        _participant_summary(data.get("participants", []), language),
        reply_markup=await draft_participant_keyboard(state, language),
    )
    await callback.answer()


@router.callback_query(F.data == "expense:date:custom")
async def request_custom_expense_date(
    callback: CallbackQuery, state: FSMContext, language: Language
) -> None:
    """Prompt for a custom local transaction date and time."""
    if await state.get_state() != AddExpenseStates.expense_date.state:
        await callback.answer(translate(language, "draft_expired"), show_alert=True)
        return
    target_message = callback_message(callback)
    data = await state.get_data()
    await state.set_state(AddExpenseStates.custom_date)
    await show(target_message,
        translate(language, "enter_custom_date"),
        reply_markup=_expense_navigation(
            language, back="expense:nav:date",
            keep=bool(data.get("edit_mode") and data.get("occurred_at")),
        ),
    )
    await callback.answer()


@router.callback_query(F.data == "expense:date:back")
async def expense_date_back(
    callback: CallbackQuery, state: FSMContext, language: Language
) -> None:
    """Return from date selection to total entry."""
    target_message = callback_message(callback)
    await state.set_state(AddExpenseStates.total)
    await render_expense_draft(target_message, state, language)
    await callback.answer()


@router.message(AddExpenseStates.custom_date, F.text.in_(button_values("back")))
async def custom_expense_date_back(
    message: Message, state: FSMContext, language: Language
) -> None:
    """Return from custom date entry to the date presets."""
    await state.set_state(AddExpenseStates.expense_date)
    await render_expense_draft(message, state, language)


@router.message(AddExpenseStates.custom_date)
async def receive_custom_expense_date(
    message: Message, state: FSMContext, language: Language
) -> None:
    """Parse a custom local datetime and continue to participants."""
    data = await state.get_data()
    timezone = str(data["timezone"])
    try:
        occurred_at = parse_local_datetime(message.text or "", timezone)
    except DomainError:
        await show(message, translate(language, "invalid_custom_date"))
        return
    await state.update_data(occurred_at=occurred_at.isoformat())
    await state.set_state(AddExpenseStates.participants)
    await show(message,
        translate(
            language,
            "date_selected",
            date=escape(format_local_datetime(occurred_at, timezone, language)),
        )
    )
    await show(message,
        _participant_summary(data.get("participants", []), language),
        reply_markup=await draft_participant_keyboard(state, language),
    )


@router.message(AddExpenseStates.participants, F.users_shared)
async def receive_shared_users(
    message: Message, state: FSMContext, services: Services, language: Language
) -> None:
    """Resolve Telegram-shared users and add them to the expense draft."""
    if (await state.get_data()).get("group_id"):
        await show(message, translate(language, "group_member_only"))
        return
    if message.users_shared is None:
        return
    person = await current_person(message, services)
    data = await state.get_data()
    participants: list[dict[str, str]] = data["participants"]
    existing = {item["id"] for item in participants}
    for shared in message.users_shared.users:
        first_name = getattr(shared, "first_name", None) or f"Telegram user {shared.user_id}"
        candidate = await services.guests.get_or_create_telegram_guest(
            person.id,
            SharedTelegramUser(
                telegram_user_id=shared.user_id,
                first_name=first_name,
                last_name=getattr(shared, "last_name", None),
                username=getattr(shared, "username", None),
            ),
        )
        if str(candidate.id) not in existing and len(participants) < 10:
            participants.append(
                {
                    "id": str(candidate.id),
                    "name": participant_label(
                        candidate.display_name, candidate.id, candidate.username
                    ),
                }
            )
            existing.add(str(candidate.id))
    await state.update_data(participants=participants, exact_amounts={}, exact_index=0)
    await show(message,
        _participant_summary(participants, language),
        reply_markup=await draft_participant_keyboard(state, language),
    )


@router.message(AddExpenseStates.participants, F.contact)
async def receive_expense_contact(
    message: Message, state: FSMContext, services: Services, language: Language,
) -> None:
    """Add a Telegram contact while keeping the persistent keyboard unchanged."""
    if (await state.get_data()).get("group_id"):
        await show(message, translate(language, "group_member_only"))
        return
    contact = message.contact
    if contact is None or contact.user_id is None:
        await show(message, translate(language, "contact_requires_telegram_id"))
        return
    owner = await current_person(message, services)
    guest = await services.guests.get_or_create_telegram_guest(
        owner.id,
        SharedTelegramUser(
            telegram_user_id=contact.user_id,
            first_name=contact.first_name,
            last_name=contact.last_name,
            username=None,
        ),
    )
    data = await state.get_data()
    participants: list[dict[str, str]] = data["participants"]
    if str(guest.id) not in {item["id"] for item in participants}:
        if len(participants) >= 10:
            await show(message, translate(language, "participant_limit"))
            return
        participants.append({
            "id": str(guest.id),
            "name": participant_label(guest.display_name, guest.id, guest.username),
        })
        await state.update_data(participants=participants, exact_amounts={}, exact_index=0)
    await show(message,
        _participant_summary(participants, language),
        reply_markup=await draft_participant_keyboard(state, language),
    )


@router.message(AddExpenseStates.participants, F.text.in_(button_values("add_manual")))
async def request_manual_name(
    message: Message, state: FSMContext, language: Language
) -> None:
    """Prompt for a manually named participant."""
    if (await state.get_data()).get("group_id"):
        await show(message, translate(language, "group_member_only"))
        return
    await state.set_state(AddExpenseStates.manual_name)
    await render_expense_draft(message, state, language)


@router.message(
    AddExpenseStates.participants,
    F.text.in_(button_values("add_from_friends")),
)
@router.message(AddExpenseStates.participants, F.text.in_(button_values("group_expense_members")))
async def choose_friend(
    message: Message, state: FSMContext, services: Services, language: Language
) -> None:
    """Show active friends available as expense participants."""
    owner = await current_person(message, services)
    data = await state.get_data()
    if data.get("group_id"):
        await _group_member_choices(message, state, services, language, 0)
        return
    friends = list(await services.friends.list_friends(owner.id))
    if not friends:
        await show(message, translate(language, "no_friends"))
        return
    await show(message,
        translate(language, "choose_friend"),
        reply_markup=expense_friends_keyboard(friends, language),
    )


@router.callback_query(F.data.startswith("expense:addfriend:"))
async def add_friend_participant(
    callback: CallbackQuery,
    state: FSMContext,
    services: Services,
    language: Language,
) -> None:
    """Add a selected active friend to the current expense draft."""
    if await state.get_state() != AddExpenseStates.participants.state:
        await callback.answer(translate(language, "draft_expired"), show_alert=True)
        return
    if callback.from_user is None:
        return
    payload, target_message = callback_payload(callback)
    owner = await services.users.find_registered_target(callback.from_user.id)
    if owner is None:
        await callback.answer(translate(language, "use_start"), show_alert=True)
        return
    person_id = UUID(payload.rsplit(":", 1)[1])
    if (await state.get_data()).get("group_id"):
        await callback.answer(translate(language, "group_member_only"), show_alert=True)
        return
    available = {
        friend.person_id: friend
        for friend in await services.friends.list_friends(owner.id)
    }
    friend = available.get(person_id)
    if friend is None:
        await callback.answer(translate(language, "person_unavailable"), show_alert=True)
        return
    data = await state.get_data()
    participants: list[dict[str, str]] = data["participants"]
    if str(friend.person_id) not in {item["id"] for item in participants}:
        if len(participants) >= 10:
            await callback.answer(translate(language, "participant_limit"), show_alert=True)
            return
        participants.append(
            {
                "id": str(friend.person_id),
                "name": friend_label(friend),
            }
        )
        await state.update_data(participants=participants, exact_amounts={}, exact_index=0)
    settings = await services.user_settings.get_or_create(owner.id)
    await show(target_message,
        _participant_summary(participants, language),
        reply_markup=await draft_participant_keyboard(state, settings.language),
    )
    await callback.answer()


@router.message(AddExpenseStates.manual_name, F.text.in_(button_values("back")))
async def manual_back(message: Message, state: FSMContext, language: Language) -> None:
    """Return from manual naming to participant selection."""
    await state.set_state(AddExpenseStates.participants)
    await show(message,
        translate(language, "continue_participants"),
        reply_markup=await draft_participant_keyboard(state, language),
    )


@router.message(AddExpenseStates.manual_name)
async def receive_manual_name(
    message: Message, state: FSMContext, services: Services, language: Language
) -> None:
    """Create a manual guest and add it to the expense draft."""
    if (await state.get_data()).get("group_id"):
        await show(message, translate(language, "group_member_only"))
        return
    owner = await current_person(message, services)
    try:
        guest = await services.guests.create_manual_guest(owner.id, message.text or "")
    except DomainError as exc:
        await show(message, str(exc))
        return
    data = await state.get_data()
    participants: list[dict[str, str]] = data["participants"]
    if len(participants) >= 10:
        await show(message, translate(language, "participant_limit"))
    else:
        participants.append(
            {
                "id": str(guest.id),
                "name": participant_label(guest.display_name, guest.id, guest.username),
            }
        )
        await state.update_data(participants=participants, exact_amounts={}, exact_index=0)
    await state.set_state(AddExpenseStates.participants)
    await show(message,
        _participant_summary(participants, language),
        reply_markup=await draft_participant_keyboard(state, language),
    )


@router.message(AddExpenseStates.participants, F.text.in_(button_values("back")))
async def participants_back(
    message: Message, state: FSMContext, language: Language
) -> None:
    """Return from participant selection to transaction-time selection."""
    await state.set_state(AddExpenseStates.expense_date)
    await render_expense_draft(message, state, language)


@router.message(
    AddExpenseStates.participants,
    F.text.in_(button_values("remove_participant")),
)
async def choose_participant_to_remove(
    message: Message, state: FSMContext, language: Language
) -> None:
    """Show removable participants from the current draft."""
    data = await state.get_data()
    participants: list[dict[str, str]] = data["participants"]
    if len(participants) == 1:
        await show(message, translate(language, "no_participants_remove"))
        return
    await show(message,
        translate(language, "choose_remove"),
        reply_markup=remove_participant_keyboard(
            participants, "" if data.get("group_id") else data["creator_id"], language
        ),
    )


@router.callback_query(F.data.startswith("expense:remove:"))
async def remove_participant(
    callback: CallbackQuery, state: FSMContext, language: Language
) -> None:
    """Remove a selected non-creator participant from the draft."""
    if await state.get_state() != AddExpenseStates.participants.state:
        await callback.answer(translate(language, "draft_expired"), show_alert=True)
        return
    payload, target_message = callback_payload(callback)
    person_id = payload.rsplit(":", 1)[1]
    data = await state.get_data()
    if person_id == data["creator_id"] and not data.get("group_id"):
        await callback.answer(translate(language, "payer_remove"), show_alert=True)
        return
    participants: list[dict[str, str]] = data["participants"]
    updated = [item for item in participants if item["id"] != person_id]
    changes: dict[str, Any] = {"participants": updated, "exact_amounts": {}, "exact_index": 0}
    if not data.get("group_id") and data.get("payer_id") == person_id:
        changes["payer_id"] = None
    await state.update_data(**changes)
    await show(target_message,
        _participant_summary(updated, language),
        reply_markup=await draft_participant_keyboard(state, language),
    )
    await callback.answer()


@router.message(AddExpenseStates.participants, F.text.in_(button_values("done")))
async def participants_done(
    message: Message, state: FSMContext, services: Services, language: Language
) -> None:
    """Validate participant count and ask who paid for the expense."""
    data = await state.get_data()
    if data.get("group_id"):
        group = await services.groups.get(UUID(data["creator_id"]), UUID(data["group_id"]))
        data = await state.update_data(group_members=[_member(m) for m in group.participants])
    participants: list[dict[str, str]] = data["participants"]
    if len(participants) < 2:
        await show(message, translate(language, "add_one_participant"))
        return
    await state.set_state(AddExpenseStates.payer)
    await show(message, _participant_summary(participants, language))
    await show(message,
        translate(language, "choose_payer"),
        reply_markup=draft_payer_keyboard(data, language),
    )


@router.callback_query(F.data == "expense:payer:back")
async def payer_back(
    callback: CallbackQuery, state: FSMContext, language: Language
) -> None:
    """Return from payer selection to participant selection."""
    if await state.get_state() != AddExpenseStates.payer.state:
        await callback.answer(translate(language, "draft_expired"), show_alert=True)
        return
    target_message = callback_message(callback)
    data = await state.get_data()
    participants: list[dict[str, str]] = data.get("participants", [])
    await state.set_state(AddExpenseStates.participants)
    await show(target_message, translate(language, "payer_selection_cancelled"))
    await show(target_message,
        _participant_summary(participants, language),
        reply_markup=await draft_participant_keyboard(state, language),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("expense:setpayer:"))
async def choose_payer(
    callback: CallbackQuery, state: FSMContext, language: Language
) -> None:
    """Store a selected participant as payer and request a split method."""
    if await state.get_state() != AddExpenseStates.payer.state:
        await callback.answer(translate(language, "draft_expired"), show_alert=True)
        return
    payload, target_message = callback_payload(callback)
    data = await state.get_data()
    participants: list[dict[str, str]] = data.get("participants", [])
    try:
        payer_id = str(UUID(payload.rsplit(":", 1)[1]))
    except ValueError:
        await callback.answer(
            translate(language, "person_unavailable"), show_alert=True
        )
        return
    eligible_payers = data.get("group_members") or participants
    payer = next((item for item in eligible_payers if item["id"] == payer_id), None)
    if payer is None:
        await callback.answer(
            translate(language, "person_unavailable"), show_alert=True
        )
        return
    payer_name = (
        translate(language, "you")
        if payer_id == str(data["creator_id"])
        else escape(payer["name"])
    )
    await state.update_data(payer_id=payer_id)
    if data.get("exact_amounts") and not _exact_complete({**data, "payer_id": payer_id}):
        await state.update_data(exact_amounts={}, exact_index=0)
    await state.set_state(AddExpenseStates.split_method)
    await show(target_message,
        translate(language, "payer_selected", name=payer_name)
        + "\n\n"
        + translate(language, "split_how"),
        reply_markup=split_method_keyboard(
            language, include_keep=bool(data.get("edit_mode") and data.get("split_method"))
        ),
    )
    await callback.answer()


@router.callback_query(F.data == "expense:split:back")
async def split_method_back(
    callback: CallbackQuery, state: FSMContext, language: Language
) -> None:
    """Return from split-method selection to payer selection."""
    if await state.get_state() != AddExpenseStates.split_method.state:
        await callback.answer(translate(language, "draft_expired"), show_alert=True)
        return
    target_message = callback_message(callback)
    data = await state.get_data()
    await state.set_state(AddExpenseStates.payer)
    await show(target_message,
        translate(language, "choose_payer"),
        reply_markup=draft_payer_keyboard(data, language),
    )
    await callback.answer()


@router.callback_query(F.data == "expense:split:equal")
async def choose_equal(
    callback: CallbackQuery, state: FSMContext, language: Language
) -> None:
    """Allocate the draft equally and show its confirmation preview."""
    target_message = callback_message(callback)
    if await state.get_state() != AddExpenseStates.split_method.state:
        await callback.answer(translate(language, "draft_expired"), show_alert=True)
        return
    data = await state.get_data()
    participants: list[dict[str, str]] = data.get("participants", [])
    if len(participants) < 2 or "payer_id" not in data:
        await callback.answer(translate(language, "draft_expired"), show_alert=True)
        return
    allocations = EqualSplitStrategy().allocate(
        data["total_minor"], [UUID(item["id"]) for item in participants]
    )
    await state.update_data(split_method=SplitMethod.EQUAL.value)
    await state.set_state(AddExpenseStates.confirm)
    await show(target_message,
        translate(language, "split_choice_saved", method=translate(language, "split_equally"))
    )
    await show(target_message,
        _review_text(
            data,
            participants,
            {str(a.person_id): a.owed_minor for a in allocations},
            language,
        ),
        reply_markup=expense_confirm_keyboard(language, data.get("draft_id")),
    )
    await callback.answer()


@router.callback_query(F.data == "expense:split:exact")
async def choose_exact(
    callback: CallbackQuery, state: FSMContext, language: Language
) -> None:
    """Begin collecting exact participant shares in stable order."""
    target_message = callback_message(callback)
    if await state.get_state() != AddExpenseStates.split_method.state:
        await callback.answer(translate(language, "draft_expired"), show_alert=True)
        return
    data = await state.get_data()
    participants: list[dict[str, str]] = data.get("participants", [])
    if len(participants) < 2 or "payer_id" not in data:
        await callback.answer(translate(language, "draft_expired"), show_alert=True)
        return
    saved_amounts = (
        data.get("exact_amounts", {})
        if data.get("edit_mode") and data.get("split_method") == SplitMethod.EXACT.value
        else {}
    )
    await state.update_data(
        split_method=SplitMethod.EXACT.value,
        exact_amounts=saved_amounts,
        exact_index=0,
    )
    await state.set_state(AddExpenseStates.exact_amount)
    await show(target_message,
        translate(language, "split_choice_saved", method=translate(language, "exact_amounts"))
    )
    await render_expense_draft(target_message, state, language)
    await callback.answer()


@router.message(AddExpenseStates.exact_amount, F.text.in_(button_values("back")))
async def exact_back(message: Message, state: FSMContext, language: Language) -> None:
    """Revisit the preceding share, forgetting that share and its dependent remainder."""
    data = await state.get_data()
    index = max(0, int(data.get("exact_index", 0)) - 1)
    if int(data.get("exact_index", 0)) == 0:
        await state.set_state(AddExpenseStates.split_method)
    else:
        retained = {p["id"] for p in data["participants"][:index]}
        await state.update_data(
            exact_index=index,
            exact_amounts={k: v for k, v in data.get("exact_amounts", {}).items() if k in retained},
        )
    await render_expense_draft(message, state, language)


@router.callback_query(AddExpenseStates.confirm, F.data == "eg:review")
async def return_to_review(callback: CallbackQuery, state: FSMContext, language: Language) -> None:
    """Leave the group picker without changing the reviewed expense."""
    await render_expense_draft(callback_message(callback), state, language)
    await callback.answer()


@router.callback_query(AddExpenseStates.confirm, F.data == "expense:review:back")
async def review_back(callback: CallbackQuery, state: FSMContext, language: Language) -> None:
    """Return to the final allocation step before confirmation."""
    data = await state.get_data()
    if data["split_method"] == SplitMethod.EXACT.value:
        index = 0 if len(data["participants"]) == 2 else len(data["participants"]) - 1
        retained = {p["id"] for p in data["participants"][:index]}
        await state.update_data(exact_index=index, exact_amounts={
            k: v for k, v in data["exact_amounts"].items() if k in retained
        })
        await state.set_state(AddExpenseStates.exact_amount)
    else:
        await state.set_state(AddExpenseStates.split_method)
    await render_expense_draft(callback_message(callback), state, language)
    await callback.answer()


@router.callback_query(AddExpenseStates.description, F.data == "expense:origin")
async def expense_origin(
    callback: CallbackQuery, state: FSMContext, services: Services, language: Language,
) -> None:
    """Leave the first expense step for the draft, group, or main menu that opened it."""
    from splitnshare.presentation.routers import drafts, groups, start

    data = await state.get_data()
    if data.get("edit_origin") == "review":
        await state.set_state(AddExpenseStates.confirm)
        await render_expense_draft(callback_message(callback), state, language)
        await callback.answer()
    elif data.get("edit_mode") and data.get("draft_id"):
        await drafts.view_draft(callback.model_copy(update={
            "data": f"draft:view:{data['draft_id']}"
        }), state, language)
    elif data.get("group_id"):
        await groups.group_details(callback.model_copy(update={
            "data": f"g:view:{uuid_token(UUID(data['group_id']))}"
        }), state, services, language)
    else:
        await start.show_main_menu_callback(callback, state, services, language)


@router.message(AddExpenseStates.exact_amount)
async def receive_exact_amount(
    message: Message, state: FSMContext, language: Language
) -> None:
    """Collect one exact share and advance or display the review."""
    data = await state.get_data()
    participants: list[dict[str, str]] = data["participants"]
    index: int = data["exact_index"]
    if index >= len(participants):
        await render_expense_draft(message, state, language)
        return
    total = Money(data["total_minor"], data["currency"])
    try:
        amount = parse_share_minor(message.text or "", total)
    except DomainError as exc:
        await show(message, str(exc))
        return
    exact: dict[str, int] = dict(data["exact_amounts"])
    current = participants[index]
    if len(participants) == 2:
        other = participants[1 - index]
        remainder = total.minor - amount
        if remainder < 0 or (
            remainder == 0 and other["id"] != data["payer_id"]
        ) or (amount == 0 and current["id"] != data["payer_id"]):
            await show(message, translate(language, "exact_first_share_invalid"))
            return
        exact[other["id"]] = remainder
        index = len(participants)
    else:
        index += 1
    exact[current["id"]] = amount
    await state.update_data(exact_amounts=exact, exact_index=index)
    if index < len(participants):
        await render_expense_draft(message, state, language)
        return
    if not _exact_complete({**data, "exact_amounts": exact}):
        await state.update_data(exact_amounts={}, exact_index=0)
        await show(message,
            translate(
                language,
                "shares_mismatch",
                total=total.format(),
                name=escape(participants[0]["name"]),
            )
        )
        await render_expense_draft(message, state, language)
        return
    await state.set_state(AddExpenseStates.confirm)
    await show(message,
        _review_text(data, participants, exact, language),
        reply_markup=expense_confirm_keyboard(language, data.get("draft_id")),
    )


@router.callback_query(F.data.startswith("expense:confirm"))
async def confirm_expense(
    callback: CallbackQuery,
    state: FSMContext,
    services: Services,
    bot: Bot,
    language: Language,
) -> None:
    """Create the reviewed expense and notify its registered participants."""
    target_message = callback_message(callback)
    data = await state.get_data()
    draft_id = data.get("draft_id")
    if (
        await state.get_state() != AddExpenseStates.confirm.state
        or not draft_id
        or callback.data != f"expense:confirm:{draft_id}"
        or not {"split_method", "payer_id"} <= data.keys()
    ):
        await callback.answer(translate(language, "draft_expired"), show_alert=True)
        return
    participants = tuple(UUID(item["id"]) for item in data["participants"])
    exact = data.get("exact_amounts")
    command = CreateExpenseCommand(
        creator_person_id=UUID(data["creator_id"]),
        description=data["description"],
        total=Money(data["total_minor"], data["currency"]),
        participant_ids=participants,
        split_method=SplitMethod(data["split_method"]),
        context=(
            GroupExpenseContext(UUID(data["group_id"]))
            if data.get("group_id") else DirectExpenseContext()
        ),
        payer_person_id=UUID(data["payer_id"]),
        exact_amounts_minor={UUID(key): value for key, value in exact.items()} if exact else None,
        occurred_at=datetime.fromisoformat(data["occurred_at"]),
        draft_id=UUID(draft_id),
    )
    try:
        expense = await services.expenses.create(command)
    except DomainError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    await state.clear()
    settings = await services.user_settings.get_or_create(expense.creator_person_id)
    await show(target_message,
        translate(language, "expense_saved")
        + "\n\n"
        + expense_text(expense, language, settings.timezone or "UTC"),
        reply_markup=back_to_main_menu_keyboard(settings.language),
    )
    await callback.answer()
    await _notify_expense_participants(bot, services, expense)


@router.callback_query(F.data == "expense:cancel")
async def cancel_expense_callback(
    callback: CallbackQuery, state: FSMContext, language: Language
) -> None:
    """Pause an inline expense draft without changing the persistent reply keyboard."""
    target_message = callback_message(callback)
    await state.clear()
    await show(target_message, translate(language, "draft_paused"))
    await callback.answer()


@router.message(F.text.in_(button_values("transactions")))
async def transactions(
    message: Message, services: Services, language: Language
) -> None:
    """Show the first transaction page from the reply menu."""
    person = await current_person(message, services)
    settings = await services.user_settings.get_or_create(person.id)
    page = await services.activities.list_for_person(person.id)
    if not page.items:
        await show(message,
            translate(language, "no_expenses"),
            reply_markup=back_to_main_menu_keyboard(language),
        )
        return
    await show(message,
        activity_text(page.items, person.id, language, settings.timezone or "UTC"),
        reply_markup=activity_list_keyboard(page, language, settings.timezone or "UTC"),
    )


@router.callback_query(F.data == "expense:list")
async def transactions_callback(
    callback: CallbackQuery, services: Services, language: Language
) -> None:
    """Send the first transaction page from expense-detail navigation."""
    if callback.from_user is None:
        return
    target_message = callback_message(callback)
    person = await services.users.find_registered_target(callback.from_user.id)
    if person is None:
        await callback.answer(translate(language, "use_start"), show_alert=True)
        return
    page = await services.activities.list_for_person(person.id)
    settings = await services.user_settings.get_or_create(person.id)
    if page.items:
        await show(target_message,
            activity_text(
                page.items, person.id, language, settings.timezone or "UTC"
            ),
            reply_markup=activity_list_keyboard(
                page, language, settings.timezone or "UTC"
            ),
        )
    else:
        await show(target_message,
            translate(language, "no_active_expenses"),
            reply_markup=back_to_main_menu_keyboard(language),
        )
    await callback.answer()


@router.callback_query(F.data == "menu:transactions")
async def menu_transactions_callback(
    callback: CallbackQuery, services: Services, language: Language
) -> None:
    """Replace the main-menu message with the first transaction page."""
    if callback.from_user is None:
        return
    target_message = callback_message(callback)
    person = await services.users.find_registered_target(callback.from_user.id)
    if person is None:
        await callback.answer(translate(language, "use_start"), show_alert=True)
        return
    page = await services.activities.list_for_person(person.id)
    settings = await services.user_settings.get_or_create(person.id)
    await show(target_message,
        (
            activity_text(
                page.items, person.id, language, settings.timezone or "UTC"
            )
            if page.items
            else translate(language, "no_active_expenses")
        ),
        reply_markup=(
            activity_list_keyboard(page, language, settings.timezone or "UTC")
            if page.items
            else back_to_main_menu_keyboard(language)
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("activity:page:"))
async def transactions_page(
    callback: CallbackQuery, services: Services, language: Language
) -> None:
    """Replace transaction text and buttons with the requested cursor page."""
    if callback.from_user is None:
        return
    payload, target_message = callback_payload(callback)
    person = await services.users.find_registered_target(callback.from_user.id)
    if person is None:
        await callback.answer(translate(language, "use_start"), show_alert=True)
        return
    cursor = payload.split(":", 2)[2]
    page = await services.activities.list_for_person(person.id, cursor=cursor)
    settings = await services.user_settings.get_or_create(person.id)
    await show(target_message,
        activity_text(page.items, person.id, language, settings.timezone or "UTC"),
        reply_markup=activity_list_keyboard(
            page, language, settings.timezone or "UTC"
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("expense:view:"))
async def view_expense(
    callback: CallbackQuery, services: Services, language: Language
) -> None:
    """Show full details for a selected visible expense."""
    if callback.from_user is None:
        return
    payload, target_message = callback_payload(callback)
    person = await services.users.find_registered_target(callback.from_user.id)
    if person is None:
        await callback.answer(translate(language, "use_start"), show_alert=True)
        return
    expense_id = UUID(payload.rsplit(":", 1)[1])
    expense = await services.expense_queries.get_details(person.id, expense_id)
    settings = await services.user_settings.get_or_create(person.id)
    await show(target_message,
        expense_text(expense, language, settings.timezone or "UTC"),
        reply_markup=expense_details_keyboard(expense, person.id, language),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("expense:delete_ask:"))
async def ask_delete(callback: CallbackQuery, language: Language) -> None:
    """Request confirmation before soft-deleting an expense."""
    payload, target_message = callback_payload(callback)
    expense_id = UUID(payload.rsplit(":", 1)[1])
    await show(target_message,
        translate(language, "delete_question"),
        reply_markup=delete_confirm_keyboard(expense_id, language),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("expense:delete:"))
async def delete_expense(
    callback: CallbackQuery, services: Services, language: Language
) -> None:
    """Soft-delete a confirmed expense and report the result."""
    if callback.from_user is None:
        return
    payload, target_message = callback_payload(callback)
    person = await services.users.find_registered_target(callback.from_user.id)
    if person is None:
        await callback.answer(translate(language, "use_start"), show_alert=True)
        return
    expense_id = UUID(payload.rsplit(":", 1)[1])
    try:
        changed = await services.expenses.delete(person.id, expense_id)
    except DomainError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    await show(target_message,
        translate(language, "expense_deleted" if changed else "expense_already_deleted")
    )
    await callback.answer()


def _participant_summary(
    participants: list[dict[str, str]], language: Language
) -> str:
    """Render currently selected draft participants."""
    return translate(language, "participants") + "\n" + "\n".join(
        f"• {escape(item['name'])}" for item in participants
    )


def _review_text(
    data: dict[str, Any],
    participants: list[dict[str, str]],
    amounts: dict[str, int],
    language: Language,
) -> str:
    """Render the final localized expense review from FSM draft data."""
    total = Money(int(data["total_minor"]), str(data["currency"]))
    lines = [
        translate(language, "review", description=escape(str(data["description"]))),
        translate(language, "total", total=total.format()),
        translate(
            language,
            "expense_date",
            date=escape(
                format_local_datetime(
                    datetime.fromisoformat(str(data["occurred_at"])),
                    str(data["timezone"]),
                    language,
                )
            ),
        ),
        translate(
            language,
            "expense_paid_by",
            name=(
                translate(language, "you")
                if str(data["payer_id"]) == str(data["creator_id"])
                else escape(
                    next(
                        item["name"]
                        for item in (data.get("group_members") or participants)
                        if item["id"] == str(data["payer_id"])
                    )
                )
            ),
        ),
        "",
    ]
    if data.get("group_name"):
        lines.append(translate(language, "group_review_label", name=escape(data["group_name"])))
    lines.extend(
        f"• {escape(item['name'])}: {Money(amounts[item['id']], total.currency).format()}"
        for item in participants
    )
    return "\n".join(lines)


async def _notify_expense_participants(
    bot: Bot, services: Services, expense: ExpenseDTO
) -> None:
    """Best-effort notify every registered participant except the creator."""
    recipient_ids = tuple(
        ({split.person_id for split in expense.splits} | {expense.payer_person_id})
        - {expense.creator_person_id}
    )
    recipients = await services.users.list_registered(recipient_ids)
    for recipient in recipients:
        if recipient.telegram_user_id is None:
            continue
        settings = await services.user_settings.find_by_telegram_id(
            recipient.telegram_user_id
        )
        recipient_language = (
            settings.language if settings is not None else Language.ENGLISH
        )
        try:
            await bot.send_message(
                recipient.telegram_user_id,
                expense_notification_text(
                    expense, recipient.id, recipient_language
                ),
            )
        except TelegramAPIError:
            # Expense creation is authoritative; notifications are best effort.
            continue
