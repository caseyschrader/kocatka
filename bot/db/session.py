"""Engine and session setup, plus the middleware that hands a session to handlers."""

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from bot.db.models import Base


def make_engine(database_url: str) -> AsyncEngine:
    return create_async_engine(database_url)


def make_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def init_db(engine: AsyncEngine) -> None:
    """Creates missing tables. Alembic migrations replace this at the PostgreSQL step."""
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


class DbSessionMiddleware(BaseMiddleware):
    """Opens one database session per incoming update and passes it as `session`."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with data["sessionmaker"]() as session:
            data["session"] = session
            return await handler(event, data)
