"""Profile rules and storage. No Telegram code here, so it is easy to test."""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from bot.db.models import Photo, Profile, User

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
    await session.execute(delete(Photo).where(Photo.user_id == user_id))
    await session.execute(delete(Profile).where(Profile.user_id == user_id))
    await session.execute(delete(User).where(User.id == user_id))


async def save_profile(session: AsyncSession, new: NewProfile) -> Profile:
    """Stores user, profile and photos in one transaction, replacing any old data."""
    if new.gender not in GENDERS:
        raise ValueError(f"unknown gender: {new.gender}")
    if new.preference not in PREFERENCES:
        raise ValueError(f"unknown preference: {new.preference}")
    if not MIN_AGE <= new.age <= MAX_AGE:
        raise ValueError(f"age out of range: {new.age}")
    if not 1 <= len(new.photo_file_ids) <= MAX_PHOTOS:
        raise ValueError(f"expected 1 to {MAX_PHOTOS} photos")

    await delete_user_data(session, new.user_id)
    session.add(
        User(
            id=new.user_id,
            first_name=new.first_name[:64],
            adult_confirmed_at=new.adult_confirmed_at,
            consented_at=new.consented_at,
        )
    )
    session.add(
        Profile(
            user_id=new.user_id,
            gender=new.gender,
            preference=new.preference,
            age=new.age,
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
