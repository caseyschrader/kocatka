"""Checks that run before every handler."""

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, Update

from bot import strings
from bot.services import safety


def _allowed_while_banned(event: Update) -> bool:
    """Banned people may still delete their data."""
    if event.message and event.message.text:
        return event.message.text.startswith("/delete_me")
    if event.callback_query and event.callback_query.data:
        return event.callback_query.data.startswith("delete:")
    return False


class BanMiddleware(BaseMiddleware):
    """Stops banned users at the door. Needs DbSessionMiddleware to run first."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user is None or user.id in data.get("admin_ids", []):
            return await handler(event, data)
        if not await safety.is_banned(data["session"], user.id) or _allowed_while_banned(event):
            return await handler(event, data)

        if isinstance(event, Update) and isinstance(event.event, Message):
            await event.event.answer(strings.BANNED)
        elif isinstance(event, Update) and isinstance(event.event, CallbackQuery):
            await event.event.answer(strings.BANNED, show_alert=True)
        return None
