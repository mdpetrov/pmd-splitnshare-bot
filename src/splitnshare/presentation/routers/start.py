"""Handle registration, onboarding, main-menu navigation, and cancellation."""

from html import escape

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from splitnshare.domain.enums import Language
from splitnshare.presentation.container import Services
from splitnshare.presentation.flow_messages import show
from splitnshare.presentation.formatters import welcome_text
from splitnshare.presentation.helpers import callback_message, telegram_identity
from splitnshare.presentation.i18n import button_values, language_name, translate
from splitnshare.presentation.keyboards import (
    main_menu,
    main_menu_inline_keyboard,
    timezone_keyboard,
)
from splitnshare.presentation.states import OnboardingStates

router = Router(name="start")
router.message.filter(F.chat.type == "private")
router.callback_query.filter(F.message.chat.type == "private")


@router.message(CommandStart())
async def start(message: Message, state: FSMContext, services: Services) -> None:
    """Register or refresh a user and continue onboarding or show the menu."""
    if message.from_user is None:
        return
    await state.clear()
    identity = telegram_identity(message.from_user)
    person = await services.users.register_or_update(identity)
    settings = await services.user_settings.get_or_create(
        person.id, preferred_language=identity.language_code
    )
    # Install the persistent keyboard only at the explicit /start entry point.
    await message.answer(
        translate(settings.language, "main_menu"), reply_markup=main_menu(settings.language)
    )
    if settings.timezone is None:
        await state.set_state(OnboardingStates.timezone)
        await show(
            message,
            translate(
                settings.language,
                "onboarding_welcome",
                name=escape(person.display_name),
                currency=escape(settings.default_currency),
                language=escape(language_name(settings.language, settings.language)),
            ),
        )
        await show(
            message,
            translate(settings.language, "choose_timezone"),
            reply_markup=timezone_keyboard(settings.language, include_back=False),
        )
        return
    balances = await services.balances.get_balances(person.id)
    await show(
        message,
        welcome_text(person.display_name, balances, settings.language),
        reply_markup=main_menu_inline_keyboard(settings.language),
    )
    await show(
        message,
        translate(settings.language, "main_menu_prompt"),
        reply_markup=main_menu_inline_keyboard(settings.language),
    )


@router.callback_query(F.data == "menu:show")
async def show_main_menu_callback(
    callback: CallbackQuery,
    state: FSMContext,
    services: Services,
    language: Language,
) -> None:
    """Clear active flow state and replace the message with the main menu."""
    if callback.from_user is None:
        return
    target_message = callback_message(callback)
    settings = await services.user_settings.find_by_telegram_id(callback.from_user.id)
    if settings is None or settings.timezone is None:
        await state.set_state(OnboardingStates.timezone)
        await show(
            target_message,
            translate(language, "onboarding_timezone_required"),
            reply_markup=timezone_keyboard(language, include_back=False),
        )
        await callback.answer()
        return
    await state.clear()
    await show(
        target_message,
        translate(language, "main_menu_prompt"),
        reply_markup=main_menu_inline_keyboard(language),
    )
    await callback.answer()


@router.message(F.text.in_(button_values("main_menu")))
async def show_main_menu_message(
    message: Message, state: FSMContext, services: Services, language: Language
) -> None:
    """Restore the persistent main keyboard from its own button."""
    if message.from_user is None:
        return
    settings = await services.user_settings.find_by_telegram_id(message.from_user.id)
    if settings is None or settings.timezone is None:
        await state.set_state(OnboardingStates.timezone)
        await show(
            message,
            translate(language, "onboarding_timezone_required"),
            reply_markup=timezone_keyboard(language, include_back=False),
        )
        return
    await state.clear()
    await show(
        message,
        translate(language, "main_menu_prompt"),
        reply_markup=main_menu_inline_keyboard(language),
    )


@router.message(Command("cancel"))
@router.message(F.text.in_(button_values("cancel")))
async def cancel(message: Message, state: FSMContext, language: Language) -> None:
    """Cancel any text-driven flow and restore the main reply keyboard."""
    if await state.get_state() == OnboardingStates.timezone.state:
        await show(
            message,
            translate(language, "onboarding_timezone_required"),
            reply_markup=timezone_keyboard(language, include_back=False),
        )
        return
    await state.clear()
    await show(
        message,
        translate(language, "cancelled_drafts_kept"),
        reply_markup=main_menu_inline_keyboard(language),
    )
