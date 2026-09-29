"""Handle inline form navigation and contacts without changing the bottom keyboard."""

from html import escape
from uuid import UUID

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, SharedUser, UsersShared

from splitnshare.application.dto import TransferGuestCommand
from splitnshare.domain.enums import Language
from splitnshare.domain.errors import ValidationError
from splitnshare.presentation.callbacks import uuid_from_token, uuid_token
from splitnshare.presentation.container import Services
from splitnshare.presentation.flow_messages import show
from splitnshare.presentation.formatters import transfer_preview_text
from splitnshare.presentation.helpers import callback_message, current_person
from splitnshare.presentation.i18n import translate
from splitnshare.presentation.keyboards import (
    add_friend_keyboard,
    cancel_keyboard,
    participant_keyboard,
    transfer_confirm_keyboard,
    transfer_target_keyboard,
)
from splitnshare.presentation.routers import balances, groups, people, settings, start
from splitnshare.presentation.states import (
    FriendStates,
    GroupStates,
    SettlementStates,
    TransferGuestStates,
    UserSettingsStates,
)

router = Router(name="inline_navigation")
router.message.filter(F.chat.type == "private")
router.callback_query.filter(F.message.chat.type == "private")


def _input_message(callback: CallbackQuery) -> Message:
    """Adapt a button to a form action while retaining its authenticated human sender."""
    return callback_message(callback).model_copy(update={"from_user": callback.from_user})


def _callback(callback: CallbackQuery, payload: str) -> CallbackQuery:
    """Reuse an existing detail renderer with an explicit navigation destination."""
    return callback.model_copy(update={"data": payload})


async def _members(message: Message, state: FSMContext, language: Language) -> None:
    """Return to the selected group invitees without losing entered preferences."""
    await state.set_state(GroupStates.members)
    data = await state.get_data()
    names = ", ".join(m["name"] for m in data.get("members", [])[-15:])
    await show(
        message,
        translate(language, "group_members_prompt")
        + "\n\n"
        + translate(language, "group_members_selected", names=escape(names)),
        reply_markup=participant_keyboard(language),
    )


async def _contact_parent(message: Message, state: FSMContext, language: Language) -> None:
    """Return from contact instructions to the form's contact-choice screen."""
    step = await state.get_state()
    if step == GroupStates.members.state:
        await _members(message, state, language)
    elif step == FriendStates.choosing.state:
        await show(
            message,
            translate(language, "add_friend_prompt"),
            reply_markup=add_friend_keyboard(language),
        )
    elif step == TransferGuestStates.target.state:
        await show(
            message,
            translate(language, "choose_transfer_target"),
            reply_markup=transfer_target_keyboard(language),
        )
    else:
        raise ValidationError(translate(language, "draft_expired"))


@router.callback_query(F.data == "flow:cancel")
async def cancel_flow(callback: CallbackQuery, state: FSMContext, language: Language) -> None:
    """Cancel the current form while preserving independently stored expense drafts."""
    await start.cancel(_input_message(callback), state, language)
    await callback.answer()


@router.callback_query(F.data == "flow:back")
async def previous_step(
    callback: CallbackQuery,
    state: FSMContext,
    services: Services,
    language: Language,
) -> None:
    """Return to the actual predecessor and discard abandoned selection values."""
    step, data = await state.get_state(), await state.get_data()
    message = _input_message(callback)
    if step == GroupStates.name.state:
        await groups.groups_menu(message, state, services, language)
    elif step == GroupStates.currency.state:
        await state.set_state(GroupStates.name)
        await show(
            message,
            translate(language, "group_name_prompt"),
            reply_markup=cancel_keyboard(language),
        )
    elif step == GroupStates.members.state:
        if data.get("group_id"):
            await groups.group_details(
                _callback(callback, f"g:view:{uuid_token(UUID(data['group_id']))}"),
                state,
                services,
                language,
            )
            return
        await state.set_state(GroupStates.currency)
        await show(
            message,
            translate(language, "group_currency_prompt", currency=data["currency"]),
            reply_markup=cancel_keyboard(language),
        )
    elif step in (GroupStates.manual_name.state, GroupStates.confirm.state):
        await _members(message, state, language)
    elif step == GroupStates.settlement.state:
        group_id = data["group_id"]
        await state.clear()
        await groups.group_subscreen(
            _callback(callback, f"g:settle:{uuid_token(UUID(group_id))}:0"),
            services,
            language,
        )
        return
    elif step == FriendStates.manual_name.state:
        await state.set_state(FriendStates.choosing)
        await _contact_parent(message, state, language)
    elif step == FriendStates.choosing.state:
        await state.clear()
        await people.friends_callback(_callback(callback, "friends:show"), services, language)
        return
    elif step == FriendStates.renaming.state:
        friend_id = data["friend_id"]
        await state.clear()
        await people.view_friend(
            _callback(callback, f"friend:view:{friend_id}"), services, language
        )
        return
    elif step == TransferGuestStates.confirm.state:
        await state.update_data(target_id=None)
        await state.set_state(TransferGuestStates.target)
        await _contact_parent(message, state, language)
    elif step == TransferGuestStates.target.state:
        guest_id = data["guest_id"]
        await state.clear()
        await people.view_friend(_callback(callback, f"friend:view:{guest_id}"), services, language)
        return
    elif step == UserSettingsStates.custom_currency.state:
        await state.clear()
        await settings.choose_currency(_callback(callback, "settings:currency"), language)
        return
    elif step == SettlementStates.amount.state:
        await balances.select_balance_to_settle(
            _callback(callback, f"settle:select:{data['other_id']}:{data['currency']}"),
            state,
            services,
            language,
        )
        return
    else:
        await callback.answer(translate(language, "draft_expired"), show_alert=True)
        return
    await callback.answer()


@router.callback_query(F.data.in_({"flow:contact", "flow:contact_back", "flow:members"}))
async def contact_instructions(
    callback: CallbackQuery,
    state: FSMContext,
    language: Language,
) -> None:
    """Explain contact attachment without invoking Telegram's reply-keyboard picker."""
    step = await state.get_state()
    if step not in (
        GroupStates.members.state,
        FriendStates.choosing.state,
        TransferGuestStates.target.state,
    ):
        await callback.answer(translate(language, "draft_expired"), show_alert=True)
        return
    if callback.data != "flow:contact":
        await _contact_parent(callback_message(callback), state, language)
    else:
        await show(
            callback_message(callback),
            translate(language, "share_contact_hint"),
            reply_markup=groups._keyboard(
                [
                    (translate(language, "back"), "flow:contact_back"),
                    (translate(language, "cancel"), "flow:cancel"),
                ]
            ),
        )
    await callback.answer()


@router.callback_query(F.data.in_({"flow:manual", "flow:friends", "flow:remove", "flow:done"}))
async def form_action(
    callback: CallbackQuery,
    state: FSMContext,
    services: Services,
    language: Language,
) -> None:
    """Dispatch inline actions to the existing authenticated form use cases."""
    step = await state.get_state()
    message = _input_message(callback)
    action = (callback.data or "").split(":")[1]
    if step == GroupStates.members.state:
        if action == "manual":
            await groups.group_manual_prompt(message, state, language)
        elif action == "friends":
            await groups.group_friend_choices(message, state, services, language)
        elif action == "remove":
            await groups.group_remove_choices(message, state, language)
        else:
            await groups.group_review(message, state, language)
    elif step == FriendStates.choosing.state and action == "manual":
        await people.request_friend_name(message, state, language)
    elif step == TransferGuestStates.target.state and action == "friends":
        await _target_friends(message, services, language, 0)
    else:
        await callback.answer(translate(language, "draft_expired"), show_alert=True)
        return
    await callback.answer()


async def _target_friends(
    message: Message,
    services: Services,
    language: Language,
    page: int,
) -> None:
    """List registered friends as transfer candidates with bounded inline pagination."""
    owner = await current_person(message, services)
    friends = [f for f in await services.friends.list_friends(owner.id) if f.registered]
    choices = [
        (f.display_name, f"flow:target:{uuid_token(f.person_id)}")
        for f in friends[page * 20 : (page + 1) * 20]
    ]
    if page:
        choices.append(("←", f"flow:targets:{page - 1}"))
    if len(friends) > (page + 1) * 20:
        choices.append(("→", f"flow:targets:{page + 1}"))
    choices.append((translate(language, "back"), "flow:contact_back"))
    await show(
        message,
        translate(language, "choose_registered" if friends else "no_friends"),
        reply_markup=groups._keyboard(choices),
    )


@router.callback_query(TransferGuestStates.target, F.data.startswith("flow:targets:"))
async def target_page(callback: CallbackQuery, services: Services, language: Language) -> None:
    """Page registered transfer candidates while retaining the target-selection state."""
    await _target_friends(
        _input_message(callback),
        services,
        language,
        max(0, int((callback.data or "").rsplit(":", 1)[1])),
    )
    await callback.answer()


@router.callback_query(TransferGuestStates.target, F.data.startswith("flow:target:"))
async def select_target(
    callback: CallbackQuery,
    state: FSMContext,
    services: Services,
    language: Language,
) -> None:
    """Authorize a registered friend before previewing an identity transfer."""
    owner = await current_person(_input_message(callback), services)
    person_id = uuid_from_token((callback.data or "").rsplit(":", 1)[1])
    friends = await services.friends.list_friends(owner.id)
    if not any(f.person_id == person_id and f.registered for f in friends):
        raise ValidationError(translate(language, "target_not_registered"))
    data = await state.get_data()
    preview = await services.guests.preview_transfer(
        TransferGuestCommand(owner.id, UUID(data["guest_id"]), person_id)
    )
    await state.update_data(target_id=str(person_id))
    await state.set_state(TransferGuestStates.confirm)
    await show(
        callback_message(callback),
        transfer_preview_text(preview, language),
        reply_markup=transfer_confirm_keyboard(language),
    )
    await callback.answer()


@router.message(FriendStates.choosing, F.contact)
@router.message(GroupStates.members, F.contact)
@router.message(TransferGuestStates.target, F.contact)
async def receive_contact(
    message: Message,
    state: FSMContext,
    services: Services,
    language: Language,
) -> None:
    """Adapt Telegram contact attachments to existing participant resolution logic."""
    contact = message.contact
    if contact is None or contact.user_id is None:
        await show(message, translate(language, "contact_requires_telegram_id"))
        return
    shared = UsersShared(
        request_id=1001,
        users=[
            SharedUser(
                user_id=contact.user_id,
                first_name=contact.first_name,
                last_name=contact.last_name,
            )
        ],
    )
    adapted = message.model_copy(update={"users_shared": shared})
    step = await state.get_state()
    if step == FriendStates.choosing.state:
        await people.receive_friend_user(adapted, state, services, language)
    elif step == GroupStates.members.state:
        await groups.group_shared_users(adapted, state, services, language)
    else:
        await people.receive_target(adapted, state, services, language)
