"""The Mini App web server. It runs inside the bot process and shares its database.

Routes:
    GET /              the page (static/index.html)
    GET /static/...    its script and styles
    GET /api/strings   the page's Russian text, from bot/strings.py (no login needed)
    GET /api/me        who is logged in and whether they have a profile
"""

from pathlib import Path

from aiogram import Bot
from aiohttp import web
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot import strings
from bot.db.models import User
from bot.services import profiles, safety
from webapp.auth import user_id_from_header

STATIC = Path(__file__).parent / "static"

BOT = web.AppKey("bot", Bot)
SESSIONMAKER = web.AppKey("sessionmaker", async_sessionmaker)
ADMIN_IDS = web.AppKey("admin_ids", list)
DEV_USER_ID = web.AppKey("dev_user_id", object)
# Set on each /api/ request by the login middleware.
USER_ID = web.RequestKey("user_id", int)
SESSION = web.RequestKey("session", AsyncSession)

# API paths anyone may call, without Telegram's login.
PUBLIC_API = {"/api/strings"}


def _error(status: int, code: str) -> web.Response:
    return web.json_response({"error": code}, status=status)


@web.middleware
async def login_and_session(request: web.Request, handler) -> web.StreamResponse:
    """For /api/ calls: find out who is asking, stop banned users, open a database session."""
    if not request.path.startswith("/api/") or request.path in PUBLIC_API:
        return await handler(request)

    app = request.app
    user_id = app[DEV_USER_ID]
    if user_id is None:
        header = request.headers.get("Authorization", "")
        user_id = user_id_from_header(app[BOT].token, header)
    if user_id is None:
        return _error(401, "unauthorized")

    async with app[SESSIONMAKER]() as session:
        if user_id not in app[ADMIN_IDS] and await safety.is_banned(session, user_id):
            return _error(403, "banned")
        request[USER_ID] = user_id
        request[SESSION] = session
        return await handler(request)


async def index(request: web.Request) -> web.FileResponse:
    # no-cache: Telegram's built-in browser otherwise keeps showing an old page after a deploy.
    return web.FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})


async def get_strings(request: web.Request) -> web.Response:
    return web.json_response(strings.WEBAPP)


async def get_me(request: web.Request) -> web.Response:
    session = request[SESSION]
    user_id = request[USER_ID]
    user = await session.get(User, user_id)
    profile = await profiles.get_profile(session, user_id)
    return web.json_response(
        {"first_name": user.first_name if user else None, "has_profile": profile is not None}
    )


def build_web_app(
    bot: Bot,
    sessionmaker: async_sessionmaker[AsyncSession],
    admin_ids: list[int],
    dev_user_id: int | None = None,
) -> web.Application:
    app = web.Application(middlewares=[login_and_session])
    app[BOT] = bot
    app[SESSIONMAKER] = sessionmaker
    app[ADMIN_IDS] = admin_ids
    app[DEV_USER_ID] = dev_user_id
    app.router.add_get("/", index)
    app.router.add_static("/static", STATIC)
    app.router.add_get("/api/strings", get_strings)
    app.router.add_get("/api/me", get_me)
    return app


async def start_web_server(app: web.Application, host: str, port: int) -> web.AppRunner:
    """Starts serving in the background. Call `cleanup()` on the result to stop."""
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    await web.TCPSite(runner, host, port).start()
    return runner
