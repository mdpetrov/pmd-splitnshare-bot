from html import escape
from uuid import UUID

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from splitnshare.application.dto import TransferGuestCommand
from splitnshare.domain.enums import Language
from splitnshare.domain.errors import DomainError
from splitnshare.presentation.container import Services
from splitnshare.presentation.formatters import transfer_preview_text
from splitnshare.presentation.helpers import callback_message, callback_payload, current_person
from splitnshare.presentation.i18n import button_values, translate
from splitnshare.presentation.keyboards import (
    guests_keyboard,
    main_menu,
    transfer_confirm_keyboard,
    transfer_target_keyboard,
)
from splitnshare.presentation.states import TransferGuestStates

router = Router(name="people")
router.message.filter(F.chat.type == "private")
router.callback_query.filter(F.message.chat.type == "private")


@router.message(F.text.in_(button_values("people")))
async def people(message: Message, services: Services, language: Language) -> None:
    owner = await current_person(message, services)
    guests = tuple(await services.guests.list_owned_guests(owner.id))
    if not guests:
        await message.answer(
            translate(language, "no_guests")
        )
        return
    await message.answer(
        translate(language, "guests_intro"),
        reply_markup=guests_keyboard(guests, language),
    )


@router.callback_query(F.data.startswith("guest:transfer:"))
async def choose_guest(
    callback: CallbackQuery,
    state: FSMContext,
    services: Services,
    language: Language,
) -> None:
    if callback.from_user is None:
        return
    payload, target_message = callback_payload(callback)
    owner = await services.users.find_registered_target(callback.from_user.id)
    if owner is None:
        await callback.answer(translate(language, "use_start"), show_alert=True)
        return
    guest_id = UUID(payload.rsplit(":", 1)[1])
    await state.clear()
    await state.update_data(owner_id=str(owner.id), guest_id=str(guest_id))
    await state.set_state(TransferGuestStates.target)
    await target_message.answer(
        translate(language, "choose_transfer_target"),
        reply_markup=transfer_target_keyboard(language),
    )
    await callback.answer()


@router.message(TransferGuestStates.target, F.users_shared)
async def receive_target(
    message: Message,
    state: FSMContext,
    services: Services,
    language: Language,
) -> None:
    if message.users_shared is None or not message.users_shared.users:
        return
    data = await state.get_data()
    shared = message.users_shared.users[0]
    target = await services.users.find_registered_target(shared.user_id)
    if target is None:
        await message.answer(
            translate(language, "target_not_registered")
        )
        return
    command = TransferGuestCommand(
        actor_person_id=UUID(data["owner_id"]),
        guest_person_id=UUID(data["guest_id"]),
        target_user_person_id=target.id,
    )
    try:
        preview = await services.guests.preview_transfer(command)
    except DomainError as exc:
        await message.answer(str(exc), reply_markup=main_menu(language))
        await state.clear()
        return
    await state.update_data(target_id=str(target.id))
    await state.set_state(TransferGuestStates.confirm)
    await message.answer(
        transfer_preview_text(preview, language),
        reply_markup=transfer_confirm_keyboard(language),
    )


@router.callback_query(F.data == "guest:confirm")
async def confirm_transfer(
    callback: CallbackQuery,
    state: FSMContext,
    services: Services,
    bot: Bot,
    language: Language,
) -> None:
    target_message = callback_message(callback)
    data = await state.get_data()
    if "target_id" not in data:
        await callback.answer(translate(language, "transfer_expired"), show_alert=True)
        return
    command = TransferGuestCommand(
        actor_person_id=UUID(data["owner_id"]),
        guest_person_id=UUID(data["guest_id"]),
        target_user_person_id=UUID(data["target_id"]),
    )
    try:
        result = await services.guests.transfer_guest(command)
    except DomainError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    await state.clear()
    await target_message.answer(
        translate(
            language,
            "transfer_completed",
            expenses=result.affected_counts["expenses"],
            groups=result.affected_counts["group_memberships"],
            name=escape(result.target_name),
        ),
        reply_markup=main_menu(language),
    )
    try:
        target_settings = await services.user_settings.find_by_telegram_id(
            result.target_telegram_user_id
        )
        target_language = (
            target_settings.language if target_settings is not None else Language.ENGLISH
        )
        await bot.send_message(
            result.target_telegram_user_id,
            translate(target_language, "transfer_notification"),
        )
    except (TelegramForbiddenError, TelegramBadRequest):
        # The transfer is authoritative; notification delivery is best effort.
        pass
    await callback.answer()


@router.callback_query(F.data == "guest:cancel")
async def cancel_transfer(
    callback: CallbackQuery, state: FSMContext, language: Language
) -> None:
    target_message = callback_message(callback)
    await state.clear()
    await target_message.answer(
        translate(language, "transfer_cancelled"), reply_markup=main_menu(language)
    )
    await callback.answer()
