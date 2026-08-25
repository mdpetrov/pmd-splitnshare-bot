from __future__ import annotations

from html import escape
from typing import Any
from uuid import UUID

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from splitnshare.application.dto import CreateExpenseCommand, SharedTelegramUser
from splitnshare.domain.contexts import DirectExpenseContext
from splitnshare.domain.enums import SplitMethod
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
from splitnshare.presentation.keyboards import (
    ADD_EXPENSE,
    ADD_MANUAL,
    ADD_RECENT,
    BACK,
    DONE,
    REMOVE_PARTICIPANT,
    TRANSACTIONS,
    cancel_keyboard,
    delete_confirm_keyboard,
    expense_confirm_keyboard,
    expense_details_keyboard,
    expense_list_keyboard,
    main_menu,
    participant_keyboard,
    recent_people_keyboard,
    remove_participant_keyboard,
    split_method_keyboard,
)
from splitnshare.presentation.states import AddExpenseStates

router = Router(name="expenses")
router.message.filter(F.chat.type == "private")
router.callback_query.filter(F.message.chat.type == "private")


@router.message(F.text == ADD_EXPENSE)
async def begin_expense(message: Message, state: FSMContext, services: Services) -> None:
    person = await current_person(message, services)
    await state.clear()
    await state.update_data(
        creator_id=str(person.id),
        participants=[{"id": str(person.id), "name": person.display_name}],
    )
    await state.set_state(AddExpenseStates.description)
    await message.answer(
        "What is this expense for?", reply_markup=cancel_keyboard(include_back=False)
    )


@router.message(AddExpenseStates.description, F.text == BACK)
async def description_back(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Back at the main menu.", reply_markup=main_menu())


@router.message(AddExpenseStates.description)
async def receive_description(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not 1 <= len(text) <= 240:
        await message.answer("Enter a description between 1 and 240 characters.")
        return
    await state.update_data(description=text)
    await state.set_state(AddExpenseStates.total)
    await message.answer(
        "Enter the total, for example 12.50 or 12.50 USD.",
        reply_markup=cancel_keyboard(),
    )


@router.message(AddExpenseStates.total, F.text == BACK)
async def total_back(message: Message, state: FSMContext) -> None:
    await state.set_state(AddExpenseStates.description)
    await message.answer(
        "What is this expense for?", reply_markup=cancel_keyboard(include_back=False)
    )


@router.message(AddExpenseStates.total)
async def receive_total(message: Message, state: FSMContext, services: Services) -> None:
    try:
        total = parse_total(message.text or "", services.default_currency)
    except DomainError as exc:
        await message.answer(str(exc))
        return
    await state.update_data(total_minor=total.minor, currency=total.currency)
    await state.set_state(AddExpenseStates.participants)
    await message.answer(
        "Add up to nine other people. They may be registered users, Telegram guests, "
        "or named guests.",
        reply_markup=participant_keyboard(),
    )


@router.message(AddExpenseStates.participants, F.users_shared)
async def receive_shared_users(message: Message, state: FSMContext, services: Services) -> None:
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
            participants.append({"id": str(candidate.id), "name": candidate.display_name})
            existing.add(str(candidate.id))
    await state.update_data(participants=participants)
    await message.answer(_participant_summary(participants), reply_markup=participant_keyboard())


@router.message(AddExpenseStates.participants, F.text == ADD_MANUAL)
async def request_manual_name(message: Message, state: FSMContext) -> None:
    await state.set_state(AddExpenseStates.manual_name)
    await message.answer("Enter the guest's display name.", reply_markup=cancel_keyboard())


@router.message(AddExpenseStates.participants, F.text == ADD_RECENT)
async def choose_recent_person(message: Message, services: Services) -> None:
    owner = await current_person(message, services)
    people = list(await services.expense_queries.list_recent_people(owner.id))
    if not people:
        await message.answer("No recent co-participants yet.")
        return
    await message.answer("Choose a recent person:", reply_markup=recent_people_keyboard(people))


@router.callback_query(F.data.startswith("expense:addperson:"))
async def add_recent_person(callback: CallbackQuery, state: FSMContext, services: Services) -> None:
    if await state.get_state() != AddExpenseStates.participants.state:
        await callback.answer("The expense draft expired.", show_alert=True)
        return
    if callback.from_user is None:
        return
    payload, target_message = callback_payload(callback)
    owner = await services.users.find_registered_target(callback.from_user.id)
    if owner is None:
        await callback.answer("Use /start first.", show_alert=True)
        return
    person_id = UUID(payload.rsplit(":", 1)[1])
    recent = {
        person.id: person
        for person in await services.expense_queries.list_recent_people(owner.id)
    }
    person = recent.get(person_id)
    if person is None:
        await callback.answer("That person is no longer available.", show_alert=True)
        return
    data = await state.get_data()
    participants: list[dict[str, str]] = data["participants"]
    if str(person.id) not in {item["id"] for item in participants}:
        if len(participants) >= 10:
            await callback.answer("The ten-participant limit has been reached.", show_alert=True)
            return
        participants.append({"id": str(person.id), "name": person.display_name})
        await state.update_data(participants=participants)
    await target_message.answer(
        _participant_summary(participants), reply_markup=participant_keyboard()
    )
    await callback.answer()


@router.message(AddExpenseStates.manual_name, F.text == BACK)
async def manual_back(message: Message, state: FSMContext) -> None:
    await state.set_state(AddExpenseStates.participants)
    await message.answer("Continue selecting participants.", reply_markup=participant_keyboard())


@router.message(AddExpenseStates.manual_name)
async def receive_manual_name(message: Message, state: FSMContext, services: Services) -> None:
    owner = await current_person(message, services)
    try:
        guest = await services.guests.create_manual_guest(owner.id, message.text or "")
    except DomainError as exc:
        await message.answer(str(exc))
        return
    data = await state.get_data()
    participants: list[dict[str, str]] = data["participants"]
    if len(participants) >= 10:
        await message.answer("The ten-participant limit has been reached.")
    else:
        participants.append({"id": str(guest.id), "name": guest.display_name})
        await state.update_data(participants=participants)
    await state.set_state(AddExpenseStates.participants)
    await message.answer(_participant_summary(participants), reply_markup=participant_keyboard())


@router.message(AddExpenseStates.participants, F.text == BACK)
async def participants_back(message: Message, state: FSMContext) -> None:
    await state.set_state(AddExpenseStates.total)
    await message.answer("Enter the total again.", reply_markup=cancel_keyboard())


@router.message(AddExpenseStates.participants, F.text == REMOVE_PARTICIPANT)
async def choose_participant_to_remove(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    participants: list[dict[str, str]] = data["participants"]
    if len(participants) == 1:
        await message.answer("There are no additional participants to remove.")
        return
    await message.answer(
        "Choose a participant to remove:",
        reply_markup=remove_participant_keyboard(participants, data["creator_id"]),
    )


@router.callback_query(F.data.startswith("expense:remove:"))
async def remove_participant(callback: CallbackQuery, state: FSMContext) -> None:
    if await state.get_state() != AddExpenseStates.participants.state:
        await callback.answer("The expense draft expired.", show_alert=True)
        return
    payload, target_message = callback_payload(callback)
    person_id = payload.rsplit(":", 1)[1]
    data = await state.get_data()
    if person_id == data["creator_id"]:
        await callback.answer("The payer cannot be removed.", show_alert=True)
        return
    participants: list[dict[str, str]] = data["participants"]
    updated = [item for item in participants if item["id"] != person_id]
    await state.update_data(participants=updated)
    await target_message.answer(
        _participant_summary(updated), reply_markup=participant_keyboard()
    )
    await callback.answer()


@router.message(AddExpenseStates.participants, F.text == DONE)
async def participants_done(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    participants: list[dict[str, str]] = data["participants"]
    if len(participants) < 2:
        await message.answer("Add at least one other participant.")
        return
    await message.answer("How should the total be split?", reply_markup=split_method_keyboard())


@router.callback_query(F.data == "expense:split:equal")
async def choose_equal(callback: CallbackQuery, state: FSMContext) -> None:
    target_message = callback_message(callback)
    data = await state.get_data()
    participants: list[dict[str, str]] = data.get("participants", [])
    if len(participants) < 2:
        await callback.answer("The expense draft expired.", show_alert=True)
        return
    allocations = EqualSplitStrategy().allocate(
        data["total_minor"], [UUID(item["id"]) for item in participants]
    )
    await state.update_data(split_method=SplitMethod.EQUAL.value)
    await state.set_state(AddExpenseStates.confirm)
    await target_message.answer(
        _review_text(data, participants, {str(a.person_id): a.owed_minor for a in allocations}),
        reply_markup=expense_confirm_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "expense:split:exact")
async def choose_exact(callback: CallbackQuery, state: FSMContext) -> None:
    target_message = callback_message(callback)
    data = await state.get_data()
    participants: list[dict[str, str]] = data.get("participants", [])
    if len(participants) < 2:
        await callback.answer("The expense draft expired.", show_alert=True)
        return
    await state.update_data(split_method=SplitMethod.EXACT.value, exact_amounts={}, exact_index=0)
    await state.set_state(AddExpenseStates.exact_amount)
    await target_message.answer(
        f"How much does {escape(participants[0]['name'])} owe? Enter 0 if the payer owes nothing.",
        reply_markup=cancel_keyboard(),
    )
    await callback.answer()


@router.message(AddExpenseStates.exact_amount, F.text == BACK)
async def exact_back(message: Message, state: FSMContext) -> None:
    await state.set_state(AddExpenseStates.participants)
    await message.answer("Choose the split again when ready.", reply_markup=participant_keyboard())


@router.message(AddExpenseStates.exact_amount)
async def receive_exact_amount(message: Message, state: FSMContext) -> None:
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
        await message.answer(f"How much does {escape(participants[index]['name'])} owe?")
        return
    if sum(exact.values()) != total.minor:
        await state.update_data(exact_amounts={}, exact_index=0)
        await message.answer(
            f"Those shares do not total {total.format()}. Start again with "
            f"{escape(participants[0]['name'])}."
        )
        return
    await state.set_state(AddExpenseStates.confirm)
    await message.answer(
        _review_text(data, participants, exact),
        reply_markup=expense_confirm_keyboard(),
    )


@router.callback_query(F.data == "expense:confirm")
async def confirm_expense(callback: CallbackQuery, state: FSMContext, services: Services) -> None:
    target_message = callback_message(callback)
    data = await state.get_data()
    if not data or "split_method" not in data:
        await callback.answer("The expense draft expired.", show_alert=True)
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
    await target_message.answer(
        "Expense saved.\n\n" + expense_text(expense), reply_markup=main_menu()
    )
    await callback.answer()


@router.callback_query(F.data == "expense:cancel")
async def cancel_expense_callback(callback: CallbackQuery, state: FSMContext) -> None:
    target_message = callback_message(callback)
    await state.clear()
    await target_message.answer("Cancelled.", reply_markup=main_menu())
    await callback.answer()


@router.message(F.text == TRANSACTIONS)
async def transactions(message: Message, services: Services) -> None:
    person = await current_person(message, services)
    page = await services.expense_queries.list_for_person(person.id)
    if not page.items:
        await message.answer("You do not have any active expenses yet.")
        return
    await message.answer("Your transactions:", reply_markup=expense_list_keyboard(page))


@router.callback_query(F.data == "expense:list")
async def transactions_callback(callback: CallbackQuery, services: Services) -> None:
    if callback.from_user is None:
        return
    target_message = callback_message(callback)
    person = await services.users.find_registered_target(callback.from_user.id)
    if person is None:
        await callback.answer("Use /start first.", show_alert=True)
        return
    page = await services.expense_queries.list_for_person(person.id)
    if page.items:
        await target_message.answer(
            "Your transactions:", reply_markup=expense_list_keyboard(page)
        )
    else:
        await target_message.answer("You do not have any active expenses.")
    await callback.answer()


@router.callback_query(F.data.startswith("expense:page:"))
async def transactions_page(callback: CallbackQuery, services: Services) -> None:
    if callback.from_user is None:
        return
    payload, target_message = callback_payload(callback)
    person = await services.users.find_registered_target(callback.from_user.id)
    if person is None:
        await callback.answer("Use /start first.", show_alert=True)
        return
    cursor = payload.split(":", 2)[2]
    page = await services.expense_queries.list_for_person(person.id, cursor=cursor)
    await target_message.edit_reply_markup(reply_markup=expense_list_keyboard(page))
    await callback.answer()


@router.callback_query(F.data.startswith("expense:view:"))
async def view_expense(callback: CallbackQuery, services: Services) -> None:
    if callback.from_user is None:
        return
    payload, target_message = callback_payload(callback)
    person = await services.users.find_registered_target(callback.from_user.id)
    if person is None:
        await callback.answer("Use /start first.", show_alert=True)
        return
    expense_id = UUID(payload.rsplit(":", 1)[1])
    expense = await services.expense_queries.get_details(person.id, expense_id)
    await target_message.answer(
        expense_text(expense), reply_markup=expense_details_keyboard(expense, person.id)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("expense:delete_ask:"))
async def ask_delete(callback: CallbackQuery) -> None:
    payload, target_message = callback_payload(callback)
    expense_id = UUID(payload.rsplit(":", 1)[1])
    await target_message.answer(
        "Delete this expense from active history and balances?",
        reply_markup=delete_confirm_keyboard(expense_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("expense:delete:"))
async def delete_expense(callback: CallbackQuery, services: Services) -> None:
    if callback.from_user is None:
        return
    payload, target_message = callback_payload(callback)
    person = await services.users.find_registered_target(callback.from_user.id)
    if person is None:
        await callback.answer("Use /start first.", show_alert=True)
        return
    expense_id = UUID(payload.rsplit(":", 1)[1])
    try:
        changed = await services.expenses.delete(person.id, expense_id)
    except DomainError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    await target_message.edit_text(
        "Expense deleted." if changed else "Expense was already deleted."
    )
    await callback.answer()


def _participant_summary(participants: list[dict[str, str]]) -> str:
    return "Participants:\n" + "\n".join(
        f"• {escape(item['name'])}" for item in participants
    )


def _review_text(
    data: dict[str, Any], participants: list[dict[str, str]], amounts: dict[str, int]
) -> str:
    total = Money(int(data["total_minor"]), str(data["currency"]))
    lines = [
        f"Review <b>{escape(str(data['description']))}</b>",
        f"Total: {total.format()}",
        "Paid by: you",
        "",
    ]
    lines.extend(
        f"• {escape(item['name'])}: {Money(amounts[item['id']], total.currency).format()}"
        for item in participants
    )
    return "\n".join(lines)
