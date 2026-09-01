from aiogram import F, Router
from aiogram.types import Message

from splitnshare.domain.enums import Language
from splitnshare.presentation.container import Services
from splitnshare.presentation.formatters import balances_text
from splitnshare.presentation.helpers import current_person
from splitnshare.presentation.i18n import button_values
from splitnshare.presentation.keyboards import main_menu

router = Router(name="balances")
router.message.filter(F.chat.type == "private")


@router.message(F.text.in_(button_values("balances")))
async def balances(message: Message, services: Services, language: Language) -> None:
    person = await current_person(message, services)
    current_balances = await services.balances.get_balances(person.id)
    await message.answer(
        balances_text(current_balances, language), reply_markup=main_menu(language)
    )
