"""Entry point: python -m bot"""

import asyncio
import contextlib
import logging

from aiogram import Bot
from aiogram.types import BotCommand, MenuButtonWebApp, WebAppInfo

from bot import strings
from bot.app import build_dispatcher
from bot.config import load_settings
from bot.db.session import init_db, make_engine, make_sessionmaker
from bot.jobs import create_missing_matches_once, run_expiry_loop
from webapp.server import build_web_app, start_web_server


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings = load_settings()

    engine = make_engine(settings.database_url)
    await init_db(engine)
    sessionmaker = make_sessionmaker(engine)

    bot = Bot(token=settings.bot_token)
    dispatcher = build_dispatcher()
    # The menu Telegram shows next to the message field.
    await bot.set_my_commands(
        [BotCommand(command=name, description=text) for name, text in strings.COMMANDS.items()]
    )
    if settings.webapp_url:
        # The button next to the message field opens the Mini App. It is set
        # only when WEBAPP_URL is given, so running on the laptop leaves it alone.
        await bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(
                text=strings.WEBAPP_MENU_BUTTON, web_app=WebAppInfo(url=settings.webapp_url)
            )
        )
    # The bot's @username, for the invite link in the Mini App.
    me = await bot.get_me()
    web_app = build_web_app(
        bot,
        sessionmaker,
        settings.admin_id_list,
        dev_user_id=settings.dev_user_id,
        bot_username=me.username,
    )
    web_runner = await start_web_server(web_app, settings.web_host, settings.web_port)
    logging.info("Mini App server on http://%s:%s", settings.web_host, settings.web_port)

    await create_missing_matches_once(bot, sessionmaker)
    expiry_task = asyncio.create_task(run_expiry_loop(bot, sessionmaker))
    try:
        # Polling: the bot asks Telegram for new messages. No public server needed.
        # Extra keyword arguments become available to middlewares and handlers.
        await dispatcher.start_polling(
            bot,
            sessionmaker=sessionmaker,
            admin_ids=settings.admin_id_list,
            webapp_url=settings.webapp_url,
        )
    finally:
        expiry_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await expiry_task
        await web_runner.cleanup()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
