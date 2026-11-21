"""Entry point: python -m bot"""

import asyncio
import logging

from aiogram import Bot, Dispatcher

from bot.config import load_settings
from bot.handlers import build_router


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings = load_settings()

    bot = Bot(token=settings.bot_token)
    dispatcher = Dispatcher()
    dispatcher.include_router(build_router())

    # Polling: the bot asks Telegram for new messages. No public server needed.
    await dispatcher.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
