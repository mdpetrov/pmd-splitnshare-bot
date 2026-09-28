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
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
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
    cancel_keyboard,
    delete_confirm_keyboard,
    expense_confirm_keyboard,
    expense_date_keyboard,
    expense_details_keyboard,
    expense_friends_keyboard,
    expense_payer_keyboard,
    main_menu,
    participant_keyboard,
    remove_participant_keyboard,
    split_method_keyboard,
)
from splitnshare.presentation.labels import friend_label, participant_label
from splitnshare.presentation.routers.groups import _keyboard, _member
from splitnshare.presentation.states import AddExpenseStates

router = Router(name="expenses")
router.message.filter(F.chat.type == "private")
router.callback_query.filter(F.message.chat.type == "private")


async def draft_participant_keyboard(state: FSMContext, language: Language) -> ReplyKeyboardMarkup:
    """Restrict group drafts to member selection while retaining ordinary expense actions."""
    data = await state.get_data()
    include_keep = bool(data.get("edit_mode") and len(data.get("participants", [])) >= 2)
    if not data.get("group_id"):
        return participant_keyboard(language, include_keep=include_keep)
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text=translate(language, "group_expense_members"))],
        [
            KeyboardButton(text=translate(language, "remove_participant")),
            KeyboardButton(text=translate(language, "done")),
        ],
        *([[KeyboardButton(text=translate(language, "keep"))]] if include_keep else []),
        [
            KeyboardButton(text=translate(language, "back")),
            KeyboardButton(text=translate(language, "cancel")),
        ],
    ], resize_keyboard=True)


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
    return markup


@router.callback_query(AddExpenseStates.payer, F.data.startswith("eg:payers:"))
async def payer_page(callback: CallbackQuery, state: FSMContext, language: Language) -> None:
    """Display the next page of eligible group payers."""
    page = max(0, int((callback.data or "").rsplit(":", 1)[1]))
    await callback_message(callback).edit_reply_markup(
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
    await message.answer(
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
        participants=participants, group_members=[_member(m) for m in group.participants]
    )
    await callback_message(callback).answer(
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
    await callback_message(callback).answer(
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
    """Attach a group and discard allocations requiring participant revalidation."""
    data = await state.get_data()
    token = (callback.data or "").rsplit(":", 1)[1]
    if token == "none":
        await state.update_data(
            group_id=None, group_name=None, group_currency=None, group_members=None
        )
        name = translate(language, "group_none")
    else:
        group = await services.groups.get(UUID(data["creator_id"]), uuid_from_token(token))
        allowed = {str(m.id) for m in group.participants}
        participants = [p for p in data["participants"] if p["id"] in allowed]
        await state.update_data(
            group_id=str(group.id), group_name=group.name, group_currency=group.default_currency,
            group_members=[_member(m) for m in group.participants], participants=participants,
        )
        name = group.name
    await state.update_data(exact_amounts={}, exact_index=0, payer_id=None, split_method=None)
    await state.set_state(AddExpenseStates.participants)
    await callback_message(callback).edit_text(
        translate(language, "group_reselect", name=escape(name))
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
    await state.update_data(edit_mode=True)
    await state.set_state(AddExpenseStates.description)
    await render_expense_draft(callback_message(callback), state, language)
    await callback.answer()


@router.callback_query(F.data == "expense:keep")
async def keep_inline_expense_value(
    callback: CallbackQuery, state: FSMContext, language: Language
) -> None:
    """Retain a saved date, payer, or split method during draft editing."""
    data = await state.get_data()
    step = await state.get_state()
    if not data.get("edit_mode"):
        await callback.answer(translate(language, "draft_expired"), show_alert=True)
        return
    target_message = callback_message(callback)
    if step == AddExpenseStates.expense_date.state and data.get("occurred_at"):
        await state.set_state(AddExpenseStates.participants)
        await target_message.edit_text(
            translate(
                language, "date_selected",
                date=escape(format_local_datetime(
                    datetime.fromisoformat(data["occurred_at"]),
                    data.get("timezone", "UTC"), language,
                )),
            )
        )
        await target_message.answer(
            _participant_summary(data.get("participants", []), language),
            reply_markup=await draft_participant_keyboard(state, language),
        )
    elif step == AddExpenseStates.payer.state and data.get("payer_id"):
        await state.set_state(AddExpenseStates.split_method)
        await target_message.edit_text(
            translate(language, "split_how"),
            reply_markup=split_method_keyboard(
                language, include_keep=bool(data.get("split_method"))
            ),
        )
    elif step == AddExpenseStates.split_method.state and data.get("split_method"):
        await target_message.edit_text(
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
        await message.answer(translate(language, "draft_expired"))
        return
    if step == AddExpenseStates.description.state and data.get("description"):
        await state.set_state(AddExpenseStates.total)
        await render_expense_draft(message, state, language)
    elif step == AddExpenseStates.total.state and "total_minor" in data:
        await state.set_state(AddExpenseStates.expense_date)
        await message.answer(
            translate(
                language, "total",
                total=Money(data["total_minor"], data["currency"]).format(),
            ),
            reply_markup=main_menu(language),
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
                await message.answer(
                    translate(language, "main_menu"), reply_markup=main_menu(language)
                )
                await render_expense_draft(message, state, language)
            else:
                await render_expense_draft(message, state, language)
        else:
            await message.answer(translate(language, "draft_expired"))
    else:
        await message.answer(translate(language, "draft_expired"))


def _exact_complete(data: dict[str, Any]) -> bool:
    """Check that every saved exact share still matches the current participants."""
    participants = data.get("participants", [])
    amounts = data.get("exact_amounts") or {}
    return (
        2 <= len(participants) <= 10
        and all(person["id"] in amounts for person in participants)
        and sum(amounts[person["id"]] for person in participants)
        == data.get("total_minor")
    )


async def render_expense_draft(message: Message, state: FSMContext, language: Language) -> None:
    """Recreate the current expense prompt from persisted values without resetting them."""
    step = await state.get_state()
    data = await state.get_data()
    participants = data.get("participants", [])
    editing = bool(data.get("edit_mode"))
    markup: InlineKeyboardMarkup | ReplyKeyboardMarkup = cancel_keyboard(language)
    if step == AddExpenseStates.exact_amount.state:
        index = int(data.get("exact_index", 0))
        if index >= len(participants):
            if _exact_complete(data):
                await state.set_state(AddExpenseStates.confirm)
                step = AddExpenseStates.confirm.state
                await message.answer(
                    translate(language, "main_menu"), reply_markup=main_menu(language)
                )
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
        markup = cancel_keyboard(
            language, include_back=False,
            include_keep=editing and bool(data.get("description")),
        )
    elif step == AddExpenseStates.total.state:
        text = translate(language, "enter_total")
        if "total_minor" in data:
            text += "\n\n" + Money(data["total_minor"], data["currency"]).format()
        markup = cancel_keyboard(language, include_keep=editing and "total_minor" in data)
    elif step == AddExpenseStates.expense_date.state:
        text, markup = translate(language, "choose_expense_date"), expense_date_keyboard(
            language, include_keep=editing and bool(data.get("occurred_at"))
        )
    elif step == AddExpenseStates.custom_date.state:
        text = translate(language, "enter_custom_date")
        markup = cancel_keyboard(language, include_keep=editing and bool(data.get("occurred_at")))
    elif step == AddExpenseStates.participants.state:
        text = _participant_summary(participants, language)
        markup = await draft_participant_keyboard(state, language)
    elif step == AddExpenseStates.manual_name.state:
        text = translate(language, "guest_name")
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
        text = translate(language, "owes_next", name=escape(participants[index]["name"]))
        markup = cancel_keyboard(
            language,
            include_keep=(
                editing and participants[index]["id"] in data.get("exact_amounts", {})
            ),
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
    await message.answer(text, reply_markup=markup)


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
    await message.answer(
        translate(language, "expense_for"),
        reply_markup=cancel_keyboard(language, include_back=False),
    )


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
    await target_message.answer(
        translate(language, "expense_for"),
        reply_markup=cancel_keyboard(language, include_back=False),
    )
    await callback.answer()


@router.message(AddExpenseStates.description, F.text.in_(button_values("back")))
async def description_back(
    message: Message, state: FSMContext, language: Language
) -> None:
    """Leave description entry and return to the main menu."""
    await state.clear()
    await message.answer(translate(language, "back_main"), reply_markup=main_menu(language))


@router.message(AddExpenseStates.description)
async def receive_description(
    message: Message, state: FSMContext, language: Language
) -> None:
    """Validate the expense description and request its total."""
    text = (message.text or "").strip()
    if not 1 <= len(text) <= 240:
        await message.answer(translate(language, "description_invalid"))
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
        await message.answer(str(exc))
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
    await message.answer(
        translate(language, "total", total=total.format()), reply_markup=main_menu(language)
    )
    await message.answer(
        translate(language, "choose_expense_date"),
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
    await target_message.edit_text(
        translate(
            language,
            "date_selected",
            date=escape(format_local_datetime(occurred_at, timezone, language)),
        )
    )
    await target_message.answer(
        translate(language, "add_people"),
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
    await target_message.answer(
        translate(language, "enter_custom_date"),
        reply_markup=cancel_keyboard(
            language, include_keep=bool(data.get("edit_mode") and data.get("occurred_at"))
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
        await message.answer(translate(language, "invalid_custom_date"))
        return
    await state.update_data(occurred_at=occurred_at.isoformat())
    await state.set_state(AddExpenseStates.participants)
    await message.answer(
        translate(
            language,
            "date_selected",
            date=escape(format_local_datetime(occurred_at, timezone, language)),
        )
    )
    await message.answer(
        translate(language, "add_people"),
        reply_markup=await draft_participant_keyboard(state, language),
    )


@router.message(AddExpenseStates.participants, F.users_shared)
async def receive_shared_users(
    message: Message, state: FSMContext, services: Services, language: Language
) -> None:
    """Resolve Telegram-shared users and add them to the expense draft."""
    if (await state.get_data()).get("group_id"):
        await message.answer(translate(language, "group_member_only"))
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
    await state.update_data(participants=participants)
    await message.answer(
        _participant_summary(participants, language),
        reply_markup=await draft_participant_keyboard(state, language),
    )


@router.message(AddExpenseStates.participants, F.text.in_(button_values("add_manual")))
async def request_manual_name(
    message: Message, state: FSMContext, language: Language
) -> None:
    """Prompt for a manually named participant."""
    if (await state.get_data()).get("group_id"):
        await message.answer(translate(language, "group_member_only"))
        return
    await state.set_state(AddExpenseStates.manual_name)
    await message.answer(
        translate(language, "guest_name"), reply_markup=cancel_keyboard(language)
    )


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
        await message.answer(translate(language, "no_friends"))
        return
    await message.answer(
        translate(language, "choose_friend"),
        reply_markup=expense_friends_keyboard(friends),
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
        await state.update_data(participants=participants)
    settings = await services.user_settings.get_or_create(owner.id)
    await target_message.answer(
        _participant_summary(participants, language),
        reply_markup=await draft_participant_keyboard(state, settings.language),
    )
    await callback.answer()


@router.message(AddExpenseStates.manual_name, F.text.in_(button_values("back")))
async def manual_back(message: Message, state: FSMContext, language: Language) -> None:
    """Return from manual naming to participant selection."""
    await state.set_state(AddExpenseStates.participants)
    await message.answer(
        translate(language, "continue_participants"),
        reply_markup=await draft_participant_keyboard(state, language),
    )


@router.message(AddExpenseStates.manual_name)
async def receive_manual_name(
    message: Message, state: FSMContext, services: Services, language: Language
) -> None:
    """Create a manual guest and add it to the expense draft."""
    if (await state.get_data()).get("group_id"):
        await message.answer(translate(language, "group_member_only"))
        return
    owner = await current_person(message, services)
    try:
        guest = await services.guests.create_manual_guest(owner.id, message.text or "")
    except DomainError as exc:
        await message.answer(str(exc))
        return
    data = await state.get_data()
    participants: list[dict[str, str]] = data["participants"]
    if len(participants) >= 10:
        await message.answer(translate(language, "participant_limit"))
    else:
        participants.append(
            {
                "id": str(guest.id),
                "name": participant_label(guest.display_name, guest.id, guest.username),
            }
        )
        await state.update_data(participants=participants)
    await state.set_state(AddExpenseStates.participants)
    await message.answer(
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
        await message.answer(translate(language, "no_participants_remove"))
        return
    await message.answer(
        translate(language, "choose_remove"),
        reply_markup=remove_participant_keyboard(
            participants, "" if data.get("group_id") else data["creator_id"]
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
    changes: dict[str, Any] = {"participants": updated}
    if not data.get("group_id") and data.get("payer_id") == person_id:
        changes["payer_id"] = None
    await state.update_data(**changes)
    await target_message.answer(
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
        await message.answer(translate(language, "add_one_participant"))
        return
    await state.set_state(AddExpenseStates.payer)
    await message.answer(
        _participant_summary(participants, language), reply_markup=main_menu(language)
    )
    await message.answer(
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
    await target_message.edit_text(translate(language, "payer_selection_cancelled"))
    await target_message.answer(
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
    await state.set_state(AddExpenseStates.split_method)
    await target_message.edit_text(
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
    await target_message.edit_text(
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
    await target_message.edit_text(
        translate(language, "split_choice_saved", method=translate(language, "split_equally"))
    )
    await target_message.answer(
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
    await target_message.edit_text(
        translate(language, "split_choice_saved", method=translate(language, "exact_amounts"))
    )
    await render_expense_draft(target_message, state, language)
    await callback.answer()


@router.message(AddExpenseStates.exact_amount, F.text.in_(button_values("back")))
async def exact_back(message: Message, state: FSMContext, language: Language) -> None:
    """Cancel exact allocation and return to participant selection."""
    await state.set_state(AddExpenseStates.participants)
    await message.answer(
        translate(language, "split_again"),
        reply_markup=await draft_participant_keyboard(state, language),
    )


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
        await message.answer(str(exc))
        return
    exact: dict[str, int] = data["exact_amounts"]
    exact[participants[index]["id"]] = amount
    index += 1
    await state.update_data(exact_amounts=exact, exact_index=index)
    if index < len(participants):
        await render_expense_draft(message, state, language)
        return
    if not _exact_complete({**data, "exact_amounts": exact}):
        await state.update_data(exact_amounts={}, exact_index=0)
        await message.answer(
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
    await message.answer(
        translate(language, "main_menu"), reply_markup=main_menu(language)
    )
    await message.answer(
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
    await target_message.answer(
        translate(language, "expense_saved")
        + "\n\n"
        + expense_text(expense, language, settings.timezone or "UTC"),
        reply_markup=main_menu(settings.language),
    )
    await callback.answer()
    await _notify_expense_participants(bot, services, expense)


@router.callback_query(F.data == "expense:cancel")
async def cancel_expense_callback(
    callback: CallbackQuery, state: FSMContext, language: Language
) -> None:
    """Pause an inline expense draft and restore the main reply menu."""
    target_message = callback_message(callback)
    await state.clear()
    await target_message.answer(
        translate(language, "draft_paused"), reply_markup=main_menu(language)
    )
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
        await message.answer(
            translate(language, "no_expenses"),
            reply_markup=back_to_main_menu_keyboard(language),
        )
        return
    await message.answer(
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
        await target_message.answer(
            activity_text(
                page.items, person.id, language, settings.timezone or "UTC"
            ),
            reply_markup=activity_list_keyboard(
                page, language, settings.timezone or "UTC"
            ),
        )
    else:
        await target_message.answer(
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
    await target_message.edit_text(
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
    await target_message.edit_text(
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
    await target_message.answer(
        expense_text(expense, language, settings.timezone or "UTC"),
        reply_markup=expense_details_keyboard(expense, person.id, language),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("expense:delete_ask:"))
async def ask_delete(callback: CallbackQuery, language: Language) -> None:
    """Request confirmation before soft-deleting an expense."""
    payload, target_message = callback_payload(callback)
    expense_id = UUID(payload.rsplit(":", 1)[1])
    await target_message.answer(
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
    await target_message.edit_text(
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
