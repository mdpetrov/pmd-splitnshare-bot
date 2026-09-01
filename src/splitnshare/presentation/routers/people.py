from html import escape
from uuid import UUID

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from splitnshare.application.dto import FriendDTO, SharedTelegramUser, TransferGuestCommand
from splitnshare.domain.enums import Language
from splitnshare.domain.errors import DomainError
from splitnshare.presentation.container import Services
from splitnshare.presentation.formatters import transfer_preview_text
from splitnshare.presentation.helpers import callback_message, callback_payload, current_person
from splitnshare.presentation.i18n import button_values, translate
from splitnshare.presentation.keyboards import (
    add_friend_keyboard,
    back_to_friends_keyboard,
    cancel_keyboard,
    friends_menu_keyboard,
    guests_keyboard,
    main_menu,
    transfer_confirm_keyboard,
    transfer_target_keyboard,
)
from splitnshare.presentation.states import FriendStates, TransferGuestStates

router = Router(name="friends")
router.message.filter(F.chat.type == "private")
router.callback_query.filter(F.message.chat.type == "private")


@router.message(F.text.in_(button_values("friends")))
async def friends(message: Message, services: Services, language: Language) -> None:
    owner = await current_person(message, services)
    friendships = tuple(await services.friends.list_friends(owner.id))
    guests = tuple(await services.guests.list_owned_guests(owner.id))
    await message.answer(
        _friends_text(friendships, len(guests), language),
        reply_markup=friends_menu_keyboard(language),
    )


@router.callback_query(F.data == "friends:show")
async def friends_callback(
    callback: CallbackQuery, services: Services, language: Language
) -> None:
    if callback.from_user is None:
        return
    target_message = callback_message(callback)
    owner = await services.users.find_registered_target(callback.from_user.id)
    if owner is None:
        await callback.answer(translate(language, "use_start"), show_alert=True)
        return
    friendships = tuple(await services.friends.list_friends(owner.id))
    guests = tuple(await services.guests.list_owned_guests(owner.id))
    await target_message.edit_text(
        _friends_text(friendships, len(guests), language),
        reply_markup=friends_menu_keyboard(language),
    )
    await callback.answer()


@router.callback_query(F.data == "friends:registered")
async def registered_friends(
    callback: CallbackQuery, services: Services, language: Language
) -> None:
    if callback.from_user is None:
        return
    target_message = callback_message(callback)
    owner = await services.users.find_registered_target(callback.from_user.id)
    if owner is None:
        await callback.answer(translate(language, "use_start"), show_alert=True)
        return
    registered = [
        friend
        for friend in await services.friends.list_friends(owner.id)
        if friend.registered
    ]
    if registered:
        lines = [translate(language, "registered_friends_intro")]
        lines.extend(
            f"• {escape(friend.display_name)}"
            + (f" (@{escape(friend.username)})" if friend.username else "")
            for friend in registered
        )
        text = "\n".join(lines)
    else:
        text = translate(language, "no_registered_friends")
    await target_message.edit_text(
        text, reply_markup=back_to_friends_keyboard(language)
    )
    await callback.answer()


@router.callback_query(F.data == "friends:guests")
async def owned_guests(
    callback: CallbackQuery, services: Services, language: Language
) -> None:
    if callback.from_user is None:
        return
    target_message = callback_message(callback)
    owner = await services.users.find_registered_target(callback.from_user.id)
    if owner is None:
        await callback.answer(translate(language, "use_start"), show_alert=True)
        return
    guests = tuple(await services.guests.list_owned_guests(owner.id))
    text = (
        translate(language, "guests_intro")
        if guests
        else translate(language, "no_guests")
    )
    await target_message.edit_text(
        text, reply_markup=guests_keyboard(guests, language)
    )
    await callback.answer()


@router.callback_query(F.data == "friends:add")
async def begin_add_friend(
    callback: CallbackQuery, state: FSMContext, language: Language
) -> None:
    target_message = callback_message(callback)
    await state.clear()
    await state.set_state(FriendStates.choosing)
    await target_message.answer(
        translate(language, "add_friend_prompt"),
        reply_markup=add_friend_keyboard(language),
    )
    await callback.answer()


@router.message(FriendStates.choosing, F.users_shared)
async def receive_friend_user(
    message: Message,
    state: FSMContext,
    services: Services,
    language: Language,
) -> None:
    if message.users_shared is None or not message.users_shared.users:
        return
    owner = await current_person(message, services)
    shared = message.users_shared.users[0]
    first_name = getattr(shared, "first_name", None) or f"Telegram user {shared.user_id}"
    try:
        friend = await services.friends.add_shared_user(
            owner.id,
            SharedTelegramUser(
                telegram_user_id=shared.user_id,
                first_name=first_name,
                last_name=getattr(shared, "last_name", None),
                username=getattr(shared, "username", None),
            ),
        )
    except DomainError as exc:
        await message.answer(str(exc))
        return
    await state.clear()
    await message.answer(
        translate(language, "friend_added", name=escape(friend.display_name)),
        reply_markup=main_menu(language),
    )


@router.message(FriendStates.choosing, F.text.in_(button_values("add_named_guest")))
async def request_friend_name(
    message: Message, state: FSMContext, language: Language
) -> None:
    await state.set_state(FriendStates.manual_name)
    await message.answer(
        translate(language, "friend_name"), reply_markup=cancel_keyboard(language)
    )


@router.message(FriendStates.choosing, F.text.in_(button_values("back")))
@router.message(FriendStates.manual_name, F.text.in_(button_values("back")))
async def add_friend_back(
    message: Message, state: FSMContext, services: Services, language: Language
) -> None:
    await state.clear()
    owner = await current_person(message, services)
    friendships = tuple(await services.friends.list_friends(owner.id))
    guests = tuple(await services.guests.list_owned_guests(owner.id))
    await message.answer(
        _friends_text(friendships, len(guests), language),
        reply_markup=main_menu(language),
    )


@router.message(FriendStates.manual_name)
async def receive_friend_name(
    message: Message,
    state: FSMContext,
    services: Services,
    language: Language,
) -> None:
    owner = await current_person(message, services)
    try:
        friend = await services.friends.add_manual_guest(owner.id, message.text or "")
    except DomainError as exc:
        await message.answer(str(exc))
        return
    await state.clear()
    await message.answer(
        translate(language, "friend_added", name=escape(friend.display_name)),
        reply_markup=main_menu(language),
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


def _friends_text(
    friendships: tuple[FriendDTO, ...], guest_count: int, language: Language
) -> str:
    registered_count = sum(friend.registered for friend in friendships)
    return translate(
        language,
        "friends_title",
        registered=registered_count,
        guests=guest_count,
    )
