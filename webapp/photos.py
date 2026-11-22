"""Profile photos for the Mini App.

Photos stay in Telegram; we only store their file ids. The server fetches the
image from Telegram when the page asks and passes it on, without keeping a copy,
so /delete_me stays complete.

An <img> tag cannot send the login header, so each card comes with photo links
that carry their own signature and expire after an hour. Only the server can
make such a link, so nobody can load photos by guessing numbers.
"""

import hashlib
import hmac
from datetime import datetime, timedelta

from aiogram import Bot

from bot.db.models import utcnow

LINK_LIFETIME = timedelta(hours=1)


def _key(token: str) -> bytes:
    # A key of its own, derived from the bot token, so photo links can never
    # be mistaken for Telegram's login signature or the other way round.
    return hmac.new(b"KocatkaPhotoLink", token.encode(), hashlib.sha256).digest()


def _signature(token: str, photo_id: int, expires: int) -> str:
    message = f"{photo_id}:{expires}".encode()
    return hmac.new(_key(token), message, hashlib.sha256).hexdigest()


def photo_url(token: str, photo_id: int, now: datetime | None = None) -> str:
    expires = int(((now or utcnow()) + LINK_LIFETIME).timestamp())
    return f"/api/photo/{photo_id}?exp={expires}&sig={_signature(token, photo_id, expires)}"


def link_is_valid(
    token: str, photo_id: int, expires: str, signature: str, now: datetime | None = None
) -> bool:
    if not expires.isdecimal():
        return False
    if int(expires) < (now or utcnow()).timestamp():
        return False
    expected = _signature(token, photo_id, int(expires))
    return hmac.compare_digest(expected, signature)


async def fetch_from_telegram(bot: Bot, file_id: str) -> bytes:
    file = await bot.get_file(file_id)
    data = await bot.download_file(file.file_path)
    return data.read()
