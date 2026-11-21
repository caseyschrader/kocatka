from sqlalchemy import select

from bot import strings
from bot.db.models import Swipe


async def swipes(sessionmaker) -> list[tuple[int, int, str]]:
    async with sessionmaker() as session:
        rows = await session.execute(select(Swipe.viewer_id, Swipe.target_id, Swipe.action))
        return sorted(tuple(row) for row in rows)


async def test_browse_needs_a_profile(chat):
    await chat.send_text("/browse")

    assert chat.last_text == strings.NO_PROFILE


async def test_browse_with_nobody_around(chat):
    await chat.register()
    await chat.send_text("/browse")

    assert chat.last_text == strings.NO_MORE_PROFILES


async def test_woman_sees_man_who_wants_women(new_chat):
    anya = new_chat("Аня")
    oleg = new_chat("Олег")
    await anya.register(gender="female", pref="men")
    await oleg.register(gender="male", pref="women")

    await anya.send_text("/browse")

    assert anya.shown_ids == [oleg.user_id]
    assert anya.photos[-1].photo == "Олег-photo-0"
    assert "Олег, 27" in anya.photos[-1].caption


async def test_gender_preference_works_both_ways(new_chat):
    anya = new_chat("Аня")  # wants men
    ivan = new_chat("Иван")  # a man who wants men: Anya is not his type
    maria = new_chat("Мария")  # a woman: not Anya's type
    oleg = new_chat("Олег")  # a man who wants everyone: fits
    await anya.register(gender="female", pref="men")
    await ivan.register(gender="male", pref="men")
    await maria.register(gender="female", pref="everyone")
    await oleg.register(gender="male", pref="everyone")

    await anya.send_text("/browse")
    await anya.press(f"swipe:pass:{oleg.user_id}")

    assert anya.shown_ids == [oleg.user_id]
    assert anya.last_text == strings.NO_MORE_PROFILES


async def test_same_gender_browsing(new_chat):
    maria = new_chat("Мария")
    lena = new_chat("Лена")
    await maria.register(gender="female", pref="women")
    await lena.register(gender="female", pref="everyone")

    await maria.send_text("/browse")

    assert maria.shown_ids == [lena.user_id]


async def test_age_range_works_both_ways(new_chat):
    anya = new_chat("Аня")
    too_old = new_chat("Пётр")
    wants_older = new_chat("Илья")  # 30, but only wants people over 35
    fits = new_chat("Олег")
    await anya.register(age="28", age_range="25-35")
    await too_old.register(gender="male", pref="women", age="45")
    await wants_older.register(gender="male", pref="women", age="30", age_range="35-50")
    await fits.register(gender="male", pref="women", age="35", age_range="20-30")

    await anya.send_text("/browse")
    await anya.press(f"swipe:pass:{fits.user_id}")

    assert anya.shown_ids == [fits.user_id]
    assert anya.last_text == strings.NO_MORE_PROFILES


async def test_like_and_pass_are_stored_and_never_repeated(new_chat, sessionmaker):
    anya = new_chat("Аня")
    oleg = new_chat("Олег")
    ivan = new_chat("Иван")
    await anya.register()
    await oleg.register(gender="male", pref="women")
    await ivan.register(gender="male", pref="women")

    await anya.send_text("/browse")
    first, = anya.shown_ids
    await anya.press(f"swipe:like:{first}")
    second = anya.shown_ids[-1]
    await anya.press(f"swipe:pass:{second}")

    assert {first, second} == {oleg.user_id, ivan.user_id}
    assert anya.last_text == strings.NO_MORE_PROFILES
    assert await swipes(sessionmaker) == sorted(
        [(anya.user_id, first, "like"), (anya.user_id, second, "pass")]
    )

    await anya.send_text("/browse")
    assert anya.last_text == strings.NO_MORE_PROFILES


async def test_pressing_an_old_button_twice_records_once(new_chat, sessionmaker):
    anya = new_chat("Аня")
    oleg = new_chat("Олег")
    await anya.register()
    await oleg.register(gender="male", pref="women")

    await anya.send_text("/browse")
    await anya.press(f"swipe:like:{oleg.user_id}")
    shown_before = len(anya.shown_ids)
    texts_before = len(anya.texts)
    await anya.press(f"swipe:pass:{oleg.user_id}")

    assert await swipes(sessionmaker) == [(anya.user_id, oleg.user_id, "like")]
    assert len(anya.shown_ids) == shown_before
    assert len(anya.texts) == texts_before


async def test_people_who_liked_you_come_first(new_chat):
    anya = new_chat("Аня")
    await anya.register()
    men = [new_chat(f"М{n}") for n in range(5)]
    for man in men:
        await man.register(gender="male", pref="women")
    admirer = men[3]

    await admirer.send_text("/browse")
    await admirer.press(f"swipe:like:{anya.user_id}")
    await anya.send_text("/browse")

    assert anya.shown_ids == [admirer.user_id]


async def test_profile_with_several_photos_is_shown_as_album(new_chat):
    anya = new_chat("Аня")
    oleg = new_chat("Олег")
    await anya.register()
    await oleg.register(gender="male", pref="women", photos=3)

    await anya.send_text("/browse")

    album = anya.albums[-1]
    assert [p.media for p in album.media] == [f"Олег-photo-{n}" for n in range(3)]
    assert "Олег, 27" in anya.last_text
    assert anya.shown_ids == [oleg.user_id]


async def test_redo_fixes_a_wrong_preference(new_chat):
    """The real case from testing: she picked "women" by mistake."""
    casey = new_chat("Кейси")
    polina = new_chat("Полина")
    await casey.register(gender="male", pref="women", age="30", age_range="18-30")
    await polina.register(gender="female", pref="women", age="19", age_range="20-27")

    await casey.send_text("/browse")
    assert casey.last_text == strings.NO_MORE_PROFILES

    await polina.send_text("/start")
    await polina.press("profile:redo")
    await polina.press("gender:female")
    await polina.press("pref:men")
    await polina.send_text("19")
    await polina.send_text("18-35")
    await polina.press("city:spb")
    await polina.send_text("Новая анкета")
    await polina.send_photo("new-photo")
    await polina.press("photos:done")

    await casey.send_text("/browse")
    assert casey.shown_ids == [polina.user_id]


async def test_redo_keeps_swipes(new_chat, sessionmaker):
    anya = new_chat("Аня")
    oleg = new_chat("Олег")
    await anya.register()
    await oleg.register(gender="male", pref="women")
    await anya.send_text("/browse")
    await anya.press(f"swipe:pass:{oleg.user_id}")

    await anya.send_text("/profile")
    await anya.press("profile:redo")
    await anya.press("gender:female")
    await anya.press("pref:men")
    await anya.send_text("27")
    await anya.send_text("18-99")
    await anya.press("city:spb")
    await anya.send_text("Снова я")
    await anya.send_photo("p")
    await anya.press("photos:done")
    await anya.send_text("/browse")

    assert anya.last_text == strings.NO_MORE_PROFILES
    assert await swipes(sessionmaker) == [(anya.user_id, oleg.user_id, "pass")]


async def test_cannot_swipe_on_yourself(chat, sessionmaker):
    await chat.register()
    await chat.press(f"swipe:like:{chat.user_id}")

    assert await swipes(sessionmaker) == []
