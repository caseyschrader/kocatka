"""Catch-alls for anything no other handler took. Must be registered last."""

from aiogram import Router
from aiogram.types import CallbackQuery, Message

from bot import strings

router = Router()


@router.callback_query()
async def on_stale_button(callback: CallbackQuery) -> None:
    await callback.answer(strings.STALE_BUTTON)


@router.message()
async def on_unknown_message(message: Message) -> None:
    await message.answer(strings.UNKNOWN)
