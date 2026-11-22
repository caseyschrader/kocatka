"""Candidate selection and swipes. No Telegram code here."""

from sqlalchemy import exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from bot.db.models import Ban, Block, Profile, Swipe
from bot.services.events import log_event

LIKE = "like"
PASS = "pass"
ACTIONS = (LIKE, PASS)

# Which genders a preference covers.
_WANTED_GENDERS = {
    "women": ("female",),
    "men": ("male",),
    "everyone": ("female", "male"),
}
# Which preferences cover a given gender.
_PREFERENCES_ACCEPTING = {
    "female": ("women", "everyone"),
    "male": ("men", "everyone"),
}


async def next_candidate(session: AsyncSession, viewer: Profile) -> Profile | None:
    """Picks one profile to show, or None if there is nobody left.

    A candidate must fit the viewer's filters, and the viewer must fit the
    candidate's filters too. Otherwise a like could never become a match.
    """
    already_swiped = select(Swipe.target_id).where(Swipe.viewer_id == viewer.user_id)
    blocked_by_viewer = select(Block.blocked_id).where(Block.blocker_id == viewer.user_id)
    blocked_viewer = select(Block.blocker_id).where(Block.blocked_id == viewer.user_id)
    banned = select(Ban.user_id)
    liked_viewer = (
        exists()
        .where(
            Swipe.viewer_id == Profile.user_id,
            Swipe.target_id == viewer.user_id,
            Swipe.action == LIKE,
        )
        .correlate(Profile)
    )

    result = await session.execute(
        select(Profile)
        .where(
            Profile.user_id != viewer.user_id,
            Profile.city == viewer.city,
            # The viewer wants the candidate's gender and age...
            Profile.gender.in_(_WANTED_GENDERS[viewer.preference]),
            Profile.age.between(viewer.age_min, viewer.age_max),
            # ...and the candidate wants the viewer's gender and age.
            Profile.preference.in_(_PREFERENCES_ACCEPTING[viewer.gender]),
            Profile.age_min <= viewer.age,
            Profile.age_max >= viewer.age,
            # Never show a profile the viewer has already decided on.
            Profile.user_id.not_in(already_swiped),
            # Blocks work both ways, and banned people are hidden.
            Profile.user_id.not_in(blocked_by_viewer),
            Profile.user_id.not_in(blocked_viewer),
            Profile.user_id.not_in(banned),
        )
        # People who already liked the viewer come first, the rest in random order.
        .order_by(liked_viewer.desc(), func.random())
        .limit(1)
        .options(joinedload(Profile.user), selectinload(Profile.photos))
    )
    return result.scalar_one_or_none()


async def can_swipe_on(session: AsyncSession, viewer_id: int, target_id: int) -> bool:
    """False if the target is the viewer, deleted their account, was banned, or
    if either of the two blocked the other. Checked again at swipe time, because
    any of these can happen while a card is on screen."""
    if viewer_id == target_id or await session.get(Profile, target_id) is None:
        return False
    if await session.get(Ban, target_id) is not None:
        return False
    blocked = await session.scalar(
        select(Block.id).where(
            or_(
                (Block.blocker_id == viewer_id) & (Block.blocked_id == target_id),
                (Block.blocker_id == target_id) & (Block.blocked_id == viewer_id),
            )
        )
    )
    return blocked is None


async def record_swipe(
    session: AsyncSession, viewer_id: int, target_id: int, action: str, **props
) -> bool:
    """Saves a Like or Pass. Returns False if this pair was already decided.

    Extra keyword arguments go into the event's properties, for example source="app".
    """
    if action not in ACTIONS:
        raise ValueError(f"unknown action: {action}")
    if viewer_id == target_id:
        raise ValueError("cannot swipe on yourself")

    existing = await session.scalar(
        select(Swipe.id).where(Swipe.viewer_id == viewer_id, Swipe.target_id == target_id)
    )
    if existing is not None:
        return False
    session.add(Swipe(viewer_id=viewer_id, target_id=target_id, action=action))
    log_event(session, action, viewer_id, target_id, **props)
    await session.commit()
    return True
