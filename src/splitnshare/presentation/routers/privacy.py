"""Present the bot's data-handling notice without requiring registration."""

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from splitnshare.domain.enums import Language
from splitnshare.presentation.i18n import translate

router = Router(name="privacy")
router.message.filter(F.chat.type == "private")


@router.message(Command("privacy"))
async def show_privacy_notice(message: Message, language: Language) -> None:
    """Explain which data is stored, why it is used, and how to request deletion."""
    await message.answer(translate(language, "privacy_notice"))
