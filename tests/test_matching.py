from datetime import timedelta

from sqlalchemy import select

from bot import strings
from bot.db.models import Match, Swipe, utcnow
from bot.jobs import create_missing_matches_once, expire_matches_once
from bot.services import matching


async def all_matches(sessionmaker) -> list[Match]:
    async with sessionmaker() as session:
        return list((await session.scalars(select(Match))).all())


async def like_each_other(first, second) -> None:
    """first likes second, then second likes back. Assumes they are each other's only candidate."""
    await first.send_text("/browse")
    await first.press(f"swipe:like:{second.user_id}")
    await second.send_text("/browse")
    await second.press(f"swipe:like:{first.user_id}")


async def woman_and_man(new_chat):
    anya = new_chat("Аня")
    oleg = new_chat("Олег")
    await anya.register(gender="female", pref="men")
    await oleg.register(gender="male", pref="women")
    return anya, oleg


def write_button(chat) -> str:
    return [b for b in chat.buttons if b.startswith("write:")][-1]


# --- Creating a match ---


async def test_one_sided_like_is_not_a_match(new_chat, sessionmaker):
    anya, oleg = await woman_and_man(new_chat)
    await oleg.send_text("/browse")
    await oleg.press(f"swipe:like:{anya.user_id}")

    assert await all_matches(sessionmaker) == []


async def test_like_answered_by_pass_is_not_a_match(new_chat, sessionmaker):
    anya, oleg = await woman_and_man(new_chat)
    await oleg.send_text("/browse")
    await oleg.press(f"swipe:like:{anya.user_id}")
    await anya.send_text("/browse")
    await anya.press(f"swipe:pass:{oleg.user_id}")

    assert await all_matches(sessionmaker) == []


async def test_mutual_like_creates_a_pending_match(new_chat, sessionmaker):
    anya, oleg = await woman_and_man(new_chat)
    await like_each_other(oleg, anya)

    match, = await all_matches(sessionmaker)
    assert match.status == matching.PENDING
    assert (match.user_a, match.user_b) == tuple(sorted((anya.user_id, oleg.user_id)))
    window = match.expires_at - match.created_at
    assert window == timedelta(hours=24)


async def test_woman_is_told_to_write_and_man_to_wait(new_chat):
    anya, oleg = await woman_and_man(new_chat)
    await like_each_other(oleg, anya)

    assert strings.MATCH_YOU_WRITE_FIRST.format(name="Олег") in anya.texts
    assert strings.MATCH_SHE_WRITES_FIRST.format(name="Аня") in oleg.texts
    assert any(b.startswith("write:") for b in anya.buttons)
    assert not any(b.startswith("write:") for b in oleg.buttons)


async def test_same_gender_match_both_may_write(new_chat):
    maria = new_chat("Мария")
    lena = new_chat("Лена")
    await maria.register(gender="female", pref="women")
    await lena.register(gender="female", pref="women")
    await like_each_other(maria, lena)

    assert strings.MATCH_EITHER_WRITES.format(name="Лена") in maria.texts
    assert strings.MATCH_EITHER_WRITES.format(name="Мария") in lena.texts
    assert write_button(maria) == write_button(lena)


# --- The first message ---


async def test_woman_writes_first_and_man_receives_it(new_chat, sessionmaker):
    anya, oleg = await woman_and_man(new_chat)
    await like_each_other(oleg, anya)

    await anya.press(write_button(anya))
    assert anya.last_text == strings.ASK_FIRST_MESSAGE.format(name="Олег")
    await anya.send_text("Привет! Как дела?")

    assert anya.last_text == strings.FIRST_MESSAGE_SENT
    assert oleg.last_text == strings.FIRST_MESSAGE_RECEIVED.format(
        name="Аня", text="Привет! Как дела?"
    )
    match, = await all_matches(sessionmaker)
    assert match.status == matching.ACTIVE
    assert match.first_sender == anya.user_id


async def test_man_cannot_write_first(new_chat, sessionmaker):
    anya, oleg = await woman_and_man(new_chat)
    await like_each_other(oleg, anya)
    received_before = len(anya.texts)

    # He has no button, but a forged or old button must not work either.
    await oleg.press(write_button(anya))

    assert oleg.last_text == strings.CANNOT_WRITE_NOT_ALLOWED
    await oleg.send_text("Привет")
    assert len(anya.texts) == received_before
    match, = await all_matches(sessionmaker)
    assert match.status == matching.PENDING


async def test_same_gender_first_writer_wins(new_chat, sessionmaker):
    maria = new_chat("Мария")
    lena = new_chat("Лена")
    await maria.register(gender="female", pref="women")
    await lena.register(gender="female", pref="women")
    await like_each_other(maria, lena)
    button = write_button(maria)

    await maria.press(button)
    await lena.press(button)
    await lena.send_text("Привет от Лены")
    await maria.send_text("Привет от Марии")

    assert strings.FIRST_MESSAGE_RECEIVED.format(
        name="Лена", text="Привет от Лены"
    ) in maria.texts
    # Лена started first. Мария's message still arrives, as an ordinary reply.
    assert lena.last_text == strings.RELAYED_MESSAGE.format(name="Мария", text="Привет от Марии")
    match, = await all_matches(sessionmaker)
    assert match.first_sender == lena.user_id


async def test_write_button_after_start_reopens_the_chat(new_chat):
    anya, oleg = await woman_and_man(new_chat)
    await like_each_other(oleg, anya)
    await anya.press(write_button(anya))
    await anya.send_text("Привет")

    await anya.press(write_button(anya))

    assert anya.last_text == strings.CHAT_OPENED.format(name="Олег")


async def test_cancel_while_writing(new_chat, sessionmaker):
    anya, oleg = await woman_and_man(new_chat)
    await like_each_other(oleg, anya)
    await anya.press(write_button(anya))
    await anya.send_text("/cancel")

    assert anya.last_text == strings.CHAT_LEFT
    await anya.send_text("Привет")
    assert anya.last_text == strings.UNKNOWN
    match, = await all_matches(sessionmaker)
    assert match.status == matching.PENDING


async def test_only_text_for_now(new_chat):
    anya, oleg = await woman_and_man(new_chat)
    await like_each_other(oleg, anya)
    await anya.press(write_button(anya))
    await anya.send_photo("selfie")

    assert anya.last_text == strings.TEXT_ONLY


async def test_too_long_first_message(new_chat):
    anya, oleg = await woman_and_man(new_chat)
    await like_each_other(oleg, anya)
    await anya.press(write_button(anya))
    await anya.send_text("а" * 1001)

    assert anya.last_text == strings.MESSAGE_TOO_LONG
    await anya.send_text("Привет")
    assert anya.last_text == strings.FIRST_MESSAGE_SENT


# --- Expiry ---


async def test_expiry_job_expires_and_tells_both(new_chat, sessionmaker, bot):
    anya, oleg = await woman_and_man(new_chat)
    await like_each_other(oleg, anya)

    assert await expire_matches_once(bot, sessionmaker, utcnow() + timedelta(hours=23)) == 0
    assert await expire_matches_once(bot, sessionmaker, utcnow() + timedelta(hours=25)) == 1

    match, = await all_matches(sessionmaker)
    assert match.status == matching.EXPIRED
    assert anya.last_text == strings.EXPIRED_STARTER.format(name="Олег")
    assert oleg.last_text == strings.EXPIRED_WAITER.format(name="Аня")

    await anya.press(write_button(anya))
    assert anya.last_text == strings.CANNOT_WRITE_TOO_LATE


async def test_expiry_job_leaves_started_matches_alone(new_chat, sessionmaker, bot):
    anya, oleg = await woman_and_man(new_chat)
    await like_each_other(oleg, anya)
    await anya.press(write_button(anya))
    await anya.send_text("Привет")

    assert await expire_matches_once(bot, sessionmaker, utcnow() + timedelta(days=3)) == 0
    match, = await all_matches(sessionmaker)
    assert match.status == matching.ACTIVE


async def test_same_gender_expiry_message(new_chat, sessionmaker, bot):
    maria = new_chat("Мария")
    lena = new_chat("Лена")
    await maria.register(gender="female", pref="women")
    await lena.register(gender="female", pref="women")
    await like_each_other(maria, lena)

    await expire_matches_once(bot, sessionmaker, utcnow() + timedelta(hours=25))

    assert maria.last_text == strings.EXPIRED_EITHER.format(name="Лена")
    assert lena.last_text == strings.EXPIRED_EITHER.format(name="Мария")


async def test_writing_after_24_hours_is_refused_even_before_the_job_runs(
    new_chat, sessionmaker
):
    anya, oleg = await woman_and_man(new_chat)
    await like_each_other(oleg, anya)
    match, = await all_matches(sessionmaker)

    async with sessionmaker() as session:
        late = utcnow() + timedelta(hours=24, seconds=1)
        outcome = await matching.start_conversation(session, match.id, anya.user_id, late)

    assert outcome == matching.TOO_LATE


# --- Startup catch-up ---


async def test_startup_creates_matches_for_old_mutual_likes(new_chat, sessionmaker, bot):
    anya, oleg = await woman_and_man(new_chat)
    ivan = new_chat("Иван")
    await ivan.register(gender="male", pref="women")
    # Likes saved before matching existed: rows only, no match, no messages.
    async with sessionmaker() as session:
        session.add_all([
            Swipe(viewer_id=anya.user_id, target_id=oleg.user_id, action="like"),
            Swipe(viewer_id=oleg.user_id, target_id=anya.user_id, action="like"),
            Swipe(viewer_id=ivan.user_id, target_id=anya.user_id, action="like"),
        ])
        await session.commit()

    assert await create_missing_matches_once(bot, sessionmaker) == 1
    assert await create_missing_matches_once(bot, sessionmaker) == 0

    match, = await all_matches(sessionmaker)
    assert {match.user_a, match.user_b} == {anya.user_id, oleg.user_id}
    assert anya.last_text == strings.MATCH_YOU_WRITE_FIRST.format(name="Олег")
    assert oleg.last_text == strings.MATCH_SHE_WRITES_FIRST.format(name="Аня")


# --- /matches ---


async def test_matches_command(new_chat):
    anya, oleg = await woman_and_man(new_chat)
    await anya.send_text("/matches")
    assert anya.last_text == strings.NO_MATCHES

    await like_each_other(oleg, anya)
    await anya.send_text("/matches")
    await oleg.send_text("/matches")

    assert anya.last_text == strings.MATCH_LINE_YOUR_TURN.format(name="Олег", hours=24)
    assert oleg.last_text == strings.MATCH_LINE_WAITING.format(name="Аня", hours=24)

    await anya.press(write_button(anya))
    await anya.send_text("Привет")
    await oleg.send_text("/matches")
    assert oleg.last_text == strings.MATCH_LINE_ACTIVE.format(name="Аня")


async def test_matches_command_needs_profile(chat):
    await chat.send_text("/matches")

    assert chat.last_text == strings.NO_PROFILE


async def test_expired_matches_are_not_listed(new_chat, sessionmaker, bot):
    anya, oleg = await woman_and_man(new_chat)
    await like_each_other(oleg, anya)
    await expire_matches_once(bot, sessionmaker, utcnow() + timedelta(hours=25))

    await anya.send_text("/matches")

    assert anya.last_text == strings.NO_MATCHES
