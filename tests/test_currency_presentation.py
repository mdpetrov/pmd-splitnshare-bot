"""Verify discovery and rejection of currencies through Telegram settings."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from aiogram.types import CallbackQuery, Chat, Message, User

from splitnshare.domain.currencies import CURRENCY_EXPONENTS
from splitnshare.domain.enums import Language
from splitnshare.domain.errors import ValidationError
from splitnshare.presentation.keyboards import currency_keyboard
from splitnshare.presentation.routers.settings import set_currency, show_supported_currencies


@pytest.mark.parametrize("language", list(Language))
async def test_currency_help_lists_supported_codes_and_precisions(language):
    message = SimpleNamespace(answer=AsyncMock())
    await show_supported_currencies(message, language)
    text = message.answer.call_args.args[0]
    assert len(text) < 4096
    assert all(code in text for code in CURRENCY_EXPONENTS)
    assert "KRW" in text.split("</b>")[2]
    assert "TND" in text.split("</b>")[-1]
    assert "ZZZ" not in text


def test_currency_presets_are_all_supported():
    for row in currency_keyboard(Language.ENGLISH).inline_keyboard:
        for button in row:
            if button.callback_data and button.callback_data.startswith("settings:set_currency:"):
                assert button.callback_data.rsplit(":", 1)[1] in CURRENCY_EXPONENTS


async def test_unsupported_currency_callback_reports_error_without_editing():
    user = User(id=123, is_bot=False, first_name="Person")
    callback = CallbackQuery(
        id="test", from_user=user, chat_instance="test",
        message=Message(
            message_id=1, date=datetime.now(UTC), chat=Chat(id=123, type="private"),
        ),
        data="settings:set_currency:ZZZ",
    )
    services = SimpleNamespace(
        users=SimpleNamespace(find_registered_target=AsyncMock(
            return_value=SimpleNamespace(id=uuid4()),
        )),
        user_settings=SimpleNamespace(update=AsyncMock(side_effect=ValidationError("Unsupported"))),
    )
    with patch.object(CallbackQuery, "answer", new_callable=AsyncMock) as answer:
        await set_currency(callback, services, Language.ENGLISH)
    assert "Unsupported currency" in answer.call_args.args[0]
    assert answer.call_args.kwargs["show_alert"] is True
