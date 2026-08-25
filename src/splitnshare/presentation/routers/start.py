from html import escape

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from splitnshare.presentation.container import Services
from splitnshare.presentation.helpers import telegram_identity
from splitnshare.presentation.keyboards import CANCEL, main_menu

router = Router(name="start")
router.message.filter(F.chat.type == "private")


@router.message(CommandStart())
async def start(message: Message, state: FSMContext, services: Services) -> None:
    if message.from_user is None:
        return
    await state.clear()
    person = await services.users.register_or_update(telegram_identity(message.from_user))
    await message.answer(
        f"Welcome, {escape(person.display_name)}. Add an expense or review your transactions.",
        reply_markup=main_menu(),
    )


@router.message(Command("cancel"))
@router.message(F.text == CANCEL)
async def cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Cancelled.", reply_markup=main_menu())

