"""Analytics events. No Telegram code here.

log_event only adds the row; the caller's commit saves it together with the
change it describes, so an event never exists without its action or vice versa.
"""

import secrets
from datetime import datetime

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Event, utcnow

EVENT_TYPES = frozenset({
    # Onboarding. Started and stopped happen before consent, so they carry no user id.
    "signup_started",
    "signup_stopped",
    "signup_completed",
    "profile_updated",
    # Browsing and matching
    "profile_viewed",
    "like",
    "pass",
    "match_created",
    "first_message_sent",
    "message_sent",
    "match_expired",
    "match_closed",
    # Safety
    "report",
    "block",
    "user_banned",
    "user_unbanned",
    "account_deleted",
})


def log_event(
    session: AsyncSession,
    event_type: str,
    user_id: int | None = None,
    target_id: int | None = None,
    now: datetime | None = None,
    **properties,
) -> None:
    if event_type not in EVENT_TYPES:
        raise ValueError(f"unknown event type: {event_type}")
    session.add(
        Event(
            event_type=event_type,
            user_id=user_id,
            target_id=target_id,
            ts=now or utcnow(),
            properties=properties,
        )
    )


async def anonymise_user(session: AsyncSession, user_id: int) -> int:
    """Replaces a user's Telegram id in all events with a random negative number.

    The history stays usable for retention and conversion numbers, but can no
    longer be linked to the person. Returns the new pseudonym. Does not commit.
    """
    pseudonym = -(secrets.randbelow(2**62) + 1)
    await session.execute(
        update(Event).where(Event.user_id == user_id).values(user_id=pseudonym)
    )
    await session.execute(
        update(Event).where(Event.target_id == user_id).values(target_id=pseudonym)
    )
    return pseudonym
