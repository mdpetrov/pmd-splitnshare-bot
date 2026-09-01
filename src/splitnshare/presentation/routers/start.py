from html import escape

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from splitnshare.domain.enums import Language
from splitnshare.presentation.container import Services
from splitnshare.presentation.helpers import telegram_identity
from splitnshare.presentation.i18n import button_values, translate
from splitnshare.presentation.keyboards import main_menu

router = Router(name="start")
router.message.filter(F.chat.type == "private")


@router.message(CommandStart())
async def start(message: Message, state: FSMContext, services: Services) -> None:
    if message.from_user is None:
        return
    await state.clear()
    identity = telegram_identity(message.from_user)
    person = await services.users.register_or_update(identity)
    settings = await services.user_settings.get_or_create(
        person.id, preferred_language=identity.language_code
    )
    await message.answer(
        translate(settings.language, "welcome", name=escape(person.display_name)),
        reply_markup=main_menu(settings.language),
    )


@router.message(Command("cancel"))
@router.message(F.text.in_(button_values("cancel")))
async def cancel(message: Message, state: FSMContext, language: Language) -> None:
    await state.clear()
    await message.answer(translate(language, "cancelled"), reply_markup=main_menu(language))
