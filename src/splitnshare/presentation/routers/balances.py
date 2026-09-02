from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from splitnshare.domain.enums import Language
from splitnshare.presentation.container import Services
from splitnshare.presentation.formatters import balances_text
from splitnshare.presentation.helpers import callback_message, current_person
from splitnshare.presentation.i18n import button_values, translate
from splitnshare.presentation.keyboards import back_to_main_menu_keyboard

router = Router(name="balances")
router.message.filter(F.chat.type == "private")
router.callback_query.filter(F.message.chat.type == "private")


@router.message(F.text.in_(button_values("balances")))
async def balances(message: Message, services: Services, language: Language) -> None:
    person = await current_person(message, services)
    current_balances = await services.balances.get_balances(person.id)
    await message.answer(
        balances_text(current_balances, language),
        reply_markup=back_to_main_menu_keyboard(language),
    )


@router.callback_query(F.data == "menu:balances")
async def balances_callback(
    callback: CallbackQuery, services: Services, language: Language
) -> None:
    if callback.from_user is None:
        return
    target_message = callback_message(callback)
    person = await services.users.find_registered_target(callback.from_user.id)
    if person is None:
        await callback.answer(translate(language, "use_start"), show_alert=True)
        return
    current_balances = await services.balances.get_balances(person.id)
    await target_message.edit_text(
        balances_text(current_balances, language),
        reply_markup=back_to_main_menu_keyboard(language),
    )
    await callback.answer()
