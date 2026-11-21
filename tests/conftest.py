"""Test helpers: a fake Telegram connection and a scripted chat partner.

Tests feed Telegram-shaped updates into the real dispatcher, so filters, state
and middleware are all exercised. Nothing touches the network.
"""

import itertools
from datetime import datetime, timezone

import pytest
from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.methods import SendMediaGroup, SendMessage, SendPhoto
from aiogram.types import Chat, Message

from bot.app import build_dispatcher
from bot.db.session import init_db, make_engine, make_sessionmaker

# Routers can only be attached once, so the dispatcher is built once for all tests.
# Each test gets its own database and its own user id, which keeps them isolated.
_dispatcher = build_dispatcher()
_ids = itertools.count(1000)


class FakeSession(BaseSession):
    """Records every call the bot makes instead of sending it to Telegram."""

    def __init__(self) -> None:
        super().__init__()
        self.calls = []

    async def close(self) -> None:
        pass

    async def make_request(self, bot, method, timeout=None):
        self.calls.append(method)
        if not isinstance(method, (SendMessage, SendPhoto, SendMediaGroup)):
            return True
        message = Message(
            message_id=next(_ids),
            date=datetime.now(timezone.utc),
            chat=Chat(id=method.chat_id, type="private"),
        )
        if isinstance(method, SendMediaGroup):
            return [message]
        return message

    async def stream_content(self, *args, **kwargs):
        yield b""


class FakeChat:
    """One Telegram user talking to the bot."""

    def __init__(self, sessionmaker, first_name: str = "Аня") -> None:
        self.user_id = next(_ids)
        self.first_name = first_name
        self.sessionmaker = sessionmaker
        self.network = FakeSession()
        self.bot = Bot(token="123456:TEST", session=self.network)

    # --- what the user does ---

    async def send_text(self, text: str) -> None:
        await self._feed({"message": self._message(text=text)})

    async def send_photo(self, file_id: str) -> None:
        sizes = [
            {"file_id": f"{file_id}-small", "file_unique_id": "s", "width": 90, "height": 90},
            {"file_id": file_id, "file_unique_id": "l", "width": 800, "height": 800},
        ]
        await self._feed({"message": self._message(photo=sizes)})

    async def send_sticker(self) -> None:
        sticker = {
            "file_id": "st",
            "file_unique_id": "st",
            "type": "regular",
            "width": 512,
            "height": 512,
            "is_animated": False,
            "is_video": False,
        }
        await self._feed({"message": self._message(sticker=sticker)})

    async def press(self, callback_data: str) -> None:
        bot_message = self._message(text="...")
        bot_message["from"] = {"id": 123456, "is_bot": True, "first_name": "Bot"}
        await self._feed(
            {
                "callback_query": {
                    "id": str(next(_ids)),
                    "from": self._user(),
                    "chat_instance": "test",
                    "data": callback_data,
                    "message": bot_message,
                }
            }
        )

    # --- what the bot answered ---

    @property
    def texts(self) -> list[str]:
        return [call.text for call in self.network.calls if isinstance(call, SendMessage)]

    @property
    def last_text(self) -> str:
        return self.texts[-1]

    @property
    def photos(self) -> list[SendPhoto]:
        return [call for call in self.network.calls if isinstance(call, SendPhoto)]

    @property
    def albums(self) -> list[SendMediaGroup]:
        return [call for call in self.network.calls if isinstance(call, SendMediaGroup)]

    @property
    def shown_ids(self) -> list[int]:
        """User ids of every browsing card shown, read from the Like buttons."""
        ids = []
        for call in self.network.calls:
            markup = getattr(call, "reply_markup", None)
            if markup is None:
                continue
            data = markup.inline_keyboard[0][0].callback_data
            if data.startswith("swipe:like:"):
                ids.append(int(data.split(":")[2]))
        return ids

    async def register(
        self,
        gender: str = "female",
        pref: str = "men",
        age: str = "27",
        age_range: str = "18-99",
        photos: int = 1,
    ) -> None:
        """Goes through the whole onboarding as this user."""
        await self.send_text("/start")
        await self.press("adult:yes")
        await self.press("consent:yes")
        await self.press(f"gender:{gender}")
        await self.press(f"pref:{pref}")
        await self.send_text(age)
        await self.send_text(age_range)
        await self.press("city:spb")
        await self.send_text(f"О себе: {self.first_name}")
        for n in range(photos):
            await self.send_photo(f"{self.first_name}-photo-{n}")
        if photos < 3:
            await self.press("photos:done")

    # --- plumbing ---

    def _user(self) -> dict:
        return {"id": self.user_id, "is_bot": False, "first_name": self.first_name}

    def _message(self, **content) -> dict:
        return {
            "message_id": next(_ids),
            "date": int(datetime.now(timezone.utc).timestamp()),
            "chat": {"id": self.user_id, "type": "private"},
            "from": self._user(),
            **content,
        }

    async def _feed(self, update: dict) -> None:
        update["update_id"] = next(_ids)
        await _dispatcher.feed_raw_update(
            self.bot, update, sessionmaker=self.sessionmaker
        )


@pytest.fixture
async def sessionmaker(tmp_path):
    engine = make_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    await init_db(engine)
    yield make_sessionmaker(engine)
    await engine.dispose()


@pytest.fixture
def chat(sessionmaker) -> FakeChat:
    return FakeChat(sessionmaker)


@pytest.fixture
def new_chat(sessionmaker):
    """Factory for tests that need several users: new_chat("Олег")."""
    return lambda first_name: FakeChat(sessionmaker, first_name=first_name)
