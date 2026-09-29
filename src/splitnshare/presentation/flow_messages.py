"""Render each private conversation as one durable, editable inline flow message."""

from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from dataclasses import dataclass, field
from html import escape
from html.parser import HTMLParser
from typing import Any

from aiogram import BaseMiddleware, Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    TelegramObject,
    Update,
)

from splitnshare.domain.enums import Language
from splitnshare.domain.errors import DomainError
from splitnshare.presentation.i18n import translate
from splitnshare.presentation.keyboards import main_menu_inline_keyboard

VIEW_KEY = "_flow_view"


class _HTMLPages(HTMLParser):
    """Split long HTML views into balanced pages without truncating user data."""

    def __init__(self) -> None:
        """Initialize the parser's page buffer and open-tag stack."""
        super().__init__(convert_charrefs=True)
        self.pages: list[str] = []
        self.buffer = ""
        self.tags: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Preserve trusted formatter tags and their attributes."""
        opening = self.get_starttag_text() or f"<{tag}>"
        self.buffer += opening
        self.tags.append((tag, opening))

    def handle_endtag(self, tag: str) -> None:
        """Close the formatter's current tag."""
        self.buffer += f"</{tag}>"
        if self.tags and self.tags[-1][0] == tag:
            self.tags.pop()

    def handle_data(self, data: str) -> None:
        """Split before Telegram's size limit and reopen formatting on the next page."""
        for character in data:
            encoded = escape(character, quote=False)
            closing = "".join(f"</{tag}>" for tag, _ in reversed(self.tags))
            if len(self.buffer) + len(encoded) + len(closing) > 3400:
                self.pages.append(self.buffer + closing)
                self.buffer = "".join(opening for _, opening in self.tags)
            self.buffer += encoded


def html_pages(text: str) -> list[str]:
    """Return size-bounded, independently formatted Telegram message pages."""
    parser = _HTMLPages()
    parser.feed(text)
    parser.close()
    if parser.buffer:
        parser.pages.append(parser.buffer)
    return parser.pages or ["…"]


@dataclass
class FlowView:
    """Collect one update's output and publish it as one inline message edit."""

    bot: Bot
    state: FSMContext
    chat_id: int
    language: Language
    message_id: int | None
    saved: dict[str, Any]
    parts: list[str] = field(default_factory=list)
    markup: InlineKeyboardMarkup | None = None
    markup_set: bool = False
    persist: bool = True

    async def publish(self, pages: list[str], markup: InlineKeyboardMarkup, page: int = 0) -> None:
        """Edit the existing message, replacing it only if Telegram cannot edit it."""
        page = min(max(page, 0), len(pages) - 1)
        visible_markup = markup.model_copy(deep=True)
        navigation = []
        if page:
            navigation.append(
                InlineKeyboardButton(
                    text="←",
                    callback_data=f"ui:page:{page - 1}",
                )
            )
        if page + 1 < len(pages):
            navigation.append(
                InlineKeyboardButton(
                    text="→",
                    callback_data=f"ui:page:{page + 1}",
                )
            )
        if navigation:
            visible_markup.inline_keyboard.append(navigation)
        if self.message_id is not None:
            try:
                await self.bot.edit_message_text(
                    chat_id=self.chat_id,
                    message_id=self.message_id,
                    text=pages[page],
                    reply_markup=visible_markup,
                )
            except TelegramBadRequest as exc:
                reason = exc.message.lower()
                if "message is not modified" not in reason:
                    if (
                        "message to edit not found" not in reason
                        and "can't be edited" not in reason
                    ):
                        raise
                    self.message_id = None
        if self.message_id is None:
            message = await self.bot.send_message(
                self.chat_id,
                pages[page],
                reply_markup=visible_markup,
            )
            self.message_id = message.message_id
        if self.persist:
            await self.state.update_data(
                **{
                    VIEW_KEY: {
                        "message_id": self.message_id,
                        "pages": pages,
                        "page": page,
                        "markup": markup.model_dump(mode="json", exclude_none=True),
                    }
                }
            )

    async def flush(self) -> None:
        """Combine status and prompt text while retaining navigation for input errors."""
        if not self.parts and not self.markup_set:
            return
        pages = (
            html_pages("\n\n".join(self.parts)) if self.parts else self.saved.get("pages", ["…"])
        )
        markup = self.markup
        if markup is None and not self.markup_set and await self.state.get_state() is not None:
            saved_markup = self.saved.get("markup")
            if saved_markup:
                markup = InlineKeyboardMarkup.model_validate(saved_markup)
        await self.publish(pages, markup or main_menu_inline_keyboard(self.language))


_current_view: ContextVar[FlowView | None] = ContextVar("current_flow_view", default=None)


def forget_flow() -> None:
    """Avoid recreating deleted account data while displaying its final acknowledgment."""
    view = _current_view.get()
    if view is not None:
        view.persist = False


async def show(
    message: Message,
    text: str,
    *,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    """Queue flow content without sending or changing any bottom keyboard."""
    view = _current_view.get()
    if view is None:
        await message.answer(text, reply_markup=reply_markup)
        return
    view.parts.append(text)
    if reply_markup is not None:
        view.markup, view.markup_set = reply_markup, True


async def show_markup(message: Message, *, reply_markup: InlineKeyboardMarkup | None) -> None:
    """Update flow controls without a second network edit during the same event."""
    view = _current_view.get()
    if view is None:
        await message.edit_reply_markup(reply_markup=reply_markup)
        return
    view.markup, view.markup_set = reply_markup, True


class FlowMessageMiddleware(BaseMiddleware):
    """Restore the flow message before routing and persist it after every transition."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        """Keep typed replies and callbacks on their original bot-authored message."""
        state = data.get("state")
        if not isinstance(event, Update) or not isinstance(state, FSMContext):
            return await handler(event, data)
        callback = event.callback_query
        message = event.message or (callback.message if callback else None)
        if not isinstance(message, Message) or message.chat.type != "private":
            return await handler(event, data)
        saved = (await state.get_data()).get(VIEW_KEY, {})
        message_id = saved.get("message_id")
        if (
            event.message
            and (event.message.text or "").split(" ", 1)[0].split("@", 1)[0] == "/start"
        ):
            message_id = None
        if callback:
            payload = callback.data or ""
            entry = payload.startswith(("menu:", "g:view:", "expense:view:"))
            if message_id and message.message_id != message_id and not entry:
                await callback.answer(translate(data["language"], "draft_expired"), show_alert=True)
                return None
            allowed = {
                button.get("callback_data")
                for row in saved.get("markup", {}).get("inline_keyboard", [])
                for button in row
            }
            if (
                message_id == message.message_id
                and allowed
                and payload not in allowed
                and not entry
                and not payload.startswith("ui:page:")
            ):
                await callback.answer(translate(data["language"], "draft_expired"), show_alert=True)
                return None
            message_id = message.message_id
        view = FlowView(data["bot"], state, message.chat.id, data["language"], message_id, saved)
        token = _current_view.set(view)
        try:
            if callback and callback.data and callback.data.startswith("ui:page:"):
                try:
                    page = int(callback.data.rsplit(":", 1)[1])
                    markup = InlineKeyboardMarkup.model_validate(saved["markup"])
                    await view.publish(saved["pages"], markup, page)
                except (ValueError, KeyError):
                    await callback.answer(
                        translate(view.language, "draft_expired"), show_alert=True
                    )
                    return None
                await callback.answer()
                return None
            try:
                result = await handler(event, data)
            except DomainError as exc:
                await show(message, escape(str(exc)))
                result = True
            await view.flush()
            return result
        finally:
            _current_view.reset(token)
