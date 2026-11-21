from sqlalchemy import func, select

from bot import strings
from bot.db.models import Ban, Block, ChatMessage, Match, Photo, Profile, Report, Swipe, User
from bot.services import matching
from tests.test_chat import chatting_pair
from tests.test_matching import like_each_other, woman_and_man, write_button


async def count(sessionmaker, model, *where) -> int:
    async with sessionmaker() as session:
        return await session.scalar(select(func.count()).select_from(model).where(*where))


async def match_status(sessionmaker) -> str:
    async with sessionmaker() as session:
        return (await session.scalars(select(Match.status))).one()


# --- Buttons everywhere ---


async def test_browsing_card_has_report_and_block(new_chat):
    anya, oleg = await woman_and_man(new_chat)
    await anya.send_text("/browse")

    assert f"report:{oleg.user_id}" in anya.buttons
    assert f"block:{oleg.user_id}" in anya.buttons


async def test_match_messages_have_report_and_block(new_chat):
    anya, oleg = await woman_and_man(new_chat)
    await like_each_other(oleg, anya)

    assert f"block:{oleg.user_id}" in anya.buttons
    assert f"block:{anya.user_id}" in oleg.buttons


# --- Block ---


async def test_block_asks_first(new_chat, sessionmaker):
    anya, oleg = await woman_and_man(new_chat)
    await anya.send_text("/browse")
    await anya.press(f"block:{oleg.user_id}")

    assert anya.last_text == strings.ASK_BLOCK_CONFIRM.format(name="Олег")
    await anya.press("blockno")
    assert anya.last_text == strings.BLOCK_CANCELLED
    assert await count(sessionmaker, Block) == 0


async def test_block_hides_both_ways(new_chat):
    anya, oleg = await woman_and_man(new_chat)
    await anya.send_text("/browse")
    await anya.press(f"block:{oleg.user_id}")
    await anya.press(f"blockyes:{oleg.user_id}")

    assert anya.last_text == strings.BLOCKED.format(name="Олег")
    await anya.send_text("/browse")
    assert anya.last_text == strings.NO_MORE_PROFILES
    await oleg.send_text("/browse")
    assert oleg.last_text == strings.NO_MORE_PROFILES


async def test_like_on_an_old_card_after_block_does_nothing(new_chat, sessionmaker):
    anya, oleg = await woman_and_man(new_chat)
    await oleg.send_text("/browse")
    await anya.send_text("/browse")
    await anya.press(f"blockyes:{oleg.user_id}")

    await oleg.press(f"swipe:like:{anya.user_id}")

    assert await count(sessionmaker, Swipe) == 0


async def test_block_ends_the_conversation(new_chat, sessionmaker):
    anya, oleg = await chatting_pair(new_chat)
    await oleg.press(write_button(oleg))

    await anya.press(f"blockyes:{oleg.user_id}")
    received = len(anya.texts)
    await oleg.send_text("Ты тут?")

    assert oleg.last_text == strings.CANNOT_WRITE_UNAVAILABLE
    assert len(anya.texts) == received
    assert await match_status(sessionmaker) == matching.CLOSED
    await oleg.send_text("/matches")
    assert oleg.last_text == strings.NO_MATCHES


async def test_pending_match_closed_by_block_does_not_expire_later(new_chat, sessionmaker, bot):
    from datetime import timedelta

    from bot.db.models import utcnow
    from bot.jobs import expire_matches_once

    anya, oleg = await woman_and_man(new_chat)
    await like_each_other(oleg, anya)
    await oleg.press(f"blockyes:{anya.user_id}")

    assert await expire_matches_once(bot, sessionmaker, utcnow() + timedelta(hours=25)) == 0
    await anya.press(write_button(anya))
    assert anya.last_text == strings.CANNOT_WRITE_UNAVAILABLE


# --- Report ---


async def test_report_saves_blocks_and_tells_admins(new_chat, sessionmaker, admin):
    anya, oleg = await chatting_pair(new_chat)

    await oleg.press(f"report:{anya.user_id}")
    assert oleg.last_text == strings.ASK_REPORT_REASON
    await oleg.press(f"reportwhy:{anya.user_id}:rude")

    assert oleg.last_text == strings.REPORT_SENT
    assert await count(sessionmaker, Report, Report.reason == "rude") == 1
    assert await count(sessionmaker, Block, Block.blocker_id == oleg.user_id) == 1
    assert await match_status(sessionmaker) == matching.CLOSED

    assert "Оскорбления" in admin.last_text
    assert str(anya.user_id) in admin.last_text
    assert f"ban:{anya.user_id}" in admin.buttons
    assert admin.photos[-1].photo == "Аня-photo-0"


async def test_report_with_unknown_reason_is_ignored(new_chat, sessionmaker):
    anya, oleg = await woman_and_man(new_chat)
    await oleg.press(f"reportwhy:{anya.user_id}:boring")

    assert await count(sessionmaker, Report) == 0


async def test_cannot_report_or_block_yourself(chat, sessionmaker):
    await chat.register()
    await chat.press(f"reportwhy:{chat.user_id}:fake")
    await chat.press(f"blockyes:{chat.user_id}")

    assert await count(sessionmaker, Report) == 0
    assert await count(sessionmaker, Block) == 0


# --- Ban ---


async def test_admin_bans_from_report(new_chat, sessionmaker, admin):
    anya, oleg = await chatting_pair(new_chat)
    await oleg.press(f"reportwhy:{anya.user_id}:fake")

    await admin.press(f"ban:{anya.user_id}")

    assert admin.last_text == strings.ADMIN_BANNED.format(user_id=anya.user_id)
    assert anya.last_text == strings.BANNED
    assert await count(sessionmaker, Ban) == 1


async def test_banned_user_is_stopped_and_hidden(new_chat, admin):
    anya, oleg = await woman_and_man(new_chat)
    await admin.send_text(f"/ban {anya.user_id} спам")

    await anya.send_text("/browse")
    assert anya.last_text == strings.BANNED
    await oleg.send_text("/browse")
    assert oleg.last_text == strings.NO_MORE_PROFILES


async def test_ban_closes_conversations(new_chat, sessionmaker, admin):
    anya, oleg = await chatting_pair(new_chat)
    await oleg.press(write_button(oleg))

    await admin.send_text(f"/ban {anya.user_id}")
    await oleg.send_text("Привет?")

    assert oleg.last_text == strings.CANNOT_WRITE_UNAVAILABLE
    assert await match_status(sessionmaker) == matching.CLOSED


async def test_unban(new_chat, admin):
    anya, oleg = await woman_and_man(new_chat)
    await admin.send_text(f"/ban {anya.user_id}")
    await admin.send_text(f"/ban {anya.user_id}")
    assert admin.last_text == strings.ADMIN_ALREADY_BANNED.format(user_id=anya.user_id)

    await admin.send_text(f"/unban {anya.user_id}")
    assert admin.last_text == strings.ADMIN_UNBANNED.format(user_id=anya.user_id)
    await anya.send_text("/browse")
    assert oleg.user_id in anya.shown_ids


async def test_ban_needs_admin(new_chat, sessionmaker):
    anya, oleg = await woman_and_man(new_chat)

    await oleg.send_text(f"/ban {anya.user_id}")
    await oleg.press(f"ban:{anya.user_id}")

    assert oleg.texts[-1] == strings.UNKNOWN
    assert await count(sessionmaker, Ban) == 0


async def test_ban_usage(admin):
    await admin.send_text("/ban")
    assert admin.last_text == strings.ADMIN_USAGE
    await admin.send_text("/ban кто-то")
    assert admin.last_text == strings.ADMIN_USAGE


# --- Delete account ---


async def test_delete_me_asks_first(chat, sessionmaker):
    await chat.register()
    await chat.send_text("/delete_me")
    assert chat.last_text == strings.ASK_DELETE_CONFIRM

    await chat.press("delete:no")
    assert chat.last_text == strings.DELETE_CANCELLED
    assert await count(sessionmaker, Profile) == 1


async def test_delete_me_removes_everything(new_chat, sessionmaker):
    anya, oleg = await chatting_pair(new_chat)
    ivan = new_chat("Иван")
    await ivan.register(gender="male", pref="women")
    await ivan.send_text("/browse")
    await ivan.press(f"swipe:like:{anya.user_id}")
    await ivan.press(f"report:{anya.user_id}")
    await ivan.press(f"reportwhy:{anya.user_id}:fake")

    await anya.send_text("/delete_me")
    await anya.press("delete:yes")

    assert anya.last_text == strings.DELETED
    uid = anya.user_id
    assert await count(sessionmaker, User, User.id == uid) == 0
    assert await count(sessionmaker, Profile, Profile.user_id == uid) == 0
    assert await count(sessionmaker, Photo, Photo.user_id == uid) == 0
    assert await count(sessionmaker, Swipe, (Swipe.viewer_id == uid) | (Swipe.target_id == uid)) == 0
    assert await count(sessionmaker, Match) == 0
    assert await count(sessionmaker, ChatMessage) == 0
    assert await count(sessionmaker, Report) == 0
    assert await count(sessionmaker, Block) == 0
    # Other people's data is untouched.
    assert await count(sessionmaker, Profile) == 2


async def test_partner_cannot_write_after_delete(new_chat):
    anya, oleg = await chatting_pair(new_chat)
    await oleg.press(write_button(oleg))
    await anya.send_text("/delete_me")
    await anya.press("delete:yes")

    await oleg.send_text("Привет?")

    assert oleg.last_text == strings.STALE_BUTTON


async def test_can_sign_up_again_after_delete(chat, sessionmaker):
    await chat.register()
    await chat.send_text("/delete_me")
    await chat.press("delete:yes")

    await chat.send_text("/start")

    assert chat.texts[-2:] == [strings.WELCOME, strings.ASK_ADULT]


async def test_banned_user_can_delete_but_not_return(new_chat, sessionmaker, admin):
    anya, oleg = await woman_and_man(new_chat)
    await admin.send_text(f"/ban {anya.user_id}")

    await anya.send_text("/delete_me")
    await anya.press("delete:yes")
    assert anya.last_text == strings.DELETED
    assert await count(sessionmaker, Profile, Profile.user_id == anya.user_id) == 0

    await anya.send_text("/start")
    assert anya.last_text == strings.BANNED
    assert await count(sessionmaker, Ban) == 1
