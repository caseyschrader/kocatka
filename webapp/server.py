"""The Mini App web server. It runs inside the bot process and shares its database.

Routes:
    GET  /                the page (static/index.html)
    GET  /static/...      its script and styles
    GET  /api/strings     the page's Russian text, from bot/strings.py (no login needed)
    GET  /api/me          who is logged in and whether they have a profile
    GET  /api/next        the next profile card, or {"card": null} when none are left
    POST /api/swipe       {"target_id", "action": "like" | "pass"}
    POST /api/report      {"target_id", "reason"}
    POST /api/block       {"target_id"}
    GET  /api/photo/{id}  a profile photo, through a signed link from a card (no login needed)
"""

import logging
from pathlib import Path

from aiogram import Bot
from aiohttp import web
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot import strings
from bot.db.models import Photo, Profile, User
from bot.handlers.matches import announce_match
from bot.handlers.safety import tell_admins
from bot.services import browsing, events, matching, profiles, safety
from webapp.auth import user_id_from_header
from webapp.photos import fetch_from_telegram, link_is_valid, photo_url

logger = logging.getLogger(__name__)

STATIC = Path(__file__).parent / "static"

BOT = web.AppKey("bot", Bot)
SESSIONMAKER = web.AppKey("sessionmaker", async_sessionmaker)
ADMIN_IDS = web.AppKey("admin_ids", list)
DEV_USER_ID = web.AppKey("dev_user_id", object)
# How photos are fetched from Telegram. Tests swap in a fake.
PHOTO_FETCHER = web.AppKey("photo_fetcher", object)
# Set on each /api/ request by the login middleware.
USER_ID = web.RequestKey("user_id", int)
SESSION = web.RequestKey("session", AsyncSession)


def _is_public(path: str) -> bool:
    """API paths that need no Telegram login. Photo links carry their own signature."""
    return path == "/api/strings" or path.startswith("/api/photo/")


def _error(status: int, code: str) -> web.Response:
    return web.json_response({"error": code}, status=status)


@web.middleware
async def login_and_session(request: web.Request, handler) -> web.StreamResponse:
    """For /api/ calls: find out who is asking, stop banned users, open a database session."""
    if not request.path.startswith("/api/") or _is_public(request.path):
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


# --- Browsing ---


def _card(token: str, profile: Profile) -> dict:
    return {
        "user_id": profile.user_id,
        "name": profile.user.first_name,
        "age": profile.age,
        "city": profile.city,
        "bio": profile.bio,
        "photos": [photo_url(token, photo.id) for photo in profile.photos],
    }


async def _read_body(request: web.Request) -> tuple[dict, int | None]:
    """The JSON body, and its target_id if that is a whole number other than the user."""
    try:
        body = await request.json()
    except ValueError:
        return {}, None
    if not isinstance(body, dict):
        return {}, None
    target_id = body.get("target_id")
    if type(target_id) is not int or target_id == request[USER_ID]:
        return body, None
    return body, target_id


async def get_next(request: web.Request) -> web.Response:
    session = request[SESSION]
    viewer = await profiles.get_profile(session, request[USER_ID])
    if viewer is None:
        return _error(409, "no_profile")
    candidate = await browsing.next_candidate(session, viewer)
    if candidate is None:
        return web.json_response({"card": None})
    events.log_event(session, "profile_viewed", viewer.user_id, candidate.user_id, source="app")
    await session.commit()
    return web.json_response({"card": _card(request.app[BOT].token, candidate)})


async def post_swipe(request: web.Request) -> web.Response:
    session = request[SESSION]
    body, target_id = await _read_body(request)
    action = body.get("action")
    if target_id is None or action not in browsing.ACTIONS:
        return _error(400, "bad_request")
    viewer_id = request[USER_ID]
    if await profiles.get_profile(session, viewer_id) is None:
        return _error(409, "no_profile")

    # The other person may have left, been banned or blocked since the card was
    # shown, or the same card was answered twice. Then nothing is saved.
    if not await browsing.can_swipe_on(session, viewer_id, target_id):
        return web.json_response({"recorded": False, "match": None})
    if not await browsing.record_swipe(session, viewer_id, target_id, action, source="app"):
        return web.json_response({"recorded": False, "match": None})

    match = None
    if action == browsing.LIKE:
        match = await matching.create_match_if_mutual(session, viewer_id, target_id)
    if match is None:
        return web.json_response({"recorded": True, "match": None})
    # Both people get the usual match message in the bot chat, with the women-first rules.
    await announce_match(request.app[BOT], session, match)
    target = await session.get(User, target_id)
    return web.json_response({"recorded": True, "match": {"name": target.first_name}})


# --- Report and block ---


async def post_report(request: web.Request) -> web.Response:
    session = request[SESSION]
    body, target_id = await _read_body(request)
    reason = body.get("reason")
    if target_id is None or reason not in safety.REPORT_REASONS:
        return _error(400, "bad_request")
    if await session.get(User, target_id) is None:
        return _error(404, "not_found")
    reporter_id = request[USER_ID]
    await safety.report(session, reporter_id, target_id, reason)
    await tell_admins(
        request.app[BOT], session, request.app[ADMIN_IDS], reporter_id, target_id, reason
    )
    return web.json_response({"ok": True})


async def post_block(request: web.Request) -> web.Response:
    session = request[SESSION]
    _, target_id = await _read_body(request)
    if target_id is None:
        return _error(400, "bad_request")
    if await session.get(User, target_id) is None:
        return _error(404, "not_found")
    await safety.block(session, request[USER_ID], target_id)
    return web.json_response({"ok": True})


# --- Photos ---


async def get_photo(request: web.Request) -> web.Response:
    app = request.app
    raw_id = request.match_info["photo_id"]
    if not raw_id.isdecimal():
        return _error(404, "not_found")
    photo_id = int(raw_id)
    query = request.query
    if not link_is_valid(app[BOT].token, photo_id, query.get("exp", ""), query.get("sig", "")):
        return _error(403, "bad_link")

    async with app[SESSIONMAKER]() as session:
        photo = await session.get(Photo, photo_id)
        if photo is None or await safety.is_banned(session, photo.user_id):
            return _error(404, "not_found")
        file_id = photo.file_id
    try:
        data = await app[PHOTO_FETCHER](app[BOT], file_id)
    except Exception:
        logger.warning("could not fetch photo %s from Telegram", photo_id, exc_info=True)
        return _error(502, "photo_unavailable")
    # private: the phone may keep it for an hour, shared caches may not.
    return web.Response(
        body=data, content_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"}
    )


def build_web_app(
    bot: Bot,
    sessionmaker: async_sessionmaker[AsyncSession],
    admin_ids: list[int],
    dev_user_id: int | None = None,
    photo_fetcher=fetch_from_telegram,
) -> web.Application:
    app = web.Application(middlewares=[login_and_session])
    app[BOT] = bot
    app[SESSIONMAKER] = sessionmaker
    app[ADMIN_IDS] = admin_ids
    app[DEV_USER_ID] = dev_user_id
    app[PHOTO_FETCHER] = photo_fetcher
    app.router.add_get("/", index)
    app.router.add_static("/static", STATIC)
    app.router.add_get("/api/strings", get_strings)
    app.router.add_get("/api/me", get_me)
    app.router.add_get("/api/next", get_next)
    app.router.add_post("/api/swipe", post_swipe)
    app.router.add_post("/api/report", post_report)
    app.router.add_post("/api/block", post_block)
    app.router.add_get("/api/photo/{photo_id}", get_photo)
    return app


async def start_web_server(app: web.Application, host: str, port: int) -> web.AppRunner:
    """Starts serving in the background. Call `cleanup()` on the result to stop."""
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    await web.TCPSite(runner, host, port).start()
    return runner
