"""Resolve each Telegram sender's saved or inferred interface language."""

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.fsm.context import FSMContext
from aiogram.types import TelegramObject, Update, User

from splitnshare.application.services import UserSettingsService
from splitnshare.domain.enums import SELECTABLE_LANGUAGES, Language
from splitnshare.presentation.i18n import button_values


class DraftNavigationMiddleware(BaseMiddleware):
    """Pause expense input before routing top-level navigation to another feature."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        """Prevent menu text from becoming an expense field while preserving its snapshot."""
        state = data.get("state")
        if not isinstance(event, Update) or not isinstance(state, FSMContext):
            return await handler(event, data)
        raw_state = data.get("raw_state")
        if not isinstance(raw_state, str):
            return await handler(event, data)
        text = event.message.text if event.message else None
        menu_values = {
            value
            for name in (
                "add_expense", "transactions", "balances", "friends", "settings", "drafts", "groups",
            )
            for value in button_values(name)
        }
        command = text.split()[0].split("@", 1)[0] if text and text.split() else None
        callback = event.callback_query.data if event.callback_query else None
        navigate = (
            text in menu_values
            or command in {"/start", "/settings", "/drafts", "/delete_account"}
            or (callback is not None and callback.startswith("menu:"))
        )
        if navigate:
            await state.clear()
            data["raw_state"] = None
        return await handler(event, data)


class UserSettingsMiddleware(BaseMiddleware):
    """Inject user settings and language into aiogram handler data."""

    def __init__(self, settings: UserSettingsService) -> None:
        """Initialize middleware with the read-only settings lookup service."""
        self._settings = settings

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        """Load saved settings when possible before dispatching an update."""
        user = data.get("event_from_user")
        language = _telegram_language(user if isinstance(user, User) else None)
        if isinstance(user, User):
            saved = await self._settings.find_by_telegram_id(user.id)
            if saved is not None:
                language = saved.language
                data["user_settings"] = saved
        data["language"] = language
        return await handler(event, data)


def _telegram_language(user: User | None) -> Language:
    """Infer a supported language from Telegram profile metadata."""
    if user is not None and user.language_code:
        code = user.language_code.split("-", 1)[0].lower()
        try:
            language = Language(code)
        except ValueError:
            pass
        else:
            if language in SELECTABLE_LANGUAGES:
                return language
    return Language.ENGLISH
