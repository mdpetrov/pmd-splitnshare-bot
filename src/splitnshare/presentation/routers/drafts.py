"""List, resume, edit, and explicitly discard saved expense drafts."""

from datetime import datetime
from html import escape
from typing import Any
from uuid import UUID

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from splitnshare.domain.enums import Language, SplitMethod
from splitnshare.domain.errors import DomainError, ValidationError
from splitnshare.domain.money import Money
from splitnshare.domain.splitting import EqualSplitStrategy
from splitnshare.infrastructure.fsm_storage import SqlAlchemyFSMStorage
from splitnshare.presentation.datetimes import format_local_datetime
from splitnshare.presentation.helpers import callback_message
from splitnshare.presentation.i18n import button_values, translate
from splitnshare.presentation.routers.expenses import render_expense_draft
from splitnshare.presentation.states import AddExpenseStates

router = Router(name="drafts")
router.message.filter(F.chat.type == "private")
router.callback_query.filter(F.message.chat.type == "private")


def _storage(state: FSMContext) -> SqlAlchemyFSMStorage:
    """Require the application's durable storage adapter for draft actions."""
    if not isinstance(state.storage, SqlAlchemyFSMStorage):
        raise ValidationError("Persistent draft storage is unavailable.")
    return state.storage


async def _show_list(
    message: Message, state: FSMContext, language: Language, offset: int = 0,
) -> None:
    """Render one owner-scoped page without discarding unfinished work."""
    await state.clear()
    drafts = await _storage(state).list_drafts(state.key, offset)
    rows = []
    for draft in drafts[:10]:
        title = str(draft.data.get("description") or translate(language, "untitled_draft"))[:45]
        rows.append([
            InlineKeyboardButton(text=title, callback_data=f"draft:view:{draft.id}"),
            InlineKeyboardButton(text=translate(language, "delete"),
                                 callback_data=f"draft:ask_delete:{draft.id}"),
        ])
    navigation = []
    if offset:
        navigation.append(InlineKeyboardButton(
            text=translate(language, "back"), callback_data=f"draft:page:{max(0, offset - 10)}",
        ))
    if len(drafts) > 10:
        navigation.append(InlineKeyboardButton(
            text=translate(language, "more"), callback_data=f"draft:page:{offset + 10}",
        ))
    if navigation:
        rows.append(navigation)
    rows.append([InlineKeyboardButton(
        text=translate(language, "main_menu"), callback_data="menu:show",
    )])
    await message.answer(
        translate(language, "drafts_help" if drafts else "drafts_empty"),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


@router.message(Command("drafts"))
@router.message(F.text.in_(button_values("drafts")))
async def show_drafts(message: Message, state: FSMContext, language: Language) -> None:
    """Open unfinished expenses from a command or the persistent menu."""
    await _show_list(message, state, language)


@router.callback_query(F.data == "menu:drafts")
@router.callback_query(F.data.startswith("draft:page:"))
async def page_drafts(callback: CallbackQuery, state: FSMContext, language: Language) -> None:
    """Navigate draft pages with a validated nonnegative offset."""
    offset = 0
    if callback.data and callback.data.startswith("draft:page:"):
        try:
            offset = int(callback.data.rsplit(":", 1)[1])
            if not 0 <= offset <= 1_000_000:
                raise ValueError
        except ValueError:
            await callback.answer(translate(language, "draft_expired"), show_alert=True)
            return
    await _show_list(callback_message(callback), state, language, offset)
    await callback.answer()


def _draft_summary(data: dict[str, Any], language: Language) -> str:
    """Show every entered draft field while tolerating an unfinished step."""
    missing = translate(language, "draft_missing")
    total = (
        Money(data["total_minor"], data["currency"]).format()
        if "total_minor" in data and "currency" in data else missing
    )
    date = (
        format_local_datetime(
            datetime.fromisoformat(data["occurred_at"]), data.get("timezone", "UTC"), language
        ) if data.get("occurred_at") else missing
    )
    participants = data.get("participants") or []
    payer = next(
        (person["name"] for person in (data.get("group_members") or participants)
         if person["id"] == data.get("payer_id")), missing,
    )
    method = data.get("split_method")
    method_label = (
        translate(language, "split_equally") if method == SplitMethod.EQUAL.value
        else translate(language, "exact_amounts") if method == SplitMethod.EXACT.value
        else missing
    )
    lines = [
        translate(language, "draft_summary"),
        escape(str(data.get("description") or missing)),
        translate(language, "total", total=total),
        translate(language, "expense_date", date=escape(date)),
        translate(
            language, "group_review_label",
            name=escape(str(data.get("group_name") or missing)),
        ),
        translate(language, "expense_paid_by", name=escape(payer)),
        translate(language, "expense_split", method=method_label),
        "",
        translate(language, "participants"),
    ]
    amounts = data.get("exact_amounts") or {}
    if (
        method == SplitMethod.EQUAL.value
        and 2 <= len(participants) <= 10
        and data.get("total_minor", 0) >= len(participants)
    ):
        try:
            allocations = EqualSplitStrategy().allocate(
                data["total_minor"], [UUID(person["id"]) for person in participants]
            )
        except (ValidationError, ValueError):
            pass
        else:
            amounts = {str(part.person_id): part.owed_minor for part in allocations}
    for person in participants:
        label = f"• {escape(person['name'])}"
        if person["id"] in amounts and data.get("currency"):
            label += f": {Money(amounts[person['id']], data['currency']).format()}"
        lines.append(label)
    if not participants:
        lines.append(missing)
    return "\n".join(lines)


@router.callback_query(F.data.startswith("draft:view:"))
@router.callback_query(F.data.startswith("draft:resume:"))
@router.callback_query(F.data.startswith("draft:edit:"))
async def view_draft(callback: CallbackQuery, state: FSMContext, language: Language) -> None:
    """Show an owned draft's complete currently known summary before any action."""
    try:
        identifier = UUID((callback.data or "").rsplit(":", 1)[1])
        draft = await _storage(state).resume(state.key, identifier)
    except (DomainError, ValueError) as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    await state.clear()
    await callback_message(callback).answer(
        _draft_summary(draft.data, language),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=translate(language, "draft_continue"),
                                  callback_data=f"draft:continue:{identifier}")],
            [InlineKeyboardButton(text=translate(language, "edit_draft"),
                                  callback_data=f"draft:edit_fields:{identifier}")],
            [InlineKeyboardButton(text=translate(language, "delete"),
                                  callback_data=f"draft:ask_delete:{identifier}")],
            [InlineKeyboardButton(text=translate(language, "main_menu"),
                                  callback_data="menu:show")],
        ]),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("draft:continue:"))
@router.callback_query(F.data.startswith("draft:edit_fields:"))
async def resume_draft(callback: CallbackQuery, state: FSMContext, language: Language) -> None:
    """Restore an owned draft at its saved step or reopen its fields for editing."""
    try:
        identifier = UUID((callback.data or "").rsplit(":", 1)[1])
        await _storage(state).resume(state.key, identifier)
        if callback.data and callback.data.startswith("draft:edit_fields:"):
            await state.update_data(edit_mode=True)
            await state.set_state(AddExpenseStates.description)
        await render_expense_draft(callback_message(callback), state, language)
    except (DomainError, ValueError) as exc:
        await callback.answer(str(exc), show_alert=True)
        return
    await callback.answer()


@router.callback_query(F.data.startswith("draft:ask_delete:"))
async def ask_discard_draft(callback: CallbackQuery, language: Language) -> None:
    """Ask for explicit confirmation before removing an unfinished expense."""
    try:
        identifier = UUID((callback.data or "").rsplit(":", 1)[1])
    except ValueError:
        await callback.answer(translate(language, "draft_expired"), show_alert=True)
        return
    await callback_message(callback).answer(
        translate(language, "discard_draft_question"),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=translate(language, "delete"),
                                  callback_data=f"draft:delete:{identifier}")],
            [InlineKeyboardButton(text=translate(language, "keep"), callback_data="menu:drafts")],
        ]),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("draft:delete:"))
async def discard_draft(callback: CallbackQuery, state: FSMContext, language: Language) -> None:
    """Delete only the selected user's draft, then refresh the list."""
    try:
        identifier = UUID((callback.data or "").rsplit(":", 1)[1])
        await _storage(state).discard(state.key, identifier)
    except (DomainError, ValueError):
        await callback.answer(translate(language, "draft_expired"), show_alert=True)
        return
    await callback_message(callback).edit_reply_markup(reply_markup=None)
    await _show_list(callback_message(callback), state, language)
    await callback.answer()
