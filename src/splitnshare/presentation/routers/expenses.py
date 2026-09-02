from __future__ import annotations

from html import escape
from typing import Any
from uuid import UUID

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from splitnshare.application.dto import CreateExpenseCommand, SharedTelegramUser
from splitnshare.domain.contexts import DirectExpenseContext
from splitnshare.domain.enums import Language, SplitMethod
from splitnshare.domain.errors import DomainError
from splitnshare.domain.money import Money
from splitnshare.domain.splitting import EqualSplitStrategy
from splitnshare.presentation.container import Services
from splitnshare.presentation.formatters import expense_text
from splitnshare.presentation.helpers import (
    callback_message,
    callback_payload,
    current_person,
    parse_share_minor,
    parse_total,
)
from splitnshare.presentation.i18n import button_values, translate
from splitnshare.presentation.keyboards import (
    back_to_main_menu_keyboard,
    cancel_keyboard,
    delete_confirm_keyboard,
    expense_confirm_keyboard,
    expense_details_keyboard,
    expense_friends_keyboard,
    expense_list_keyboard,
    main_menu,
    participant_keyboard,
    remove_participant_keyboard,
    split_method_keyboard,
)
from splitnshare.presentation.labels import friend_label, participant_label
from splitnshare.presentation.states import AddExpenseStates

router = Router(name="expenses")
router.message.filter(F.chat.type == "private")
router.callback_query.filter(F.message.chat.type == "private")


@router.message(F.text.in_(button_values("add_expense")))
async def begin_expense(
    message: Message, state: FSMContext, services: Services, language: Language
) -> None:
    person = await current_person(message, services)
    await state.clear()
    await state.update_data(
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
    if callback.from_user is None:
        return
    target_message = callback_message(callback)
    person = await services.users.find_registered_target(callback.from_user.id)
    if person is None:
        await callback.answer(translate(language, "use_start"), show_alert=True)
        return
    await state.clear()
    await state.update_data(
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
    await state.clear()
    await message.answer(translate(language, "back_main"), reply_markup=main_menu(language))


@router.message(AddExpenseStates.description)
async def receive_description(
    message: Message, state: FSMContext, language: Language
) -> None:
    text = (message.text or "").strip()
    if not 1 <= len(text) <= 240:
        await message.answer(translate(language, "description_invalid"))
        return
    await state.update_data(description=text)
    await state.set_state(AddExpenseStates.total)
    await message.answer(
        translate(language, "enter_total"),
        reply_markup=cancel_keyboard(language),
    )


@router.message(AddExpenseStates.total, F.text.in_(button_values("back")))
async def total_back(message: Message, state: FSMContext, language: Language) -> None:
    await state.set_state(AddExpenseStates.description)
    await message.answer(
        translate(language, "expense_for"),
        reply_markup=cancel_keyboard(language, include_back=False),
    )


@router.message(AddExpenseStates.total)
async def receive_total(
    message: Message, state: FSMContext, services: Services, language: Language
) -> None:
    person = await current_person(message, services)
    settings = await services.user_settings.get_or_create(person.id)
    try:
        total = parse_total(message.text or "", settings.default_currency)
    except DomainError as exc:
        await message.answer(str(exc))
        return
    await state.update_data(total_minor=total.minor, currency=total.currency)
    await state.set_state(AddExpenseStates.participants)
    await message.answer(
        translate(language, "add_people"),
        reply_markup=participant_keyboard(language),
    )


@router.message(AddExpenseStates.participants, F.users_shared)
async def receive_shared_users(
    message: Message, state: FSMContext, services: Services, language: Language
) -> None:
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
        reply_markup=participant_keyboard(language),
    )


@router.message(AddExpenseStates.participants, F.text.in_(button_values("add_manual")))
async def request_manual_name(
    message: Message, state: FSMContext, language: Language
) -> None:
    await state.set_state(AddExpenseStates.manual_name)
    await message.answer(
        translate(language, "guest_name"), reply_markup=cancel_keyboard(language)
    )


@router.message(
    AddExpenseStates.participants,
    F.text.in_(button_values("add_from_friends")),
)
async def choose_friend(
    message: Message, services: Services, language: Language
) -> None:
    owner = await current_person(message, services)
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
        reply_markup=participant_keyboard(settings.language),
    )
    await callback.answer()


@router.message(AddExpenseStates.manual_name, F.text.in_(button_values("back")))
async def manual_back(message: Message, state: FSMContext, language: Language) -> None:
    await state.set_state(AddExpenseStates.participants)
    await message.answer(
        translate(language, "continue_participants"),
        reply_markup=participant_keyboard(language),
    )


@router.message(AddExpenseStates.manual_name)
async def receive_manual_name(
    message: Message, state: FSMContext, services: Services, language: Language
) -> None:
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
        reply_markup=participant_keyboard(language),
    )


@router.message(AddExpenseStates.participants, F.text.in_(button_values("back")))
async def participants_back(
    message: Message, state: FSMContext, language: Language
) -> None:
    await state.set_state(AddExpenseStates.total)
    await message.answer(
        translate(language, "enter_total_again"), reply_markup=cancel_keyboard(language)
    )


@router.message(
    AddExpenseStates.participants,
    F.text.in_(button_values("remove_participant")),
)
async def choose_participant_to_remove(
    message: Message, state: FSMContext, language: Language
) -> None:
    data = await state.get_data()
    participants: list[dict[str, str]] = data["participants"]
    if len(participants) == 1:
        await message.answer(translate(language, "no_participants_remove"))
        return
    await message.answer(
        translate(language, "choose_remove"),
        reply_markup=remove_participant_keyboard(participants, data["creator_id"]),
    )


@router.callback_query(F.data.startswith("expense:remove:"))
async def remove_participant(
    callback: CallbackQuery, state: FSMContext, language: Language
) -> None:
    if await state.get_state() != AddExpenseStates.participants.state:
        await callback.answer(translate(language, "draft_expired"), show_alert=True)
        return
    payload, target_message = callback_payload(callback)
    person_id = payload.rsplit(":", 1)[1]
    data = await state.get_data()
    if person_id == data["creator_id"]:
        await callback.answer(translate(language, "payer_remove"), show_alert=True)
        return
    participants: list[dict[str, str]] = data["participants"]
    updated = [item for item in participants if item["id"] != person_id]
    await state.update_data(participants=updated)
    await target_message.answer(
        _participant_summary(updated, language),
        reply_markup=participant_keyboard(language),
    )
    await callback.answer()


@router.message(AddExpenseStates.participants, F.text.in_(button_values("done")))
async def participants_done(
    message: Message, state: FSMContext, language: Language
) -> None:
    data = await state.get_data()
    participants: list[dict[str, str]] = data["participants"]
    if len(participants) < 2:
        await message.answer(translate(language, "add_one_participant"))
        return
    await message.answer(
        translate(language, "split_how"), reply_markup=split_method_keyboard(language)
    )


@router.callback_query(F.data == "expense:split:equal")
async def choose_equal(
    callback: CallbackQuery, state: FSMContext, language: Language
) -> None:
    target_message = callback_message(callback)
    data = await state.get_data()
    participants: list[dict[str, str]] = data.get("participants", [])
    if len(participants) < 2:
        await callback.answer(translate(language, "draft_expired"), show_alert=True)
        return
    allocations = EqualSplitStrategy().allocate(
        data["total_minor"], [UUID(item["id"]) for item in participants]
    )
    await state.update_data(split_method=SplitMethod.EQUAL.value)
    await state.set_state(AddExpenseStates.confirm)
    await target_message.answer(
        _review_text(
            data,
            participants,
            {str(a.person_id): a.owed_minor for a in allocations},
            language,
        ),
        reply_markup=expense_confirm_keyboard(language),
    )
    await callback.answer()


@router.callback_query(F.data == "expense:split:exact")
async def choose_exact(
    callback: CallbackQuery, state: FSMContext, language: Language
) -> None:
    target_message = callback_message(callback)
    data = await state.get_data()
    participants: list[dict[str, str]] = data.get("participants", [])
    if len(participants) < 2:
        await callback.answer(translate(language, "draft_expired"), show_alert=True)
        return
    await state.update_data(split_method=SplitMethod.EXACT.value, exact_amounts={}, exact_index=0)
    await state.set_state(AddExpenseStates.exact_amount)
    await target_message.answer(
        translate(language, "owes_prompt", name=escape(participants[0]["name"])),
        reply_markup=cancel_keyboard(language),
    )
    await callback.answer()


@router.message(AddExpenseStates.exact_amount, F.text.in_(button_values("back")))
async def exact_back(message: Message, state: FSMContext, language: Language) -> None:
    await state.set_state(AddExpenseStates.participants)
    await message.answer(
        translate(language, "split_again"), reply_markup=participant_keyboard(language)
    )


@router.message(AddExpenseStates.exact_amount)
async def receive_exact_amount(
    message: Message, state: FSMContext, language: Language
) -> None:
    data = await state.get_data()
    participants: list[dict[str, str]] = data["participants"]
    index: int = data["exact_index"]
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
        await message.answer(
            translate(language, "owes_next", name=escape(participants[index]["name"]))
        )
        return
    if sum(exact.values()) != total.minor:
        await state.update_data(exact_amounts={}, exact_index=0)
        await message.answer(
            translate(
                language,
                "shares_mismatch",
                total=total.format(),
                name=escape(participants[0]["name"]),
            )
        )
        return
    await state.set_state(AddExpenseStates.confirm)
    await message.answer(
        _review_text(data, participants, exact, language),
        reply_markup=expense_confirm_keyboard(language),
    )


@router.callback_query(F.data == "expense:confirm")
async def confirm_expense(
    callback: CallbackQuery,
    state: FSMContext,
    services: Services,
    language: Language,
) -> None:
    target_message = callback_message(callback)
    data = await state.get_data()
    if not data or "split_method" not in data:
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
        context=DirectExpenseContext(),
        exact_amounts_minor={UUID(key): value for key, value in exact.items()} if exact else None,
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
        + expense_text(expense, language),
        reply_markup=main_menu(settings.language),
    )
    await callback.answer()


@router.callback_query(F.data == "expense:cancel")
async def cancel_expense_callback(
    callback: CallbackQuery, state: FSMContext, language: Language
) -> None:
    target_message = callback_message(callback)
    await state.clear()
    await target_message.answer(
        translate(language, "cancelled"), reply_markup=main_menu(language)
    )
    await callback.answer()


@router.message(F.text.in_(button_values("transactions")))
async def transactions(
    message: Message, services: Services, language: Language
) -> None:
    person = await current_person(message, services)
    page = await services.expense_queries.list_for_person(person.id)
    if not page.items:
        await message.answer(translate(language, "no_expenses"))
        return
    await message.answer(
        translate(language, "your_transactions"),
        reply_markup=expense_list_keyboard(page, language),
    )


@router.callback_query(F.data == "expense:list")
async def transactions_callback(
    callback: CallbackQuery, services: Services, language: Language
) -> None:
    if callback.from_user is None:
        return
    target_message = callback_message(callback)
    person = await services.users.find_registered_target(callback.from_user.id)
    if person is None:
        await callback.answer(translate(language, "use_start"), show_alert=True)
        return
    page = await services.expense_queries.list_for_person(person.id)
    if page.items:
        await target_message.answer(
            translate(language, "your_transactions"),
            reply_markup=expense_list_keyboard(page, language),
        )
    else:
        await target_message.answer(translate(language, "no_active_expenses"))
    await callback.answer()


@router.callback_query(F.data == "menu:transactions")
async def menu_transactions_callback(
    callback: CallbackQuery, services: Services, language: Language
) -> None:
    if callback.from_user is None:
        return
    target_message = callback_message(callback)
    person = await services.users.find_registered_target(callback.from_user.id)
    if person is None:
        await callback.answer(translate(language, "use_start"), show_alert=True)
        return
    page = await services.expense_queries.list_for_person(person.id)
    await target_message.edit_text(
        translate(
            language,
            "your_transactions" if page.items else "no_active_expenses",
        ),
        reply_markup=(
            expense_list_keyboard(page, language)
            if page.items
            else back_to_main_menu_keyboard(language)
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("expense:page:"))
async def transactions_page(
    callback: CallbackQuery, services: Services, language: Language
) -> None:
    if callback.from_user is None:
        return
    payload, target_message = callback_payload(callback)
    person = await services.users.find_registered_target(callback.from_user.id)
    if person is None:
        await callback.answer(translate(language, "use_start"), show_alert=True)
        return
    cursor = payload.split(":", 2)[2]
    page = await services.expense_queries.list_for_person(person.id, cursor=cursor)
    await target_message.edit_reply_markup(reply_markup=expense_list_keyboard(page, language))
    await callback.answer()


@router.callback_query(F.data.startswith("expense:view:"))
async def view_expense(
    callback: CallbackQuery, services: Services, language: Language
) -> None:
    if callback.from_user is None:
        return
    payload, target_message = callback_payload(callback)
    person = await services.users.find_registered_target(callback.from_user.id)
    if person is None:
        await callback.answer(translate(language, "use_start"), show_alert=True)
        return
    expense_id = UUID(payload.rsplit(":", 1)[1])
    expense = await services.expense_queries.get_details(person.id, expense_id)
    await target_message.answer(
        expense_text(expense, language),
        reply_markup=expense_details_keyboard(expense, person.id, language),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("expense:delete_ask:"))
async def ask_delete(callback: CallbackQuery, language: Language) -> None:
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
    return translate(language, "participants") + "\n" + "\n".join(
        f"• {escape(item['name'])}" for item in participants
    )


def _review_text(
    data: dict[str, Any],
    participants: list[dict[str, str]],
    amounts: dict[str, int],
    language: Language,
) -> str:
    total = Money(int(data["total_minor"]), str(data["currency"]))
    lines = [
        translate(language, "review", description=escape(str(data["description"]))),
        translate(language, "total", total=total.format()),
        translate(language, "paid_you"),
        "",
    ]
    lines.extend(
        f"• {escape(item['name'])}: {Money(amounts[item['id']], total.currency).format()}"
        for item in participants
    )
    return "\n".join(lines)
