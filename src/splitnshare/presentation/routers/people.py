"""Handle unified friends, aliases, removal, and explicit guest transfers."""

from asyncio import gather
from collections.abc import Sequence
from uuid import UUID

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from splitnshare.application.dto import (
    BalanceDTO,
    FriendDTO,
    GuestDTO,
    SharedTelegramUser,
    TransferGuestCommand,
)
from splitnshare.domain.enums import Language
from splitnshare.domain.errors import DomainError
from splitnshare.domain.money import Money
from splitnshare.presentation.container import Services
from splitnshare.presentation.formatters import transfer_preview_text
from splitnshare.presentation.helpers import callback_message, callback_payload, current_person
from splitnshare.presentation.i18n import button_values, translate
from splitnshare.presentation.keyboards import (
    add_friend_keyboard,
    back_to_friends_keyboard,
    cancel_keyboard,
    friend_detail_keyboard,
    friend_remove_confirm_keyboard,
    friends_list_keyboard,
    guests_keyboard,
    main_menu,
    registered_friends_keyboard,
    transfer_confirm_keyboard,
    transfer_target_keyboard,
)
from splitnshare.presentation.labels import friend_html, participant_html
from splitnshare.presentation.states import FriendStates, TransferGuestStates

router = Router(name="friends")
router.message.filter(F.chat.type == "private")
router.callback_query.filter(F.message.chat.type == "private")


@router.message(F.text.in_(button_values("friends")))
async def friends(message: Message, services: Services, language: Language) -> None:
    """Show the user's unified registered and guest friends list."""
    owner = await current_person(message, services)
    friendships = tuple(await services.friends.list_friends(owner.id))
    await message.answer(
        _friends_text(friendships, language),
        reply_markup=friends_list_keyboard(friendships, language),
    )


@router.callback_query(F.data == "friends:show")
@router.callback_query(F.data == "menu:friends")
async def friends_callback(
    callback: CallbackQuery, services: Services, language: Language
) -> None:
    """Replace the current message with the unified friends list."""
    if callback.from_user is None:
        return
    target_message = callback_message(callback)
    owner = await services.users.find_registered_target(callback.from_user.id)
    if owner is None:
        await callback.answer(translate(language, "use_start"), show_alert=True)
        return
    friendships = tuple(await services.friends.list_friends(owner.id))
    await target_message.edit_text(
        _friends_text(friendships, language),
        reply_markup=friends_list_keyboard(friendships, language),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("friend:view:"))
async def view_friend(
    callback: CallbackQuery, services: Services, language: Language
) -> None:
    """Show details and available actions for one active friend."""
    if callback.from_user is None:
        return
    payload, target_message = callback_payload(callback)
    owner = await services.users.find_registered_target(callback.from_user.id)
    if owner is None:
        await callback.answer(translate(language, "use_start"), show_alert=True)
        return
    friend_id = UUID(payload.rsplit(":", 1)[1])
    available = {
        friend.person_id: friend
        for friend in await services.friends.list_friends(owner.id)
    }
    friend = available.get(friend_id)
    if friend is None:
        await callback.answer(
            translate(language, "friend_already_removed"), show_alert=True
        )
        return
    transfer_guest = None
    if not friend.registered:
        transfer_guest = next(
            (
                guest
                for guest in await services.guests.list_owned_guests(owner.id)
                if guest.person_id == friend.person_id
            ),
            None,
        )
    transaction_count, balances = await gather(
        services.expense_queries.count_shared(owner.id, friend.person_id),
        services.balances.get_balances(owner.id),
    )
    friend_balances = tuple(
        balance for balance in balances if balance.other_person_id == friend.person_id
    )
    await target_message.edit_text(
        _friend_details_text(
            friend,
            transfer_guest,
            language,
            transaction_count,
            friend_balances,
        ),
        reply_markup=friend_detail_keyboard(friend, language, transfer_guest),
    )
    await callback.answer()


@router.callback_query(F.data == "friends:registered")
async def registered_friends(
    callback: CallbackQuery, services: Services, language: Language
) -> None:
    """Show the legacy filtered list of registered friends."""
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
    text = _registered_friends_text(registered, language)
    await target_message.edit_text(
        text, reply_markup=registered_friends_keyboard(registered, language)
    )
    await callback.answer()


@router.callback_query(F.data == "friends:guests")
async def owned_guests(
    callback: CallbackQuery, services: Services, language: Language
) -> None:
    """Show the legacy filtered list of active guest friends."""
    if callback.from_user is None:
        return
    target_message = callback_message(callback)
    owner = await services.users.find_registered_target(callback.from_user.id)
    if owner is None:
        await callback.answer(translate(language, "use_start"), show_alert=True)
        return
    guests = tuple(await services.guests.list_owned_guests(owner.id))
    active_friend_ids = {
        friend.person_id for friend in await services.friends.list_friends(owner.id)
    }
    text = _guests_text(guests, language)
    await target_message.edit_text(
        text,
        reply_markup=guests_keyboard(guests, language, active_friend_ids),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("friend:remove_ask:"))
async def ask_remove_friend(
    callback: CallbackQuery, services: Services, language: Language
) -> None:
    """Validate a friend selection and request removal confirmation."""
    if callback.from_user is None:
        return
    payload, target_message = callback_payload(callback)
    _, _, origin, friend_id_text = payload.split(":", 3)
    owner = await services.users.find_registered_target(callback.from_user.id)
    if owner is None:
        await callback.answer(translate(language, "use_start"), show_alert=True)
        return
    friend_id = UUID(friend_id_text)
    available = {
        friend.person_id: friend
        for friend in await services.friends.list_friends(owner.id)
    }
    friend = available.get(friend_id)
    if friend is None:
        await callback.answer(
            translate(language, "friend_already_removed"), show_alert=True
        )
        return
    text = "\n\n".join(
        (
            translate(
                language,
                "remove_friend_question",
                name=friend_html(friend),
            ),
            translate(language, "remove_friend_warning"),
        )
    )
    await target_message.edit_text(
        text,
        reply_markup=friend_remove_confirm_keyboard(friend.person_id, origin, language),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("friend:remove:"))
async def remove_friend(
    callback: CallbackQuery, services: Services, language: Language
) -> None:
    """Archive a friendship and return to its originating list."""
    if callback.from_user is None:
        return
    payload, target_message = callback_payload(callback)
    _, _, _, friend_id_text = payload.split(":", 3)
    owner = await services.users.find_registered_target(callback.from_user.id)
    if owner is None:
        await callback.answer(translate(language, "use_start"), show_alert=True)
        return
    friend_id = UUID(friend_id_text)
    available = {
        friend.person_id: friend
        for friend in await services.friends.list_friends(owner.id)
    }
    friend = available.get(friend_id)
    changed = await services.friends.remove_friend(owner.id, friend_id)
    if not changed or friend is None:
        text = translate(language, "friend_already_removed")
    else:
        text = translate(
            language,
            "friend_removed",
            name=friend_html(friend),
        )
    await target_message.edit_text(
        text, reply_markup=back_to_friends_keyboard(language)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("friend:rename:"))
async def begin_rename_friend(
    callback: CallbackQuery,
    state: FSMContext,
    services: Services,
    language: Language,
) -> None:
    """Store the selected friend and prompt for a private alias."""
    if callback.from_user is None:
        return
    payload, target_message = callback_payload(callback)
    owner = await services.users.find_registered_target(callback.from_user.id)
    if owner is None:
        await callback.answer(translate(language, "use_start"), show_alert=True)
        return
    friend_id = UUID(payload.rsplit(":", 1)[1])
    available_ids = {
        friend.person_id for friend in await services.friends.list_friends(owner.id)
    }
    if friend_id not in available_ids:
        await callback.answer(
            translate(language, "friend_already_removed"), show_alert=True
        )
        return
    await state.clear()
    await state.update_data(friend_id=str(friend_id))
    await state.set_state(FriendStates.renaming)
    await target_message.answer(
        translate(language, "rename_friend_prompt"),
        reply_markup=cancel_keyboard(language),
    )
    await callback.answer()


@router.message(FriendStates.renaming, F.text.in_(button_values("back")))
async def rename_friend_back(
    message: Message, state: FSMContext, services: Services, language: Language
) -> None:
    """Cancel alias entry and restore the selected friend's details."""
    await state.clear()
    owner = await current_person(message, services)
    friendships = tuple(await services.friends.list_friends(owner.id))
    await message.answer(translate(language, "friends"), reply_markup=main_menu(language))
    await message.answer(
        _friends_text(friendships, language),
        reply_markup=friends_list_keyboard(friendships, language),
    )


@router.message(FriendStates.renaming)
async def rename_friend(
    message: Message,
    state: FSMContext,
    services: Services,
    language: Language,
) -> None:
    """Validate and save a private friend alias from text input."""
    owner = await current_person(message, services)
    data = await state.get_data()
    friend_id_text = data.get("friend_id")
    if not isinstance(friend_id_text, str):
        await state.clear()
        await message.answer(
            translate(language, "friend_already_removed"),
            reply_markup=main_menu(language),
        )
        return
    try:
        renamed = await services.friends.rename_friend(
            owner.id, UUID(friend_id_text), message.text or ""
        )
    except DomainError as exc:
        await message.answer(str(exc))
        return
    await state.clear()
    friendships = tuple(await services.friends.list_friends(owner.id))
    await message.answer(
        translate(language, "friend_renamed", name=friend_html(renamed)),
        reply_markup=main_menu(language),
    )
    await message.answer(
        _friends_text(friendships, language),
        reply_markup=friends_list_keyboard(friendships, language),
    )


@router.callback_query(F.data == "friends:add")
async def begin_add_friend(
    callback: CallbackQuery, state: FSMContext, language: Language
) -> None:
    """Start the flow for adding a Telegram or manually named friend."""
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
    """Add a friend from Telegram's shared-user picker response."""
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
        translate(
            language,
            "friend_added",
            name=friend_html(friend),
        ),
        reply_markup=main_menu(language),
    )


@router.message(FriendStates.choosing, F.text.in_(button_values("add_named_guest")))
async def request_friend_name(
    message: Message, state: FSMContext, language: Language
) -> None:
    """Prompt for the display name of a manually created guest friend."""
    await state.set_state(FriendStates.manual_name)
    await message.answer(
        translate(language, "friend_name"), reply_markup=cancel_keyboard(language)
    )


@router.message(FriendStates.choosing, F.text.in_(button_values("back")))
@router.message(FriendStates.manual_name, F.text.in_(button_values("back")))
async def add_friend_back(
    message: Message, state: FSMContext, services: Services, language: Language
) -> None:
    """Cancel friend creation and restore the unified friend list."""
    await state.clear()
    owner = await current_person(message, services)
    friendships = tuple(await services.friends.list_friends(owner.id))
    await message.answer(translate(language, "friends"), reply_markup=main_menu(language))
    await message.answer(
        _friends_text(friendships, language),
        reply_markup=friends_list_keyboard(friendships, language),
    )


@router.message(FriendStates.manual_name)
async def receive_friend_name(
    message: Message,
    state: FSMContext,
    services: Services,
    language: Language,
) -> None:
    """Create and display a manually named guest friend."""
    owner = await current_person(message, services)
    try:
        friend = await services.friends.add_manual_guest(owner.id, message.text or "")
    except DomainError as exc:
        await message.answer(str(exc))
        return
    await state.clear()
    await message.answer(
        translate(
            language,
            "friend_added",
            name=friend_html(friend),
        ),
        reply_markup=main_menu(language),
    )


@router.callback_query(F.data.startswith("guest:transfer_hint:"))
async def choose_suggested_transfer(
    callback: CallbackQuery,
    state: FSMContext,
    services: Services,
    language: Language,
) -> None:
    """Prepare a transfer using a guest's newly registered suggestion."""
    if callback.from_user is None:
        return
    payload, target_message = callback_payload(callback)
    owner = await services.users.find_registered_target(callback.from_user.id)
    if owner is None:
        await callback.answer(translate(language, "use_start"), show_alert=True)
        return
    guest_id = UUID(payload.rsplit(":", 1)[1])
    owned_guests = {
        guest.person_id: guest
        for guest in await services.guests.list_owned_guests(owner.id)
    }
    guest = owned_guests.get(guest_id)
    if guest is None or guest.suggested_target_person_id is None:
        await callback.answer(
            translate(language, "registration_suggestion_unavailable"),
            show_alert=True,
        )
        return
    command = TransferGuestCommand(
        actor_person_id=owner.id,
        guest_person_id=guest.person_id,
        target_user_person_id=guest.suggested_target_person_id,
    )
    try:
        preview = await services.guests.preview_transfer(command)
    except DomainError as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    await state.clear()
    await state.update_data(
        owner_id=str(owner.id),
        guest_id=str(guest.person_id),
        target_id=str(guest.suggested_target_person_id),
    )
    await state.set_state(TransferGuestStates.confirm)
    await target_message.answer(
        transfer_preview_text(preview, language),
        reply_markup=transfer_confirm_keyboard(language),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("guest:transfer:"))
async def choose_guest(
    callback: CallbackQuery,
    state: FSMContext,
    services: Services,
    language: Language,
) -> None:
    """Select an active guest and request a registered transfer target."""
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
    """Resolve a shared registered target and show the transfer preview."""
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
    """Commit the confirmed guest transfer and notify its target."""
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
            name=participant_html(
                result.target_name, result.target_person_id, result.target_username
            ),
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
    """Clear the transfer draft and report cancellation."""
    target_message = callback_message(callback)
    await state.clear()
    await target_message.answer(
        translate(language, "transfer_cancelled"), reply_markup=main_menu(language)
    )
    await callback.answer()


def _friends_text(friendships: tuple[FriendDTO, ...], language: Language) -> str:
    """Render the unified friends list and registration state."""
    lines = [translate(language, "friends_list_title")]
    if not friendships:
        lines.extend(("", translate(language, "no_friends")))
        return "\n".join(lines)
    lines.append("")
    lines.extend(f"• {friend_html(friend)}" for friend in friendships)
    return "\n".join(lines)


def _friend_details_text(
    friend: FriendDTO,
    transfer_guest: GuestDTO | None,
    language: Language,
    transaction_count: int = 0,
    balances: Sequence[BalanceDTO] = (),
) -> str:
    """Render friend status, financial summary, and transfer guidance."""
    lines = [
        translate(
            language,
            "friend_details",
            name=friend_html(friend),
            status=translate(
                language,
                "friend_registered" if friend.registered else "friend_unregistered",
            ),
        ),
        "",
        translate(
            language,
            "friend_transaction_count",
            count=transaction_count,
        ),
        translate(language, "friend_total_balance"),
    ]
    if balances:
        lines.extend(
            translate(
                language,
                "balance_you_owe_amount"
                if balance.net_minor < 0
                else "balance_you_are_owed_amount",
                amount=Money(abs(balance.net_minor), balance.currency).format(),
            )
            for balance in balances
        )
    else:
        lines.append(translate(language, "friend_no_balance"))
    if transfer_guest is None:
        return "\n".join(lines)
    lines.extend(("", translate(language, "transfer_explanation")))
    if (
        transfer_guest.suggested_target_person_id is not None
        and transfer_guest.suggested_target_name is not None
    ):
        lines.extend(
            (
                "",
                translate(
                    language,
                    "registration_suggestion",
                    target=participant_html(
                        transfer_guest.suggested_target_name,
                        transfer_guest.suggested_target_person_id,
                        transfer_guest.suggested_target_username,
                    ),
                ),
            )
        )
    return "\n".join(lines)


def _registered_friends_text(
    friends: list[FriendDTO] | tuple[FriendDTO, ...], language: Language
) -> str:
    """Render the legacy registered-only friends listing."""
    if not friends:
        return translate(language, "no_registered_friends")
    lines = [translate(language, "registered_friends_intro")]
    lines.extend(
        f"• {friend_html(friend)}"
        for friend in friends
    )
    return "\n".join(lines)


def _guests_text(guests: tuple[GuestDTO, ...], language: Language) -> str:
    """Render active guests with transfer explanation and suggestions."""
    lines = [
        translate(language, "guests_intro"),
        "",
        translate(language, "transfer_explanation"),
    ]
    if not guests:
        lines.extend(("", translate(language, "no_guests")))
        return "\n".join(lines)
    for guest in guests:
        lines.extend(
            (
                "",
                f"• {participant_html(guest.display_name, guest.person_id, guest.username)}",
            )
        )
        if (
            guest.suggested_target_person_id is not None
            and guest.suggested_target_name is not None
        ):
            lines.append(
                translate(
                    language,
                    "registration_suggestion",
                    target=participant_html(
                        guest.suggested_target_name,
                        guest.suggested_target_person_id,
                        guest.suggested_target_username,
                    ),
                )
            )
    return "\n".join(lines)
