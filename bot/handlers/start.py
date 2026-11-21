from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from bot import strings

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(strings.WELCOME)
