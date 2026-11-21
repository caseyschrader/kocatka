"""Entry point: python -m bot"""

import asyncio
import logging

from aiogram import Bot

from bot.app import build_dispatcher
from bot.config import load_settings
from bot.db.session import init_db, make_engine, make_sessionmaker


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings = load_settings()

    engine = make_engine(settings.database_url)
    await init_db(engine)

    bot = Bot(token=settings.bot_token)
    dispatcher = build_dispatcher()
    try:
        # Polling: the bot asks Telegram for new messages. No public server needed.
        # Extra keyword arguments become available to middlewares and handlers.
        await dispatcher.start_polling(bot, sessionmaker=make_sessionmaker(engine))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
