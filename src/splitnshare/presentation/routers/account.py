"""Handle irreversible user-account anonymization with explicit confirmation."""

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from splitnshare.domain.enums import Language
from splitnshare.domain.errors import UnsettledAccountError
from splitnshare.presentation.container import Services
from splitnshare.presentation.flow_messages import forget_flow, show, show_markup
from splitnshare.presentation.helpers import callback_message
from splitnshare.presentation.i18n import translate
from splitnshare.presentation.keyboards import (
    delete_account_confirm_keyboard,
    main_menu_inline_keyboard,
)
from splitnshare.presentation.states import DeleteAccountStates

router = Router(name="account")
router.message.filter(F.chat.type == "private")
router.callback_query.filter(F.message.chat.type == "private")


@router.message(Command("delete_account"))
async def request_account_deletion(
    message: Message,
    state: FSMContext,
    services: Services,
    language: Language,
) -> None:
    """Describe retained shared records and request irreversible confirmation."""
    if message.from_user is None:
        return
    person = await services.users.find_registered_target(message.from_user.id)
    if person is None:
        await show(message, translate(language, "use_start"))
        return
    await state.clear()
    balances = await services.balances.get_balances(person.id)
    if any(balance.net_minor != 0 for balance in balances):
        await show(message,
            translate(language, "delete_account_unsettled"),
            reply_markup=main_menu_inline_keyboard(language),
        )
        return
    await state.set_state(DeleteAccountStates.confirm)
    await show(message,
        translate(language, "delete_account_warning"),
        reply_markup=delete_account_confirm_keyboard(language),
    )


@router.callback_query(F.data == "account:delete:confirm")
async def confirm_account_deletion(
    callback: CallbackQuery,
    state: FSMContext,
    services: Services,
    language: Language,
) -> None:
    """Anonymize the authenticated account and update its confirmation message."""
    if await state.get_state() != DeleteAccountStates.confirm.state:
        await callback.answer(
            translate(language, "delete_account_expired"), show_alert=True
        )
        return
    if callback.from_user is None:
        return
    target_message = callback_message(callback)
    person = await services.users.find_registered_target(callback.from_user.id)
    if person is None:
        await state.clear()
        await callback.answer(
            translate(language, "delete_account_expired"), show_alert=True
        )
        return
    try:
        deleted = await services.users.delete_account(person.id)
    except UnsettledAccountError:
        await state.clear()
        await show_markup(target_message, reply_markup=None)
        await show(target_message,
            translate(language, "delete_account_unsettled"),
            reply_markup=main_menu_inline_keyboard(language),
        )
        await callback.answer()
        return
    await state.clear()
    if not deleted:
        await callback.answer(
            translate(language, "delete_account_expired"), show_alert=True
        )
        return
    forget_flow()
    await show_markup(target_message, reply_markup=None)
    await show(target_message,
        translate(language, "delete_account_complete"),
    )
    await callback.answer()


@router.callback_query(F.data == "account:delete:cancel")
async def cancel_account_deletion(
    callback: CallbackQuery,
    state: FSMContext,
    language: Language,
) -> None:
    """Keep the account and restore its main reply menu."""
    target_message = callback_message(callback)
    await state.clear()
    await show(target_message, translate(language, "delete_account_cancelled"))
    await show(target_message,
        translate(language, "main_menu_prompt"),
        reply_markup=main_menu_inline_keyboard(language),
    )
    await callback.answer()
