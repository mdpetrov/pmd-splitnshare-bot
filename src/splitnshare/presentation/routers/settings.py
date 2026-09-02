"""Handle currency, language, timezone, and onboarding settings flows."""

from html import escape

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from splitnshare.application.dto import UpdateUserSettingsCommand, UserSettingsDTO
from splitnshare.domain.enums import Language
from splitnshare.domain.errors import DomainError
from splitnshare.presentation.container import Services
from splitnshare.presentation.helpers import callback_message, callback_payload, current_person
from splitnshare.presentation.i18n import button_values, language_name, translate
from splitnshare.presentation.keyboards import (
    cancel_keyboard,
    currency_keyboard,
    language_keyboard,
    main_menu,
    main_menu_inline_keyboard,
    settings_keyboard,
    timezone_keyboard,
)
from splitnshare.presentation.states import OnboardingStates, UserSettingsStates
from splitnshare.presentation.timezones import (
    timezone_from_callback_key,
    timezone_label,
)

router = Router(name="settings")
router.message.filter(F.chat.type == "private")
router.callback_query.filter(F.message.chat.type == "private")


@router.message(Command("settings"))
@router.message(F.text.in_(button_values("settings")))
async def show_settings(
    message: Message,
    state: FSMContext,
    services: Services,
    language: Language,
) -> None:
    """Show the current user's settings from the reply menu."""
    person = await current_person(message, services)
    settings = await services.user_settings.get_or_create(
        person.id,
        preferred_language=message.from_user.language_code if message.from_user else None,
    )
    if settings.timezone is None:
        await state.set_state(OnboardingStates.timezone)
        await message.answer(
            translate(language, "onboarding_timezone_required"),
            reply_markup=timezone_keyboard(language, include_back=False),
        )
        return
    await message.answer(
        _settings_text(settings, language),
        reply_markup=settings_keyboard(language),
    )


@router.callback_query(F.data == "settings:show")
@router.callback_query(F.data == "menu:settings")
async def show_settings_callback(
    callback: CallbackQuery,
    state: FSMContext,
    services: Services,
    language: Language,
) -> None:
    """Replace the current message with the user's settings panel."""
    if callback.from_user is None:
        return
    target_message = callback_message(callback)
    person = await services.users.find_registered_target(callback.from_user.id)
    if person is None:
        await callback.answer("Use /start first.", show_alert=True)
        return
    settings = await services.user_settings.get_or_create(person.id)
    if settings.timezone is None:
        await state.set_state(OnboardingStates.timezone)
        await target_message.edit_text(
            translate(language, "onboarding_timezone_required"),
            reply_markup=timezone_keyboard(language, include_back=False),
        )
        await callback.answer()
        return
    await target_message.edit_text(
        _settings_text(settings, language),
        reply_markup=settings_keyboard(language),
    )
    await callback.answer()


@router.callback_query(F.data == "settings:currency")
async def choose_currency(callback: CallbackQuery, language: Language) -> None:
    """Show preset and custom currency choices."""
    target_message = callback_message(callback)
    await target_message.edit_text(
        translate(language, "choose_currency"),
        reply_markup=currency_keyboard(language),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("settings:set_currency:"))
async def set_currency(
    callback: CallbackQuery, services: Services, language: Language
) -> None:
    """Validate a currency callback and persist the selected default."""
    if callback.from_user is None:
        return
    payload, target_message = callback_payload(callback)
    person = await services.users.find_registered_target(callback.from_user.id)
    if person is None:
        await callback.answer("Use /start first.", show_alert=True)
        return
    currency = payload.rsplit(":", 1)[1]
    updated = await services.user_settings.update(
        UpdateUserSettingsCommand(person_id=person.id, default_currency=currency)
    )
    await target_message.edit_text(
        translate(language, "currency_saved", currency=escape(updated.default_currency)),
        reply_markup=settings_keyboard(language),
    )
    await callback.answer()


@router.callback_query(F.data == "settings:custom_currency")
async def request_custom_currency(
    callback: CallbackQuery, state: FSMContext, language: Language
) -> None:
    """Enter the state that accepts a custom ISO currency code."""
    target_message = callback_message(callback)
    await state.set_state(UserSettingsStates.custom_currency)
    await target_message.answer(
        translate(language, "enter_currency"), reply_markup=cancel_keyboard(language)
    )
    await callback.answer()


@router.message(
    UserSettingsStates.custom_currency,
    F.text.in_(button_values("back")),
)
async def custom_currency_back(
    message: Message, state: FSMContext, services: Services, language: Language
) -> None:
    """Leave custom currency entry and restore the settings panel."""
    await state.clear()
    person = await current_person(message, services)
    settings = await services.user_settings.get_or_create(person.id)
    await message.answer(
        _settings_text(settings, language),
        reply_markup=settings_keyboard(language),
    )


@router.message(UserSettingsStates.custom_currency)
async def receive_custom_currency(
    message: Message, state: FSMContext, services: Services, language: Language
) -> None:
    """Parse and save a user-entered ISO currency code."""
    person = await current_person(message, services)
    try:
        updated = await services.user_settings.update(
            UpdateUserSettingsCommand(
                person_id=person.id,
                default_currency=message.text or "",
            )
        )
    except DomainError:
        await message.answer(translate(language, "invalid_currency"))
        return
    await state.clear()
    await message.answer(
        translate(language, "currency_saved", currency=escape(updated.default_currency)),
        reply_markup=main_menu(language),
    )


@router.callback_query(F.data == "settings:language")
async def choose_language(callback: CallbackQuery, language: Language) -> None:
    """Show supported interface-language choices."""
    target_message = callback_message(callback)
    await target_message.edit_text(
        translate(language, "choose_language"),
        reply_markup=language_keyboard(language),
    )
    await callback.answer()


@router.callback_query(F.data == "settings:timezone")
async def choose_timezone(callback: CallbackQuery, language: Language) -> None:
    """Show localized timezone choices from the settings panel."""
    target_message = callback_message(callback)
    await target_message.edit_text(
        translate(language, "choose_timezone"),
        reply_markup=timezone_keyboard(language),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("settings:set_timezone:"))
async def set_timezone(
    callback: CallbackQuery,
    state: FSMContext,
    services: Services,
    language: Language,
) -> None:
    """Save a timezone and complete onboarding when applicable."""
    if callback.from_user is None:
        return
    payload, target_message = callback_payload(callback)
    timezone = timezone_from_callback_key(payload.rsplit(":", 1)[1])
    if timezone is None:
        await callback.answer(translate(language, "timezone_invalid"), show_alert=True)
        return
    person = await services.users.find_registered_target(callback.from_user.id)
    if person is None:
        await callback.answer(translate(language, "use_start"), show_alert=True)
        return
    updated = await services.user_settings.update(
        UpdateUserSettingsCommand(person_id=person.id, timezone=timezone)
    )
    label = escape(timezone_label(updated.timezone, language))
    onboarding = await state.get_state() == OnboardingStates.timezone.state
    if onboarding:
        await state.clear()
        await target_message.edit_text(
            translate(language, "timezone_saved", timezone=label)
        )
        await target_message.answer(
            translate(language, "onboarding_complete"),
            reply_markup=main_menu(language),
        )
        await target_message.answer(
            translate(language, "main_menu_prompt"),
            reply_markup=main_menu_inline_keyboard(language),
        )
    else:
        await target_message.edit_text(
            translate(language, "timezone_saved", timezone=label),
            reply_markup=settings_keyboard(language),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("settings:set_language:"))
async def set_language(callback: CallbackQuery, services: Services) -> None:
    """Persist the selected interface language and redraw settings."""
    if callback.from_user is None:
        return
    payload, target_message = callback_payload(callback)
    person = await services.users.find_registered_target(callback.from_user.id)
    if person is None:
        await callback.answer("Use /start first.", show_alert=True)
        return
    selected = Language(payload.rsplit(":", 1)[1])
    await services.user_settings.update(
        UpdateUserSettingsCommand(person_id=person.id, language=selected)
    )
    await target_message.edit_text(
        translate(selected, "language_saved"),
        reply_markup=settings_keyboard(selected),
    )
    await target_message.answer(
        translate(selected, "main_menu"), reply_markup=main_menu(selected)
    )
    await target_message.answer(
        translate(selected, "main_menu_prompt"),
        reply_markup=main_menu_inline_keyboard(selected),
    )
    await callback.answer()


@router.callback_query(F.data == "settings:close")
async def close_settings(
    callback: CallbackQuery,
    state: FSMContext,
    services: Services,
    language: Language,
) -> None:
    """Clear settings input state and return to the main reply menu."""
    if callback.from_user is None:
        return
    target_message = callback_message(callback)
    settings = await services.user_settings.find_by_telegram_id(callback.from_user.id)
    if settings is None or settings.timezone is None:
        await state.set_state(OnboardingStates.timezone)
        await target_message.edit_text(
            translate(language, "onboarding_timezone_required"),
            reply_markup=timezone_keyboard(language, include_back=False),
        )
        await callback.answer()
        return
    await state.clear()
    await target_message.edit_text(
        translate(language, "main_menu_prompt"),
        reply_markup=main_menu_inline_keyboard(language),
    )
    await callback.answer()


def _settings_text(settings: UserSettingsDTO, display_language: Language) -> str:
    """Render current user settings in the selected display language."""
    return translate(
        display_language,
        "settings_title",
        currency=escape(settings.default_currency),
        language=escape(language_name(settings.language, display_language)),
        timezone=escape(timezone_label(settings.timezone, display_language)),
    )
