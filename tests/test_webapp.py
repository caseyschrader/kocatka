"""The Mini App web server, called the way Telegram's built-in browser calls it."""

import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import pytest
from aiohttp.test_utils import TestClient, TestServer
from pydantic import ValidationError

from bot import strings
from bot.config import Settings
from webapp.auth import user_id_from_init_data
from webapp.server import build_web_app

NOW = datetime(2026, 11, 22, 12, 0, tzinfo=timezone.utc)


def signed_init_data(
    token: str, user_id: int, first_name: str = "Аня", auth_date: datetime | None = None
) -> str:
    """initData as Telegram would sign it for this user."""
    when = auth_date or datetime.now(timezone.utc)
    fields = {
        "auth_date": str(int(when.timestamp())),
        "query_id": "AAHtest",
        "user": json.dumps({"id": user_id, "first_name": first_name}, ensure_ascii=False),
    }
    check_string = "\n".join(f"{key}={value}" for key, value in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


@pytest.fixture
async def web(sessionmaker, bot, admins):
    """Factory for a test client of the web server: `await web()`."""
    clients = []

    async def make(dev_user_id: int | None = None) -> TestClient:
        app = build_web_app(bot, sessionmaker, admins, dev_user_id=dev_user_id)
        client = TestClient(TestServer(app))
        await client.start_server()
        clients.append(client)
        return client

    yield make
    for client in clients:
        await client.close()


def login(bot, user_id: int, **kwargs) -> dict:
    return {"Authorization": "tma " + signed_init_data(bot.token, user_id, **kwargs)}


# --- signature check ---


def test_valid_init_data_gives_user_id(bot):
    init_data = signed_init_data(bot.token, 42, auth_date=NOW - timedelta(hours=1))

    assert user_id_from_init_data(bot.token, init_data, now=NOW) == 42


def test_init_data_signed_with_another_token_is_rejected(bot):
    init_data = signed_init_data("999:OTHER", 42, auth_date=NOW)

    assert user_id_from_init_data(bot.token, init_data, now=NOW) is None


def test_changed_init_data_is_rejected(bot):
    init_data = signed_init_data(bot.token, 42, auth_date=NOW)
    forged = init_data.replace("%22id%22%3A+42", "%22id%22%3A+43")
    assert forged != init_data

    assert user_id_from_init_data(bot.token, forged, now=NOW) is None


def test_old_init_data_is_rejected(bot):
    init_data = signed_init_data(bot.token, 42, auth_date=NOW - timedelta(hours=25))

    assert user_id_from_init_data(bot.token, init_data, now=NOW) is None


def test_empty_init_data_is_rejected(bot):
    assert user_id_from_init_data(bot.token, "", now=NOW) is None


# --- endpoints ---


async def test_page_is_served_without_cache(web):
    client = await web()

    response = await client.get("/")

    assert response.status == 200
    assert response.headers["Cache-Control"] == "no-cache"
    assert "telegram-web-app.js" in await response.text()


async def test_script_is_served(web):
    client = await web()

    response = await client.get("/static/app.js")

    assert response.status == 200


async def test_strings_need_no_login(web):
    client = await web()

    response = await client.get("/api/strings")

    assert response.status == 200
    assert await response.json() == strings.WEBAPP


async def test_me_without_login_is_refused(web):
    client = await web()

    response = await client.get("/api/me")

    assert response.status == 401


async def test_me_with_forged_login_is_refused(web):
    client = await web()
    headers = {"Authorization": "tma " + signed_init_data("999:OTHER", 42)}

    response = await client.get("/api/me", headers=headers)

    assert response.status == 401


async def test_me_for_registered_user(web, bot, chat):
    await chat.register()
    client = await web()

    response = await client.get("/api/me", headers=login(bot, chat.user_id))

    assert response.status == 200
    assert await response.json() == {"first_name": "Аня", "has_profile": True}


async def test_me_for_user_without_profile(web, bot):
    client = await web()

    response = await client.get("/api/me", headers=login(bot, 777))

    assert await response.json() == {"first_name": None, "has_profile": False}


async def test_banned_user_is_refused(web, bot, chat, admin):
    await chat.register()
    await admin.send_text(f"/ban {chat.user_id}")
    client = await web()

    response = await client.get("/api/me", headers=login(bot, chat.user_id))

    assert response.status == 403
    assert await response.json() == {"error": "banned"}


async def test_dev_mode_acts_as_dev_user_without_login(web, chat):
    await chat.register()
    client = await web(dev_user_id=chat.user_id)

    response = await client.get("/api/me")

    assert (await response.json())["has_profile"] is True


# --- settings ---


def test_settings_refuse_dev_mode_off_localhost():
    with pytest.raises(ValidationError, match="DEV_USER_ID"):
        Settings(_env_file=None, bot_token="x", dev_user_id=1, web_host="0.0.0.0")


def test_settings_allow_dev_mode_on_localhost():
    settings = Settings(_env_file=None, bot_token="x", dev_user_id=1)

    assert settings.dev_user_id == 1


def test_settings_require_https_webapp_url():
    with pytest.raises(ValidationError, match="https"):
        Settings(_env_file=None, bot_token="x", webapp_url="http://example.com")


def test_settings_strip_trailing_slash_from_webapp_url():
    settings = Settings(_env_file=None, bot_token="x", webapp_url="https://example.com/")

    assert settings.webapp_url == "https://example.com"
