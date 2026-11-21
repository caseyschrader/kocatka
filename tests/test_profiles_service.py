from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select

from bot.db.models import Match, Photo, Profile, Swipe, User
from bot.services import profiles

NOW = datetime(2026, 11, 21, tzinfo=timezone.utc)


def new_profile(**overrides) -> profiles.NewProfile:
    values = dict(
        user_id=1,
        first_name="Аня",
        adult_confirmed_at=NOW,
        consented_at=NOW,
        gender="female",
        preference="men",
        age=27,
        age_min=25,
        age_max=35,
        city=profiles.CITY_SPB,
        bio="О себе",
        photo_file_ids=["a", "b"],
    )
    values.update(overrides)
    return profiles.NewProfile(**values)


@pytest.mark.parametrize(
    "text, expected",
    [("27", 27), (" 18 ", 18), ("17", 17), ("99", 99), ("100", None), ("0", None),
     ("-3", None), ("27.5", None), ("abc", None), ("", None)],
)
def test_parse_age(text, expected):
    assert profiles.parse_age(text) == expected


def test_clean_bio():
    assert profiles.clean_bio("  привет  ") == "привет"
    assert profiles.clean_bio("   ") is None
    assert profiles.clean_bio("я" * 500) == "я" * 500
    assert profiles.clean_bio("я" * 501) is None


async def test_save_and_get_profile(sessionmaker):
    async with sessionmaker() as session:
        await profiles.save_profile(session, new_profile())

    async with sessionmaker() as session:
        profile = await profiles.get_profile(session, 1)
    assert profile.user.first_name == "Аня"
    assert [(p.position, p.file_id) for p in profile.photos] == [(0, "a"), (1, "b")]


async def test_get_profile_missing(sessionmaker):
    async with sessionmaker() as session:
        assert await profiles.get_profile(session, 404) is None


async def test_saving_again_replaces_old_data(sessionmaker):
    async with sessionmaker() as session:
        await profiles.save_profile(session, new_profile())
        profile = await profiles.save_profile(
            session, new_profile(age=30, photo_file_ids=["c"])
        )

        assert profile.age == 30
        assert [p.file_id for p in profile.photos] == ["c"]
        assert await session.scalar(select(func.count()).select_from(Photo)) == 1


async def test_saving_again_keeps_swipes_and_signup_date(sessionmaker):
    async with sessionmaker() as session:
        first = await profiles.save_profile(session, new_profile())
        created_at = first.created_at
        await profiles.save_profile(session, new_profile(user_id=2))
        session.add(Swipe(viewer_id=1, target_id=2, action="like"))
        await session.commit()

        again = await profiles.save_profile(session, new_profile(preference="everyone"))

        assert again.preference == "everyone"
        assert again.created_at == created_at
        assert await session.scalar(select(func.count()).select_from(Swipe)) == 1
        assert await session.scalar(select(func.count()).select_from(Profile)) == 2


async def test_delete_user_data_removes_everything(sessionmaker):
    async with sessionmaker() as session:
        await profiles.save_profile(session, new_profile())
        await profiles.save_profile(session, new_profile(user_id=2))
        await profiles.save_profile(session, new_profile(user_id=3))
        session.add_all([
            Swipe(viewer_id=1, target_id=2, action="like"),
            Swipe(viewer_id=2, target_id=1, action="pass"),
            Swipe(viewer_id=2, target_id=3, action="like"),
            Match(user_a=1, user_b=2, status="pending", created_at=NOW, expires_at=NOW),
            Match(user_a=2, user_b=3, status="pending", created_at=NOW, expires_at=NOW),
        ])
        await session.commit()

        await profiles.delete_user_data(session, 1)
        await session.commit()

        for model in (User, Profile):
            assert await session.scalar(select(func.count()).select_from(model)) == 2
        # Swipes made by and about the user are gone. Other people's remain.
        assert await session.scalar(select(func.count()).select_from(Swipe)) == 1
        assert await session.scalar(select(func.count()).select_from(Match)) == 1
        assert await profiles.get_profile(session, 1) is None
        assert await profiles.get_profile(session, 2) is not None


@pytest.mark.parametrize(
    "overrides",
    [{"gender": "other"}, {"preference": "nobody"}, {"age": 17}, {"age": 100},
     {"age_min": 17}, {"age_max": 100}, {"age_min": 40, "age_max": 30},
     {"photo_file_ids": []}, {"photo_file_ids": ["a", "b", "c", "d"]}],
)
async def test_save_rejects_invalid_data(sessionmaker, overrides):
    async with sessionmaker() as session:
        with pytest.raises(ValueError):
            await profiles.save_profile(session, new_profile(**overrides))


@pytest.mark.parametrize(
    "text, expected",
    [("25-35", (25, 35)), ("25 35", (25, 35)), ("от 25 до 35", (25, 35)),
     ("35-25", (25, 35)), ("18-99", (18, 99)), ("30-30", (30, 30)),
     ("17-30", None), ("25-100", None), ("30", None), ("1-2-3", None), ("", None)],
)
def test_parse_age_range(text, expected):
    assert profiles.parse_age_range(text) == expected
