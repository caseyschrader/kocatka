"""Matches and the women-first rule. No Telegram code here.

Rules:
* A like in both directions creates a pending match with a 24 hour window.
* Woman and man: only the woman may write first.
* Same gender: either may write first. Whoever writes first wins (the tiebreak).
* The first message turns the match active. If nobody writes in time, it expires.
"""

from datetime import datetime, timedelta

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from bot.db.models import ChatMessage, Match, Profile, Swipe, as_utc, utcnow
from bot.services.events import log_event
from bot.services.browsing import LIKE

MATCH_WINDOW = timedelta(hours=24)

PENDING = "pending"
ACTIVE = "active"
EXPIRED = "expired"
CLOSED = "closed"  # ended by a block, report or ban

# Outcomes of trying to write.
OK = "ok"
NOT_FOUND = "not_found"
NOT_ALLOWED = "not_allowed"
TOO_LATE = "too_late"
ALREADY_STARTED = "already_started"
UNAVAILABLE = "unavailable"


def other_user(match, user_id: int) -> int:
    return match.user_b if match.user_a == user_id else match.user_a


async def create_match_if_mutual(
    session: AsyncSession, viewer_id: int, target_id: int, now: datetime | None = None
) -> Match | None:
    """Creates a match if both people liked each other and none exists yet."""
    now = now or utcnow()
    likes = await session.scalar(
        select(func.count())
        .select_from(Swipe)
        .where(
            Swipe.action == LIKE,
            or_(
                (Swipe.viewer_id == viewer_id) & (Swipe.target_id == target_id),
                (Swipe.viewer_id == target_id) & (Swipe.target_id == viewer_id),
            ),
        )
    )
    if likes != 2:
        return None

    user_a, user_b = sorted((viewer_id, target_id))
    existing = await session.scalar(
        select(Match.id).where(Match.user_a == user_a, Match.user_b == user_b)
    )
    if existing is not None:
        return None

    match = Match(
        user_a=user_a,
        user_b=user_b,
        status=PENDING,
        created_at=now,
        expires_at=now + MATCH_WINDOW,
    )
    session.add(match)
    await session.flush()  # assigns match.id
    starters = await allowed_starters(session, match)
    log_event(
        session, "match_created", user_a, user_b, now,
        match_id=match.id, same_gender=len(starters) == 2,
    )
    await session.commit()
    return match


async def create_missing_matches(
    session: AsyncSession, now: datetime | None = None
) -> list[Match]:
    """Creates matches for mutual likes that have none. Run at startup.

    Catches likes made before matching existed, or a crash between saving a
    like and creating its match. Does nothing once everything is caught up.
    """
    mine = aliased(Swipe)
    theirs = aliased(Swipe)
    pairs = await session.execute(
        select(mine.viewer_id, mine.target_id)
        .join(
            theirs,
            (theirs.viewer_id == mine.target_id) & (theirs.target_id == mine.viewer_id),
        )
        .where(
            mine.action == LIKE,
            theirs.action == LIKE,
            mine.viewer_id < mine.target_id,
            ~select(Match.id)
            .where(Match.user_a == mine.viewer_id, Match.user_b == mine.target_id)
            .exists(),
        )
    )
    created = []
    for user_a, user_b in pairs.all():
        match = await create_match_if_mutual(session, user_a, user_b, now)
        if match is not None:
            created.append(match)
    return created


async def allowed_starters(session: AsyncSession, match) -> set[int]:
    """Who may send the first message in this match."""
    rows = await session.execute(
        select(Profile.user_id, Profile.gender).where(
            Profile.user_id.in_((match.user_a, match.user_b))
        )
    )
    genders = dict(rows.all())
    if len(genders) < 2:
        return set()  # one of them deleted their profile
    if genders[match.user_a] == genders[match.user_b]:
        return {match.user_a, match.user_b}
    return {user_id for user_id, gender in genders.items() if gender == "female"}


async def get_match(session: AsyncSession, match_id: int) -> Match | None:
    return await session.get(Match, match_id, populate_existing=True)


async def check_can_start(
    session: AsyncSession, match_id: int, user_id: int, now: datetime | None = None
) -> tuple[str, Match | None]:
    """Says whether this user may write the first message right now."""
    now = now or utcnow()
    match = await get_match(session, match_id)
    if match is None or user_id not in (match.user_a, match.user_b):
        return NOT_FOUND, None
    if match.status == CLOSED:
        return UNAVAILABLE, match
    if match.status == ACTIVE:
        return ALREADY_STARTED, match
    if match.status == EXPIRED or as_utc(match.expires_at) <= now:
        return TOO_LATE, match
    if user_id not in await allowed_starters(session, match):
        return NOT_ALLOWED, match
    return OK, match


async def check_can_chat(
    session: AsyncSession, match_id: int, user_id: int, now: datetime | None = None
) -> tuple[str, Match | None]:
    """OK if the conversation is running, or if this user may start it now."""
    outcome, match = await check_can_start(session, match_id, user_id, now)
    if outcome == ALREADY_STARTED:
        return OK, match
    return outcome, match


async def record_message(
    session: AsyncSession, match_id: int, sender_id: int, recipient_id: int, length: int
) -> None:
    """Notes that a message was relayed. The text is not stored."""
    session.add(ChatMessage(match_id=match_id, sender_id=sender_id, length=length))
    log_event(session, "message_sent", sender_id, recipient_id, match_id=match_id, length=length)
    await session.commit()


async def start_conversation(
    session: AsyncSession, match_id: int, sender_id: int, now: datetime | None = None
) -> str:
    """Records the first message. Returns OK or the reason it was refused."""
    now = now or utcnow()
    outcome, match = await check_can_start(session, match_id, sender_id, now)
    if outcome != OK:
        return outcome
    created_at = as_utc(match.created_at)
    other_id = other_user(match, sender_id)

    # Conditional update: if the other person (same-gender pair) or the expiry
    # job got there a moment earlier, no row changes and we report that.
    result = await session.execute(
        update(Match)
        .where(Match.id == match_id, Match.status == PENDING, Match.expires_at > now)
        .values(status=ACTIVE, first_sender=sender_id, started_at=now)
        # Skip mirroring the change onto loaded objects: SQLite returns naive
        # datetimes, which cannot be compared in Python. get_match reloads anyway.
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        await session.commit()
        return ALREADY_STARTED
    log_event(
        session, "first_message_sent", sender_id, other_id, now,
        match_id=match_id, seconds_since_match=int((now - created_at).total_seconds()),
    )
    await session.commit()
    return OK


async def expire_due(session: AsyncSession, now: datetime | None = None) -> list:
    """Marks every pending match past its window as expired and returns them."""
    now = now or utcnow()
    result = await session.execute(
        update(Match)
        .where(Match.status == PENDING, Match.expires_at <= now)
        .values(status=EXPIRED)
        .returning(Match.id, Match.user_a, Match.user_b)
        .execution_options(synchronize_session=False)
    )
    expired = result.all()
    for match_id, user_a, user_b in expired:
        log_event(session, "match_expired", user_a, user_b, now, match_id=match_id)
    await session.commit()
    return expired


async def matches_for(session: AsyncSession, user_id: int) -> list[Match]:
    """Pending and active matches of a user, newest first."""
    result = await session.scalars(
        select(Match)
        .where(
            or_(Match.user_a == user_id, Match.user_b == user_id),
            Match.status.in_((PENDING, ACTIVE)),
        )
        .order_by(Match.created_at.desc())
    )
    return list(result.all())
