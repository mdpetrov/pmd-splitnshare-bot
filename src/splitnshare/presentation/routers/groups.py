"""Provide private-chat group creation, membership, summary, and settlement screens."""

from html import escape
from uuid import UUID, uuid4

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from splitnshare.application.dto import BalanceDTO, GroupDTO, PersonDTO, SharedTelegramUser
from splitnshare.domain.currencies import normalize_currency
from splitnshare.domain.enums import Language
from splitnshare.domain.errors import PermissionDeniedError, ValidationError
from splitnshare.domain.money import Money
from splitnshare.presentation.callbacks import uuid_from_token, uuid_token
from splitnshare.presentation.container import Services
from splitnshare.presentation.flow_messages import show
from splitnshare.presentation.helpers import callback_message, current_person
from splitnshare.presentation.i18n import button_values, translate
from splitnshare.presentation.keyboards import cancel_keyboard, main_menu, participant_keyboard
from splitnshare.presentation.labels import participant_label
from splitnshare.presentation.routers.balances import _notify_settlement_counterparty
from splitnshare.presentation.states import AddExpenseStates, GroupStates

router = Router(name="groups")
router.message.filter(F.chat.type == "private")
router.callback_query.filter(F.message.chat.type == "private")


def _keyboard(choices: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    """Build two-column group controls with a visible icon on every action."""
    icons = {
        "g:view:": "👥", "g:new": "➕", "menu:show": "🏠",
        "g:expense:": "🧾", "g:summary:": "📊", "g:members:": "👥",
        "g:settle:": "💸", "g:invite:": "➕", "g:pay:": "💸",
        "g:paid:": "✅", "menu:groups": "↩️", "g:list:": "➡️",
    }
    buttons = [
        InlineKeyboardButton(
            text=(
                label if label.startswith(("🏠", "👥", "➕", "🧾", "📊", "💸", "✅", "↩️", "➡️"))
                else f"{next((icon for prefix, icon in icons.items() if payload.startswith(prefix)), '🔹')} {label}"
            )[:80],
            callback_data=payload,
        )
        for label, payload in choices
    ]
    return InlineKeyboardMarkup(inline_keyboard=[buttons[i:i + 2] for i in range(0, len(buttons), 2)])


async def _actor(callback: CallbackQuery, services: Services) -> PersonDTO:
    """Resolve the authenticated callback sender."""
    person = await services.users.find_registered_target(callback.from_user.id)
    if person is None:
        raise PermissionDeniedError("Use /start before opening groups.")
    return person


def _member(person: PersonDTO) -> dict[str, str]:
    """Serialize a participant label into persistent conversation data."""
    return {
        "id": str(person.id),
        "name": participant_label(person.display_name, person.id, person.username),
    }


def _details(group: GroupDTO, language: Language) -> str:
    """Render the group header without exposing unescaped user text."""
    return translate(language, "group_details", name=escape(group.name),
                     currency=group.default_currency, count=len(group.participants))


def _actions(group: GroupDTO, actor_id: UUID, language: Language) -> InlineKeyboardMarkup:
    """Offer group operations with owner-only invitations."""
    token = uuid_token(group.id)
    choices = [(translate(language, "add_expense"), f"g:expense:{token}"),
               (translate(language, "group_summary"), f"g:summary:{token}:0"),
               (translate(language, "group_members_title"), f"g:members:{token}:0"),
               (translate(language, "group_settle"), f"g:settle:{token}:0")]
    if group.owner_person_id == actor_id:
        choices.append((translate(language, "group_invite"), f"g:invite:{token}"))
    choices.append((translate(language, "groups"), "menu:groups"))
    return _keyboard(choices)


async def _list(
    message: Message,
    actor_id: UUID,
    services: Services,
    language: Language,
    page: int = 0,
) -> None:
    """Show a bounded page of the actor's groups."""
    groups = await services.groups.list_groups(actor_id)
    choices = [(g.name, f"g:view:{uuid_token(g.id)}") for g in groups[page * 20:(page + 1) * 20]]
    if len(groups) > (page + 1) * 20:
        choices.append((translate(language, "more"), f"g:list:{page + 1}"))
    choices.extend([(translate(language, "group_create"), "g:new"),
                    (translate(language, "main_menu"), "menu:show")])
    await show(message,
        translate(language, "groups" if groups else "group_empty"),
        reply_markup=_keyboard(choices),
    )


@router.message(F.text.in_(button_values("groups")))
async def groups_menu(
    message: Message,
    state: FSMContext,
    services: Services,
    language: Language,
) -> None:
    """Open groups from the main reply menu."""
    person = await current_person(message, services)
    await state.clear()
    await _list(message, person.id, services, language)


@router.callback_query(F.data == "menu:groups")
@router.callback_query(F.data.startswith("g:list:"))
async def groups_list(
    callback: CallbackQuery,
    state: FSMContext,
    services: Services,
    language: Language,
) -> None:
    """Open or paginate the group list."""
    actor = await _actor(callback, services)
    await state.clear()
    page = int((callback.data or "").rsplit(":", 1)[1]) if callback.data != "menu:groups" else 0
    await _list(callback_message(callback), actor.id, services, language, max(0, page))
    await callback.answer()


@router.callback_query(F.data.startswith("g:view:"))
async def group_details(
    callback: CallbackQuery,
    state: FSMContext,
    services: Services,
    language: Language,
) -> None:
    """Show an authorized group's main screen."""
    actor = await _actor(callback, services)
    group_id = uuid_from_token((callback.data or "").rsplit(":", 1)[1])
    group = await services.groups.get(actor.id, group_id)
    await state.clear()
    await show(callback_message(callback),
        _details(group, language), reply_markup=_actions(group, actor.id, language)
    )
    await callback.answer()


@router.callback_query(F.data == "g:new")
async def begin_group(
    callback: CallbackQuery,
    state: FSMContext,
    services: Services,
    language: Language,
) -> None:
    """Start a persistent group-creation conversation."""
    actor = await _actor(callback, services)
    await state.clear()
    await state.update_data(
        actor_id=str(actor.id), members=[_member(actor)], token=uuid_token(uuid4())
    )
    await state.set_state(GroupStates.name)
    await show(callback_message(callback),
        translate(language, "group_name_prompt"),
        reply_markup=cancel_keyboard(language),
    )
    await callback.answer()


@router.message(GroupStates.name)
async def group_name(
    message: Message,
    state: FSMContext,
    services: Services,
    language: Language,
) -> None:
    """Validate the name and request an explicit supported currency."""
    name = " ".join((message.text or "").split())
    if not 1 <= len(name) <= 120:
        raise ValidationError("Group names must contain 1 to 120 characters.")
    actor = await current_person(message, services)
    settings = await services.user_settings.get_or_create(actor.id)
    await state.update_data(name=name)
    await state.set_state(GroupStates.currency)
    await show(message,
        translate(language, "group_currency_prompt", currency=settings.default_currency),
        reply_markup=cancel_keyboard(language),
    )


@router.message(GroupStates.currency)
async def group_currency(message: Message, state: FSMContext, language: Language) -> None:
    """Store a verified currency before collecting invitees."""
    currency = normalize_currency(message.text or "")
    await state.update_data(currency=currency)
    await state.set_state(GroupStates.members)
    await show(message,
        translate(language, "group_members_prompt"), reply_markup=participant_keyboard(language)
    )


@router.callback_query(F.data.startswith("g:invite:"))
async def group_invite(
    callback: CallbackQuery,
    state: FSMContext,
    services: Services,
    language: Language,
) -> None:
    """Let the owner invite more participants to an existing group."""
    actor = await _actor(callback, services)
    group_id = uuid_from_token((callback.data or "").rsplit(":", 1)[1])
    group = await services.groups.get(actor.id, group_id)
    if group.owner_person_id != actor.id:
        raise PermissionDeniedError("Only the group owner can invite participants.")
    await state.clear()
    await state.update_data(
        actor_id=str(actor.id), group_id=str(group.id), members=[], token=uuid_token(uuid4())
    )
    await state.set_state(GroupStates.members)
    await show(callback_message(callback),
        translate(language, "group_members_prompt"), reply_markup=participant_keyboard(language)
    )
    await callback.answer()


async def _add_member(
    message: Message,
    state: FSMContext,
    person: PersonDTO,
    language: Language,
) -> None:
    """Deduplicate a draft invitation and display a bounded selection summary."""
    data = await state.get_data()
    members = data["members"]
    if str(person.id) not in {m["id"] for m in members}:
        members.append(_member(person))
    await state.update_data(members=members)
    await state.set_state(GroupStates.members)
    await show(message, translate(language, "group_members_selected", names=escape(
        ", ".join(m["name"] for m in members[-15:])
    )), reply_markup=participant_keyboard(language))


@router.message(GroupStates.members, F.users_shared)
async def group_shared_users(
    message: Message,
    state: FSMContext,
    services: Services,
    language: Language,
) -> None:
    """Resolve Telegram contacts into registered users or owned guests."""
    actor = await current_person(message, services)
    if message.users_shared is None:
        return
    for shared in message.users_shared.users:
        person = await services.guests.get_or_create_telegram_guest(actor.id, SharedTelegramUser(
            telegram_user_id=shared.user_id,
            first_name=shared.first_name or f"Telegram user {shared.user_id}",
            last_name=shared.last_name, username=shared.username,
        ))
        await _add_member(message, state, person, language)


@router.message(GroupStates.members, F.text.in_(button_values("add_manual")))
async def group_manual_prompt(message: Message, state: FSMContext, language: Language) -> None:
    """Prompt for a named guest invitation."""
    await state.set_state(GroupStates.manual_name)
    await show(message,
        translate(language, "guest_name"),
        reply_markup=cancel_keyboard(language),
    )


@router.message(GroupStates.manual_name)
async def group_manual_name(
    message: Message,
    state: FSMContext,
    services: Services,
    language: Language,
) -> None:
    """Create a guest owned by the inviter and add it to the selection."""
    actor = await current_person(message, services)
    person = await services.guests.create_manual_guest(actor.id, message.text or "")
    await _add_member(message, state, person, language)


@router.message(GroupStates.members, F.text.in_(button_values("add_from_friends")))
async def group_friend_choices(
    message: Message,
    state: FSMContext,
    services: Services,
    language: Language,
) -> None:
    """Show the first page of friends available for invitation."""
    actor = await current_person(message, services)
    await _friends(message, actor.id, services, language, 0)


async def _friends(
    message: Message,
    actor_id: UUID,
    services: Services,
    language: Language,
    page: int,
) -> None:
    """Page friends so Telegram keyboard limits cannot hide invitees."""
    friends = await services.friends.list_friends(actor_id)
    choices = [
        (f.display_name, f"g:friend:{uuid_token(f.person_id)}")
        for f in friends[page * 20:(page + 1) * 20]
    ]
    if len(friends) > (page + 1) * 20:
        choices.append((translate(language, "more"), f"g:friends:{page + 1}"))
    if page:
        choices.append(("←", f"g:friends:{page - 1}"))
    choices.append((translate(language, "back"), "flow:members"))
    await show(message,
        translate(language, "choose_friend" if friends else "no_friends"),
        reply_markup=_keyboard(choices) if choices else None,
    )


@router.callback_query(GroupStates.members, F.data.startswith("g:friends:"))
async def group_friends_page(
    callback: CallbackQuery,
    services: Services,
    language: Language,
) -> None:
    """Advance the invitee friend selector."""
    actor = await _actor(callback, services)
    page = max(0, int((callback.data or "").rsplit(":", 1)[1]))
    await _friends(callback_message(callback), actor.id, services, language, page)
    await callback.answer()


@router.callback_query(GroupStates.members, F.data.startswith("g:friend:"))
async def group_choose_friend(
    callback: CallbackQuery,
    state: FSMContext,
    services: Services,
    language: Language,
) -> None:
    """Resolve a friend from the actor's own list before adding it."""
    actor = await _actor(callback, services)
    person_id = uuid_from_token((callback.data or "").rsplit(":", 1)[1])
    friends = await services.friends.list_friends(actor.id)
    friend = next((f for f in friends if f.person_id == person_id), None)
    if friend is None:
        raise ValidationError("This friend is no longer available.")
    await _add_member(callback_message(callback), state, PersonDTO(
        id=friend.person_id, display_name=friend.display_name, kind=friend.kind,
        registered=friend.registered, username=friend.username,
        telegram_user_id=friend.telegram_user_id,
    ), language)
    await callback.answer()


@router.message(GroupStates.members, F.text.in_(button_values("remove_participant")))
async def group_remove_choices(message: Message, state: FSMContext, language: Language) -> None:
    """Offer removal from the uncommitted invitee selection."""
    data = await state.get_data()
    choices = [
        (m["name"], f"g:remove:{uuid_token(UUID(m['id']))}")
        for m in data["members"] if m["id"] != data["actor_id"]
    ]
    await show(message,
        translate(language, "choose_remove"),
        reply_markup=_keyboard(choices[:90] + [(translate(language, "back"), "flow:members")]),
    )


@router.callback_query(GroupStates.members, F.data.startswith("g:remove:"))
async def group_remove(callback: CallbackQuery, state: FSMContext, language: Language) -> None:
    """Remove a non-owner invitee before the group is committed."""
    data = await state.get_data()
    person_id = str(uuid_from_token((callback.data or "").rsplit(":", 1)[1]))
    if person_id != data["actor_id"]:
        await state.update_data(members=[m for m in data["members"] if m["id"] != person_id])
    await group_remove_choices(callback_message(callback), state, language)
    await callback.answer()


@router.message(GroupStates.members, F.text.in_(button_values("back")))
async def group_members_back(
    message: Message,
    state: FSMContext,
    services: Services,
    language: Language,
) -> None:
    """Cancel pending invitations and return to groups."""
    await show(message, translate(language, "groups"), reply_markup=main_menu_inline_keyboard(language))
    await groups_menu(message, state, services, language)


@router.message(GroupStates.members, F.text.in_(button_values("done")))
async def group_review(message: Message, state: FSMContext, language: Language) -> None:
    """Review the complete invitee list before committing membership."""
    data = await state.get_data()
    if len(data["members"]) < (1 if data.get("group_id") else 2):
        raise ValidationError("Add at least one other participant.")
    await state.set_state(GroupStates.confirm)
    text = escape(data.get("name", translate(language, "group_invite")))
    if data.get("currency"):
        text += " · " + data["currency"]
    await show(message, text, reply_markup=main_menu_inline_keyboard(language))
    members = data["members"]
    for offset in range(0, len(members), 20):
        names = ("• " + escape(m["name"]) for m in members[offset:offset + 20])
        await show(message, "\n".join(names))
    action = translate(language, "group_invite" if data.get("group_id") else "group_confirm")
    await show(message, action, reply_markup=_keyboard([
        (action, f"g:save:{data['token']}"), (translate(language, "back"), "g:edit"),
    ]))


@router.callback_query(GroupStates.confirm, F.data == "g:edit")
async def group_edit(callback: CallbackQuery, state: FSMContext, language: Language) -> None:
    """Return to invitee selection without discarding entered preferences."""
    await state.set_state(GroupStates.members)
    await show(callback_message(callback),
        translate(language, "group_members_prompt"), reply_markup=participant_keyboard(language)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("g:save:"))
async def group_save(
    callback: CallbackQuery,
    state: FSMContext,
    services: Services,
    bot: Bot,
    language: Language,
) -> None:
    """Commit the reviewed membership and notify newly added registered users."""
    data = await state.get_data()
    if (
        await state.get_state() != GroupStates.confirm.state
        or callback.data != f"g:save:{data.get('token')}"
    ):
        await callback.answer(translate(language, "draft_expired"), show_alert=True)
        return
    actor = await _actor(callback, services)
    ids = tuple(UUID(m["id"]) for m in data["members"])
    if data.get("group_id"):
        group, added = await services.groups.add_members(actor.id, UUID(data["group_id"]), ids)
    else:
        group = await services.groups.create(actor.id, data["name"], data["currency"], ids)
        added = tuple(m.id for m in group.participants if m.id != actor.id)
    await state.clear()
    await show(callback_message(callback),
        _details(group, language), reply_markup=main_menu_inline_keyboard(language)
    )
    await show(callback_message(callback),
        translate(language, "group_invites_saved"), reply_markup=_actions(group, actor.id, language)
    )
    await callback.answer()
    for person in await services.users.list_registered(added):
        if person.telegram_user_id is None or person.id == actor.id:
            continue
        settings = await services.user_settings.get_or_create(person.id)
        try:
            await bot.send_message(
                person.telegram_user_id,
                translate(
                    settings.language, "group_added", name=escape(actor.display_name),
                    group=escape(group.name), currency=group.default_currency,
                ),
                reply_markup=_keyboard([(group.name, f"g:view:{uuid_token(group.id)}")]),
            )
        except TelegramAPIError:
            pass


@router.callback_query(F.data.startswith("g:expense:"))
async def group_expense(
    callback: CallbackQuery,
    state: FSMContext,
    services: Services,
    language: Language,
) -> None:
    """Start a durable expense using this group's currency and member selector."""
    actor = await _actor(callback, services)
    group_id = uuid_from_token((callback.data or "").rsplit(":", 1)[1])
    group = await services.groups.get(actor.id, group_id)
    await state.clear()
    await state.update_data(
        draft_id=str(uuid4()), creator_id=str(actor.id), participants=[_member(actor)],
        group_id=str(group.id), group_name=group.name, group_currency=group.default_currency,
        group_members=[_member(m) for m in group.participants],
    )
    await state.set_state(AddExpenseStates.description)
    from splitnshare.presentation.routers.expenses import render_expense_draft

    await render_expense_draft(callback_message(callback), state, language)
    await callback.answer()


@router.callback_query(F.data.startswith("g:summary:"))
@router.callback_query(F.data.startswith("g:members:"))
@router.callback_query(F.data.startswith("g:settle:"))
async def group_subscreen(callback: CallbackQuery, services: Services, language: Language) -> None:
    """Page group members, pairwise balances, or settlement counterparties."""
    actor = await _actor(callback, services)
    _, screen, token, page_text = (callback.data or "").split(":")
    page = max(0, int(page_text))
    group, balances = await services.groups.summary(actor.id, uuid_from_token(token))
    labels = {m.id: m.display_name for m in group.participants}
    choices: list[tuple[str, str]] = []
    lines = []
    if screen == "members":
        lines = [
            escape(participant_label(m.display_name, m.id, m.username)) for m in group.participants
        ]
    elif screen == "summary":
        lines = [
            translate(
                language, "group_payment", payer=escape(b.other_name),
                recipient=escape(labels[member_id]), amount=Money(b.net_minor, b.currency).format(),
            )
            for member_id, items in balances.items() for b in items if b.net_minor > 0
        ]
    else:
        own = balances.get(actor.id, ())
        ids = list(dict.fromkeys(b.other_person_id for b in own))
        choices = [
            (labels.get(person_id, str(person_id)), f"g:pay:{token}:{uuid_token(person_id)}")
            for person_id in ids[page * 20:(page + 1) * 20]
        ]
        if len(ids) > (page + 1) * 20:
            choices.append((translate(language, "more"), f"g:settle:{token}:{page + 1}"))
        if own:
            choices.append((translate(language, "group_settle_all"), f"g:pay:{token}:all"))
        lines = [translate(language, "group_settle" if own else "group_no_person_debts")]
    if screen != "settle" and len(lines) > (page + 1) * 20:
        choices.append((translate(language, "more"), f"g:{screen}:{token}:{page + 1}"))
    choices.append((translate(language, "group_back"), f"g:view:{token}"))
    visible = lines[page * 20:(page + 1) * 20] if screen != "settle" else lines
    await show(callback_message(callback),
        _details(group, language) + "\n\n"
        + ("\n".join(visible) or translate(language, "group_no_debts")),
        reply_markup=_keyboard(choices),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("g:pay:"))
async def group_payment_review(
    callback: CallbackQuery,
    state: FSMContext,
    services: Services,
    language: Language,
) -> None:
    """Snapshot the current user's selected group balances for confirmation."""
    actor = await _actor(callback, services)
    _, _, token, other_token = (callback.data or "").split(":")
    group, balances = await services.groups.summary(actor.id, uuid_from_token(token))
    other_id = uuid_from_token(other_token) if other_token != "all" else None
    selected = [
        b for b in balances.get(actor.id, ()) if other_id is None or b.other_person_id == other_id
    ]
    if not selected:
        await callback.answer(translate(language, "group_no_person_debts"), show_alert=True)
        return
    confirmation = uuid_token(uuid4())
    await state.clear()
    await state.update_data(
        group_id=str(group.id), other_id=str(other_id) if other_id else None, token=confirmation,
        balances=[{"other_person_id": str(b.other_person_id), "other_name": b.other_name,
                   "currency": b.currency, "net_minor": b.net_minor} for b in selected])
    await state.set_state(GroupStates.settlement)
    lines = [translate(
        language, "group_payment",
        payer=escape(actor.display_name if b.net_minor < 0 else b.other_name),
        recipient=escape(b.other_name if b.net_minor < 0 else actor.display_name),
        amount=Money(abs(b.net_minor), b.currency).format(),
    ) for b in selected]
    for offset in range(0, len(lines), 15):
        await show(callback_message(callback), translate(
            language, "group_settle_review", group=escape(group.name),
            payments="\n".join(lines[offset:offset + 15]),
        ))
    await show(callback_message(callback),
        translate(language, "group_settle_confirm"), reply_markup=_keyboard([
            (translate(language, "group_settle_confirm"), f"g:paid:{confirmation}"),
            (translate(language, "back"), "flow:back"),
        ]),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("g:paid:"))
async def group_payment_save(
    callback: CallbackQuery,
    state: FSMContext,
    services: Services,
    bot: Bot,
    language: Language,
) -> None:
    """Record every reviewed group payment in a single atomic transaction."""
    data = await state.get_data()
    if (
        await state.get_state() != GroupStates.settlement.state
        or callback.data != f"g:paid:{data.get('token')}"
    ):
        await callback.answer(translate(language, "settlement_stale"), show_alert=True)
        return
    actor = await _actor(callback, services)
    expected = tuple(BalanceDTO(
        other_person_id=UUID(b["other_person_id"]), other_name=b["other_name"],
        currency=b["currency"], net_minor=b["net_minor"],
    ) for b in data["balances"])
    settlements = await services.groups.settle(actor.id, UUID(data["group_id"]), expected,
                                               UUID(data["other_id"]) if data["other_id"] else None)
    await state.clear()
    await show(callback_message(callback),
        translate(language, "group_settled"), reply_markup=_keyboard([
            (translate(language, "group_back"), f"g:view:{uuid_token(UUID(data['group_id']))}"),
        ]),
    )
    await callback.answer()
    for settlement in settlements:
        await _notify_settlement_counterparty(bot, services, settlement)
