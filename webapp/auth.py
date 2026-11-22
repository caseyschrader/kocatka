"""Checks that a Mini App request really comes from Telegram.

When Telegram opens the page, it hands it a signed string called initData that
says who the user is. The page sends it back with every request in the header
`Authorization: tma <initData>`. The signature is made with the bot token, which
only Telegram and this server know, so nobody can pretend to be someone else.
"""

from datetime import datetime, timedelta

from aiogram.utils.web_app import safe_parse_webapp_init_data

from bot.db.models import as_utc, utcnow

# Telegram signs initData when the page opens. Older than this, ask to reopen.
MAX_AGE = timedelta(hours=24)


def user_id_from_init_data(token: str, init_data: str, now: datetime | None = None) -> int | None:
    """The Telegram user id, or None if the data is missing, forged or too old."""
    try:
        data = safe_parse_webapp_init_data(token, init_data)
    except ValueError:
        return None
    if data.user is None:
        return None
    if (now or utcnow()) - as_utc(data.auth_date) > MAX_AGE:
        return None
    return data.user.id


def user_id_from_header(token: str, header: str, now: datetime | None = None) -> int | None:
    scheme, _, init_data = header.partition(" ")
    if scheme != "tma":
        return None
    return user_id_from_init_data(token, init_data, now)
