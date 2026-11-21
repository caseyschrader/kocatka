"""Blocks, reports and bans. No Telegram code here."""

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Ban, Block, Match, Report
from bot.services.events import log_event
from bot.services.matching import ACTIVE, CLOSED, PENDING

REPORT_REASONS = ("fake", "rude", "explicit", "minor", "other")


async def _close_matches(session: AsyncSession, reason: str, *conditions) -> None:
    result = await session.execute(
        update(Match)
        .where(Match.status.in_((PENDING, ACTIVE)), *conditions)
        .values(status=CLOSED)
        .returning(Match.id, Match.user_a, Match.user_b)
        .execution_options(synchronize_session=False)
    )
    for match_id, user_a, user_b in result.all():
        log_event(session, "match_closed", user_a, user_b, match_id=match_id, reason=reason)


async def block(
    session: AsyncSession, blocker_id: int, blocked_id: int, via_report: bool = False
) -> None:
    """Blocks someone and closes any match between the two. Safe to repeat."""
    if blocker_id == blocked_id:
        raise ValueError("cannot block yourself")
    exists = await session.scalar(
        select(Block.id).where(Block.blocker_id == blocker_id, Block.blocked_id == blocked_id)
    )
    if exists is None:
        session.add(Block(blocker_id=blocker_id, blocked_id=blocked_id))
        log_event(session, "block", blocker_id, blocked_id, via_report=via_report)
    user_a, user_b = sorted((blocker_id, blocked_id))
    reason = "report" if via_report else "block"
    await _close_matches(session, reason, Match.user_a == user_a, Match.user_b == user_b)
    await session.commit()


async def is_blocked_either_way(session: AsyncSession, user_1: int, user_2: int) -> bool:
    found = await session.scalar(
        select(Block.id).where(
            or_(
                (Block.blocker_id == user_1) & (Block.blocked_id == user_2),
                (Block.blocker_id == user_2) & (Block.blocked_id == user_1),
            )
        )
    )
    return found is not None


async def report(session: AsyncSession, reporter_id: int, reported_id: int, reason: str) -> None:
    """Saves a report. Reporting also blocks, so the reporter is left alone."""
    if reason not in REPORT_REASONS:
        raise ValueError(f"unknown reason: {reason}")
    session.add(Report(reporter_id=reporter_id, reported_id=reported_id, reason=reason))
    log_event(session, "report", reporter_id, reported_id, reason=reason)
    await block(session, reporter_id, reported_id, via_report=True)


async def is_banned(session: AsyncSession, user_id: int) -> bool:
    return await session.get(Ban, user_id) is not None


async def ban(session: AsyncSession, user_id: int, admin_id: int, reason: str = "") -> bool:
    """Bans a user and closes all their matches. Returns False if already banned."""
    if await is_banned(session, user_id):
        return False
    session.add(Ban(user_id=user_id, banned_by=admin_id, reason=reason[:200]))
    log_event(session, "user_banned", user_id)
    await _close_matches(session, "ban", or_(Match.user_a == user_id, Match.user_b == user_id))
    await session.commit()
    return True


async def unban(session: AsyncSession, user_id: int) -> bool:
    found = await session.get(Ban, user_id)
    if found is None:
        return False
    await session.delete(found)
    log_event(session, "user_unbanned", user_id)
    await session.commit()
    return True
