from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User

from splitnshare.application.services import UserSettingsService
from splitnshare.domain.enums import Language


class UserSettingsMiddleware(BaseMiddleware):
    def __init__(self, settings: UserSettingsService) -> None:
        self._settings = settings

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
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
    if user is not None and user.language_code:
        code = user.language_code.split("-", 1)[0].lower()
        try:
            return Language(code)
        except ValueError:
            pass
    return Language.ENGLISH
