from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select

from bot.db.models import Photo, Profile, User
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


async def test_delete_user_data_removes_everything(sessionmaker):
    async with sessionmaker() as session:
        await profiles.save_profile(session, new_profile())
        await profiles.save_profile(session, new_profile(user_id=2))

        await profiles.delete_user_data(session, 1)
        await session.commit()

        for model in (User, Profile):
            assert await session.scalar(select(func.count()).select_from(model)) == 1
        assert await profiles.get_profile(session, 1) is None
        assert await profiles.get_profile(session, 2) is not None


@pytest.mark.parametrize(
    "overrides",
    [{"gender": "other"}, {"preference": "nobody"}, {"age": 17}, {"age": 100},
     {"photo_file_ids": []}, {"photo_file_ids": ["a", "b", "c", "d"]}],
)
async def test_save_rejects_invalid_data(sessionmaker, overrides):
    async with sessionmaker() as session:
        with pytest.raises(ValueError):
            await profiles.save_profile(session, new_profile(**overrides))
