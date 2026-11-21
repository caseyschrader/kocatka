from sqlalchemy import func, select

from bot import strings
from bot.db.models import Photo, Profile, User
from bot.services import profiles


async def count(sessionmaker, model) -> int:
    async with sessionmaker() as session:
        return await session.scalar(select(func.count()).select_from(model))


async def nothing_stored(sessionmaker) -> bool:
    return all([await count(sessionmaker, m) == 0 for m in (User, Profile, Photo)])


async def go_to_photos(chat, age: str = "27", bio: str = "Люблю белые ночи") -> None:
    """Walks the happy path up to the point where photos are requested."""
    await chat.send_text("/start")
    await chat.press("adult:yes")
    await chat.press("consent:yes")
    await chat.press("gender:female")
    await chat.press("pref:men")
    await chat.send_text(age)
    await chat.send_text("25-35")
    await chat.press("city:spb")
    await chat.send_text(bio)


async def test_start_greets_and_asks_age_confirmation(chat):
    await chat.send_text("/start")

    assert chat.texts == [strings.WELCOME, strings.ASK_ADULT]


async def test_questions_come_in_order(chat):
    await go_to_photos(chat)

    assert chat.texts == [
        strings.WELCOME,
        strings.ASK_ADULT,
        strings.ASK_CONSENT,
        strings.ASK_GENDER,
        strings.ASK_PREFERENCE,
        strings.ASK_AGE,
        strings.ASK_AGE_RANGE,
        strings.ASK_CITY,
        strings.ASK_BIO,
        strings.ASK_PHOTOS,
    ]


async def test_full_flow_saves_profile(chat, sessionmaker):
    await go_to_photos(chat)
    await chat.send_photo("photo-1")
    await chat.send_photo("photo-2")
    await chat.press("photos:done")

    async with sessionmaker() as session:
        profile = await profiles.get_profile(session, chat.user_id)
    assert profile.user.first_name == "Аня"
    assert profile.user.adult_confirmed_at is not None
    assert profile.user.consented_at is not None
    assert profile.gender == "female"
    assert profile.preference == "men"
    assert profile.age == 27
    assert (profile.age_min, profile.age_max) == (25, 35)
    assert profile.city == "Санкт-Петербург"
    assert profile.bio == "Люблю белые ночи"
    assert [p.file_id for p in profile.photos] == ["photo-1", "photo-2"]

    assert chat.texts[-2:] == [strings.PROFILE_SAVED, strings.BROWSE_HINT]
    card = chat.photos[-1]
    assert card.photo == "photo-1"
    assert "Аня, 27" in card.caption
    assert "Люблю белые ночи" in card.caption


async def test_nothing_is_stored_before_the_last_step(chat, sessionmaker):
    await go_to_photos(chat)
    await chat.send_photo("photo-1")

    assert await nothing_stored(sessionmaker)


async def test_third_photo_finishes_automatically(chat, sessionmaker):
    await go_to_photos(chat)
    for n in (1, 2, 3):
        await chat.send_photo(f"photo-{n}")

    assert await count(sessionmaker, Photo) == 3
    assert strings.PROFILE_SAVED in chat.texts


async def test_fourth_photo_is_not_added(chat, sessionmaker):
    await go_to_photos(chat)
    for n in (1, 2, 3, 4):
        await chat.send_photo(f"photo-{n}")

    assert await count(sessionmaker, Photo) == 3


async def test_under_18_button_stops_and_stores_nothing(chat, sessionmaker):
    await chat.send_text("/start")
    await chat.press("adult:no")

    assert chat.last_text == strings.UNDERAGE
    assert await nothing_stored(sessionmaker)
    # The flow is over: later button presses do not continue it.
    await chat.press("consent:yes")
    assert chat.last_text == strings.UNDERAGE


async def test_declined_consent_stops_and_stores_nothing(chat, sessionmaker):
    await chat.send_text("/start")
    await chat.press("adult:yes")
    await chat.press("consent:no")

    assert chat.last_text == strings.CONSENT_DECLINED
    await chat.press("gender:female")
    assert chat.last_text == strings.CONSENT_DECLINED
    assert await nothing_stored(sessionmaker)


async def test_consent_cannot_be_skipped(chat):
    await chat.send_text("/start")
    await chat.press("adult:yes")
    await chat.press("gender:female")

    assert chat.last_text == strings.ASK_CONSENT


async def test_invalid_age_asks_again(chat):
    await chat.send_text("/start")
    await chat.press("adult:yes")
    await chat.press("consent:yes")
    await chat.press("gender:male")
    await chat.press("pref:everyone")

    for bad in ("двадцать", "27 лет", "0", "150", "-5"):
        await chat.send_text(bad)
        assert chat.last_text == strings.AGE_INVALID
    await chat.send_sticker()
    assert chat.last_text == strings.AGE_INVALID

    await chat.send_text("31")
    assert chat.last_text == strings.ASK_AGE_RANGE


async def test_typed_age_under_18_stops(chat, sessionmaker):
    await chat.send_text("/start")
    await chat.press("adult:yes")
    await chat.press("consent:yes")
    await chat.press("gender:male")
    await chat.press("pref:women")
    await chat.send_text("17")

    assert chat.last_text == strings.UNDERAGE
    await chat.send_text("25")
    assert chat.last_text == strings.UNKNOWN
    assert await nothing_stored(sessionmaker)


async def test_other_city_stops_and_stores_nothing(chat, sessionmaker):
    await chat.send_text("/start")
    await chat.press("adult:yes")
    await chat.press("consent:yes")
    await chat.press("gender:female")
    await chat.press("pref:men")
    await chat.send_text("30")
    await chat.send_text("25-40")
    await chat.press("city:other")

    assert chat.last_text == strings.CITY_NOT_SUPPORTED
    assert await nothing_stored(sessionmaker)


async def test_bio_too_long_asks_again(chat):
    await go_to_photos(chat, bio="я" * 501)
    assert chat.last_text == strings.BIO_INVALID

    await chat.send_text("я" * 500)
    assert chat.last_text == strings.ASK_PHOTOS


async def test_text_instead_of_photo(chat):
    await go_to_photos(chat)
    await chat.send_text("вот моё фото")

    assert chat.last_text == strings.PHOTO_EXPECTED


async def test_done_without_photos_is_refused(chat, sessionmaker):
    await go_to_photos(chat)
    await chat.press("photos:done")

    assert chat.last_text == strings.PHOTO_NEEDED
    assert await nothing_stored(sessionmaker)


async def test_typing_during_a_button_step(chat):
    await chat.send_text("/start")
    await chat.send_text("да")

    assert chat.last_text == strings.USE_BUTTONS


async def test_cancel_clears_progress(chat, sessionmaker):
    await go_to_photos(chat)
    await chat.send_text("/cancel")
    assert chat.last_text == strings.CANCELLED

    await chat.send_photo("photo-1")
    assert chat.last_text == strings.UNKNOWN
    assert await nothing_stored(sessionmaker)


async def test_cancel_with_nothing_in_progress(chat):
    await chat.send_text("/cancel")

    assert chat.last_text == strings.NOTHING_TO_CANCEL


async def test_start_again_with_existing_profile_shows_it(chat, sessionmaker):
    await go_to_photos(chat)
    await chat.send_photo("photo-1")
    await chat.press("photos:done")

    await chat.send_text("/start")

    assert chat.last_text == strings.ALREADY_REGISTERED
    assert len(chat.photos) == 2
    assert await count(sessionmaker, Profile) == 1


async def test_profile_command(chat):
    await chat.send_text("/profile")
    assert chat.last_text == strings.NO_PROFILE

    await go_to_photos(chat)
    await chat.send_photo("photo-1")
    await chat.press("photos:done")
    await chat.send_text("/profile")

    assert "Аня, 27" in chat.photos[-1].caption


async def test_two_users_do_not_mix(sessionmaker):
    from tests.conftest import FakeChat

    anya = FakeChat(sessionmaker, first_name="Аня")
    oleg = FakeChat(sessionmaker, first_name="Олег")

    await go_to_photos(anya, age="27", bio="Аня о себе")
    await go_to_photos(oleg, age="33", bio="Олег о себе")
    await anya.send_photo("anya-photo")
    await oleg.send_photo("oleg-photo")
    await oleg.press("photos:done")
    await anya.press("photos:done")

    async with sessionmaker() as session:
        a = await profiles.get_profile(session, anya.user_id)
        o = await profiles.get_profile(session, oleg.user_id)
    assert (a.age, a.bio, a.photos[0].file_id) == (27, "Аня о себе", "anya-photo")
    assert (o.age, o.bio, o.photos[0].file_id) == (33, "Олег о себе", "oleg-photo")


async def go_to_age_range(chat) -> None:
    await chat.send_text("/start")
    await chat.press("adult:yes")
    await chat.press("consent:yes")
    await chat.press("gender:female")
    await chat.press("pref:men")
    await chat.send_text("27")


async def test_age_range_below_18_is_refused(chat):
    await go_to_age_range(chat)

    for bad in ("16-30", "17-17", "0-25"):
        await chat.send_text(bad)
        assert chat.last_text == strings.AGE_RANGE_INVALID

    await chat.send_text("18-30")
    assert chat.last_text == strings.ASK_CITY


async def test_age_range_must_be_two_numbers(chat):
    await go_to_age_range(chat)

    for bad in ("30", "любой", "20-30-40", "25-120"):
        await chat.send_text(bad)
        assert chat.last_text == strings.AGE_RANGE_INVALID
    await chat.send_sticker()
    assert chat.last_text == strings.AGE_RANGE_INVALID


async def test_age_range_accepts_words_and_reversed_order(chat, sessionmaker):
    await go_to_age_range(chat)
    await chat.send_text("от 40 до 30")
    await chat.press("city:spb")
    await chat.send_text("О себе")
    await chat.send_photo("photo-1")
    await chat.press("photos:done")

    async with sessionmaker() as session:
        profile = await profiles.get_profile(session, chat.user_id)
    assert (profile.age_min, profile.age_max) == (30, 40)
