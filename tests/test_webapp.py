"""The Mini App web server, called the way Telegram's built-in browser calls it."""

import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import pytest
from aiohttp.test_utils import TestClient, TestServer
from pydantic import ValidationError

from sqlalchemy import select

from bot import strings
from bot.config import Settings
from bot.db.models import Block, Event, Report
from webapp.auth import user_id_from_init_data
from webapp.photos import link_is_valid, photo_url
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


async def fake_fetch(bot, file_id: str) -> bytes:
    """Stands in for downloading a photo from Telegram."""
    return f"image:{file_id}".encode()


@pytest.fixture
async def web(sessionmaker, bot, admins):
    """Factory for a test client of the web server: `await web()`."""
    clients = []

    async def make(dev_user_id: int | None = None) -> TestClient:
        app = build_web_app(
            bot,
            sessionmaker,
            admins,
            dev_user_id=dev_user_id,
            photo_fetcher=fake_fetch,
            bot_username="KocatkaTestBot",
        )
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
    assert await response.json() == {
        "first_name": "Аня",
        "has_profile": True,
        "bot_username": "KocatkaTestBot",
    }


async def test_me_for_user_without_profile(web, bot):
    client = await web()

    response = await client.get("/api/me", headers=login(bot, 777))

    assert await response.json() == {
        "first_name": None,
        "has_profile": False,
        "bot_username": "KocatkaTestBot",
    }


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


# --- browsing ---


@pytest.fixture
async def anya(chat):
    await chat.register(gender="female", pref="men")
    return chat


@pytest.fixture
async def oleg(new_chat):
    man = new_chat("Олег")
    await man.register(gender="male", pref="women", photos=2)
    return man


async def test_next_needs_a_profile(web, bot):
    client = await web()

    response = await client.get("/api/next", headers=login(bot, 777))

    assert response.status == 409
    assert await response.json() == {"error": "no_profile"}


async def test_next_shows_a_matching_card(web, bot, anya, oleg, sessionmaker):
    client = await web()

    response = await client.get("/api/next", headers=login(bot, anya.user_id))

    card = (await response.json())["card"]
    assert card["user_id"] == oleg.user_id
    assert card["name"] == "Олег"
    assert card["age"] == 27
    assert card["bio"] == "О себе: Олег"
    assert len(card["photos"]) == 2
    assert all(url.startswith("/api/photo/") and "sig=" in url for url in card["photos"])
    async with sessionmaker() as session:
        viewed = await session.scalar(
            select(Event).where(Event.event_type == "profile_viewed", Event.user_id == anya.user_id)
        )
    assert viewed.target_id == oleg.user_id
    assert viewed.properties == {"source": "app"}


async def test_next_is_empty_when_nobody_is_left(web, bot, anya):
    client = await web()

    response = await client.get("/api/next", headers=login(bot, anya.user_id))

    assert await response.json() == {"card": None}


async def test_like_without_match(web, bot, anya, oleg, sessionmaker):
    client = await web()

    response = await client.post(
        "/api/swipe",
        json={"target_id": oleg.user_id, "action": "like"},
        headers=login(bot, anya.user_id),
    )

    assert await response.json() == {"recorded": True, "match": None}
    async with sessionmaker() as session:
        like = await session.scalar(select(Event).where(Event.event_type == "like"))
    assert (like.user_id, like.target_id, like.properties) == (
        anya.user_id,
        oleg.user_id,
        {"source": "app"},
    )


async def test_mutual_like_in_app_creates_match_and_tells_both_in_chat(web, bot, anya, oleg):
    await oleg.send_text("/browse")
    await oleg.press(f"swipe:like:{anya.user_id}")
    client = await web()

    response = await client.post(
        "/api/swipe",
        json={"target_id": oleg.user_id, "action": "like"},
        headers=login(bot, anya.user_id),
    )

    assert await response.json() == {"recorded": True, "match": {"name": "Олег"}}
    assert strings.MATCH_YOU_WRITE_FIRST.format(name="Олег") in anya.texts
    assert strings.MATCH_SHE_WRITES_FIRST.format(name="Аня") in oleg.texts


async def test_same_card_answered_twice_is_saved_once(web, bot, anya, oleg):
    client = await web()
    body = {"target_id": oleg.user_id, "action": "pass"}

    await client.post("/api/swipe", json=body, headers=login(bot, anya.user_id))
    response = await client.post("/api/swipe", json=body, headers=login(bot, anya.user_id))

    assert await response.json() == {"recorded": False, "match": None}


@pytest.mark.parametrize(
    "body",
    [
        {"target_id": 5, "action": "superlike"},
        {"target_id": "5", "action": "like"},
        {"target_id": True, "action": "like"},
        {"action": "like"},
        [],
    ],
)
async def test_swipe_rejects_bad_requests(web, bot, anya, body):
    client = await web()

    response = await client.post("/api/swipe", json=body, headers=login(bot, anya.user_id))

    assert response.status == 400


async def test_swipe_on_yourself_is_rejected(web, bot, anya):
    client = await web()

    response = await client.post(
        "/api/swipe",
        json={"target_id": anya.user_id, "action": "like"},
        headers=login(bot, anya.user_id),
    )

    assert response.status == 400


async def test_swipe_after_being_blocked_is_not_saved(web, bot, anya, oleg):
    await oleg.press(f"blockyes:{anya.user_id}")
    client = await web()

    response = await client.post(
        "/api/swipe",
        json={"target_id": oleg.user_id, "action": "like"},
        headers=login(bot, anya.user_id),
    )

    assert await response.json() == {"recorded": False, "match": None}


# --- report and block ---


async def test_report_saves_blocks_and_tells_admins(web, bot, anya, oleg, admin, sessionmaker):
    client = await web()

    response = await client.post(
        "/api/report",
        json={"target_id": oleg.user_id, "reason": "fake"},
        headers=login(bot, anya.user_id),
    )

    assert await response.json() == {"ok": True}
    async with sessionmaker() as session:
        report = await session.scalar(select(Report))
        block = await session.scalar(select(Block))
    assert (report.reporter_id, report.reported_id, report.reason) == (
        anya.user_id,
        oleg.user_id,
        "fake",
    )
    assert (block.blocker_id, block.blocked_id) == (anya.user_id, oleg.user_id)
    assert any("Жалоба" in text for text in admin.texts)
    assert f"ban:{oleg.user_id}" in admin.buttons


async def test_report_rejects_unknown_reason(web, bot, anya, oleg):
    client = await web()

    response = await client.post(
        "/api/report",
        json={"target_id": oleg.user_id, "reason": "boring"},
        headers=login(bot, anya.user_id),
    )

    assert response.status == 400


async def test_report_of_unknown_user_is_not_found(web, bot, anya):
    client = await web()

    response = await client.post(
        "/api/report",
        json={"target_id": 999999, "reason": "fake"},
        headers=login(bot, anya.user_id),
    )

    assert response.status == 404


async def test_blocked_profile_is_not_shown_again(web, bot, anya, oleg):
    client = await web()

    response = await client.post(
        "/api/block", json={"target_id": oleg.user_id}, headers=login(bot, anya.user_id)
    )
    after = await client.get("/api/next", headers=login(bot, anya.user_id))

    assert await response.json() == {"ok": True}
    assert await after.json() == {"card": None}


# --- photos ---


async def _first_card(client, bot, viewer) -> dict:
    response = await client.get("/api/next", headers=login(bot, viewer.user_id))
    return (await response.json())["card"]


async def test_photo_link_from_card_serves_the_image(web, bot, anya, oleg):
    client = await web()
    card = await _first_card(client, bot, anya)

    response = await client.get(card["photos"][1])

    assert response.status == 200
    assert response.content_type == "image/jpeg"
    assert await response.read() == "image:Олег-photo-1".encode()
    assert response.headers["Cache-Control"] == "private, max-age=3600"


async def test_photo_with_changed_signature_is_refused(web, bot, anya, oleg):
    client = await web()
    card = await _first_card(client, bot, anya)

    response = await client.get(card["photos"][0][:-4] + "0000")

    assert response.status == 403


async def test_photo_link_cannot_be_moved_to_another_photo(web, bot):
    client = await web()
    url = photo_url(bot.token, 1)

    response = await client.get(url.replace("/api/photo/1?", "/api/photo/2?"))

    assert response.status == 403


async def test_photo_of_banned_user_is_not_served(web, bot, anya, oleg, admin):
    client = await web()
    card = await _first_card(client, bot, anya)
    await admin.send_text(f"/ban {oleg.user_id}")

    response = await client.get(card["photos"][0])

    assert response.status == 404


def test_photo_link_expires_after_an_hour(bot):
    url = photo_url(bot.token, 7, now=NOW)
    expires = url.split("exp=")[1].split("&")[0]
    signature = url.split("sig=")[1]

    assert link_is_valid(bot.token, 7, expires, signature, now=NOW + timedelta(minutes=59))
    assert not link_is_valid(bot.token, 7, expires, signature, now=NOW + timedelta(minutes=61))


# --- /browse offers the app ---


async def test_browse_offers_the_app_when_it_is_set_up(anya, oleg):
    anya.webapp_url = "https://example.com"

    await anya.send_text("/browse")

    assert anya.last_text == strings.BROWSE_IN_APP
    assert anya.shown_ids == []
    assert "browse:chat" in anya.buttons


async def test_browse_in_chat_button_shows_a_card(anya, oleg):
    anya.webapp_url = "https://example.com"
    await anya.send_text("/browse")

    await anya.press("browse:chat")

    assert anya.shown_ids == [oleg.user_id]
