"""Background work that runs alongside polling."""

import asyncio
import logging
from datetime import datetime

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.handlers.matches import announce_expiry, announce_match
from bot.services import matching

logger = logging.getLogger(__name__)

EXPIRY_CHECK_SECONDS = 60


async def expire_matches_once(
    bot: Bot, sessionmaker: async_sessionmaker[AsyncSession], now: datetime | None = None
) -> int:
    """Expires overdue matches, tells both people, returns how many expired."""
    async with sessionmaker() as session:
        expired = await matching.expire_due(session, now)
        for match in expired:
            await announce_expiry(bot, session, match)
    if expired:
        logger.info("expired %d matches", len(expired))
    return len(expired)


async def create_missing_matches_once(
    bot: Bot, sessionmaker: async_sessionmaker[AsyncSession]
) -> int:
    """Startup catch-up: matches for mutual likes that never got one."""
    async with sessionmaker() as session:
        created = await matching.create_missing_matches(session)
        for match in created:
            await announce_match(bot, session, match)
    if created:
        logger.info("created %d missing matches", len(created))
    return len(created)


async def run_expiry_loop(bot: Bot, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    """Checks once a minute. Also catches up on anything that expired while the bot was off."""
    while True:
        try:
            await expire_matches_once(bot, sessionmaker)
        except Exception:
            logger.exception("expiry check failed, will retry")
        await asyncio.sleep(EXPIRY_CHECK_SECONDS)
