"""Profile rules and storage. No Telegram code here, so it is easy to test."""

import re
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from bot.db.models import Match, Photo, Profile, Swipe, User

MIN_AGE = 18
MAX_AGE = 99
BIO_MAX_LENGTH = 500
MAX_PHOTOS = 3

GENDERS = ("female", "male")
PREFERENCES = ("women", "men", "everyone")
CITY_SPB = "Санкт-Петербург"


@dataclass
class NewProfile:
    user_id: int
    first_name: str
    adult_confirmed_at: datetime
    consented_at: datetime
    gender: str
    preference: str
    age: int
    age_min: int
    age_max: int
    city: str
    bio: str
    photo_file_ids: list[str]


def parse_age(text: str) -> int | None:
    """Returns the age as a number, or None if the text is not a plausible age.

    Ages below MIN_AGE are returned as is, so the caller can tell
    "too young" apart from "not a number".
    """
    text = text.strip()
    if not text.isdecimal():
        return None
    age = int(text)
    if age < 1 or age > MAX_AGE:
        return None
    return age


def parse_age_range(text: str) -> tuple[int, int] | None:
    """Reads a range such as "25-35" or "от 25 до 35".

    Returns (min, max), or None unless the text holds exactly two numbers,
    both between MIN_AGE and MAX_AGE. The order does not matter.
    """
    numbers = [int(n) for n in re.findall(r"\d+", text)]
    if len(numbers) != 2:
        return None
    low, high = sorted(numbers)
    if low < MIN_AGE or high > MAX_AGE:
        return None
    return low, high


def clean_bio(text: str) -> str | None:
    """Returns the trimmed bio, or None if it is empty or too long."""
    text = text.strip()
    if not text or len(text) > BIO_MAX_LENGTH:
        return None
    return text


async def get_profile(session: AsyncSession, user_id: int) -> Profile | None:
    result = await session.execute(
        select(Profile)
        .where(Profile.user_id == user_id)
        .options(joinedload(Profile.user), selectinload(Profile.photos))
        .execution_options(populate_existing=True)
    )
    return result.scalar_one_or_none()


async def delete_user_data(session: AsyncSession, user_id: int) -> None:
    """Removes every row we hold about a user. Does not commit."""
    await session.execute(
        delete(Match).where(or_(Match.user_a == user_id, Match.user_b == user_id))
    )
    await session.execute(
        delete(Swipe).where(or_(Swipe.viewer_id == user_id, Swipe.target_id == user_id))
    )
    await session.execute(delete(Photo).where(Photo.user_id == user_id))
    await session.execute(delete(Profile).where(Profile.user_id == user_id))
    await session.execute(delete(User).where(User.id == user_id))


async def save_profile(session: AsyncSession, new: NewProfile) -> Profile:
    """Stores user, profile and photos in one transaction, replacing the old profile."""
    if new.gender not in GENDERS:
        raise ValueError(f"unknown gender: {new.gender}")
    if new.preference not in PREFERENCES:
        raise ValueError(f"unknown preference: {new.preference}")
    if not MIN_AGE <= new.age <= MAX_AGE:
        raise ValueError(f"age out of range: {new.age}")
    if not MIN_AGE <= new.age_min <= new.age_max <= MAX_AGE:
        raise ValueError(f"bad age range: {new.age_min} to {new.age_max}")
    if not 1 <= len(new.photo_file_ids) <= MAX_PHOTOS:
        raise ValueError(f"expected 1 to {MAX_PHOTOS} photos")

    # Insert or update in place. Swipes are kept, so a redone profile still
    # never sees the same people twice and earlier likes still count.
    await session.execute(delete(Photo).where(Photo.user_id == new.user_id))
    await session.merge(
        User(
            id=new.user_id,
            first_name=new.first_name[:64],
            adult_confirmed_at=new.adult_confirmed_at,
            consented_at=new.consented_at,
        )
    )
    await session.merge(
        Profile(
            user_id=new.user_id,
            gender=new.gender,
            preference=new.preference,
            age=new.age,
            age_min=new.age_min,
            age_max=new.age_max,
            city=new.city,
            bio=new.bio,
        )
    )
    await session.flush()
    session.add_all(
        Photo(user_id=new.user_id, file_id=file_id, position=position)
        for position, file_id in enumerate(new.photo_file_ids)
    )
    await session.commit()

    profile = await get_profile(session, new.user_id)
    assert profile is not None
    return profile
