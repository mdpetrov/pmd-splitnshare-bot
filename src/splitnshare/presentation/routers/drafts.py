"""List, resume, edit, and explicitly discard saved expense drafts."""

from uuid import UUID

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from splitnshare.domain.enums import Language
from splitnshare.domain.errors import DomainError, ValidationError
from splitnshare.infrastructure.fsm_storage import SqlAlchemyFSMStorage
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
            InlineKeyboardButton(text=title, callback_data=f"draft:resume:{draft.id}"),
            InlineKeyboardButton(text=translate(language, "edit_draft"),
                                 callback_data=f"draft:edit:{draft.id}"),
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


@router.callback_query(F.data.startswith("draft:resume:"))
@router.callback_query(F.data.startswith("draft:edit:"))
async def resume_draft(callback: CallbackQuery, state: FSMContext, language: Language) -> None:
    """Restore an owned draft at its saved step or reopen its fields for editing."""
    try:
        identifier = UUID((callback.data or "").rsplit(":", 1)[1])
        await _storage(state).resume(state.key, identifier)
        if callback.data and callback.data.startswith("draft:edit:"):
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
