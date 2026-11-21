from sqlalchemy import select

from bot import strings
from bot.db.models import ChatMessage
from tests.test_matching import like_each_other, woman_and_man, write_button


async def chatting_pair(new_chat):
    """Аня and Олег with a started conversation. Аня is still in the chat."""
    anya, oleg = await woman_and_man(new_chat)
    await like_each_other(oleg, anya)
    await anya.press(write_button(anya))
    await anya.send_text("Привет!")
    return anya, oleg


async def test_man_can_reply_after_she_starts(new_chat):
    anya, oleg = await chatting_pair(new_chat)

    await oleg.press(write_button(oleg))
    assert oleg.last_text == strings.CHAT_OPENED.format(name="Аня")
    await oleg.send_text("Привет, Аня!")

    assert anya.last_text == strings.RELAYED_MESSAGE.format(name="Олег", text="Привет, Аня!")


async def test_conversation_goes_back_and_forth(new_chat):
    anya, oleg = await chatting_pair(new_chat)
    await oleg.press(write_button(oleg))

    await oleg.send_text("Как дела?")
    await anya.send_text("Отлично")
    await oleg.send_text("Кофе в субботу?")

    assert anya.last_text == strings.RELAYED_MESSAGE.format(name="Олег", text="Кофе в субботу?")
    # Ordinary messages are not confirmed to the sender, so Аня's reply is Олег's latest.
    assert oleg.last_text == strings.RELAYED_MESSAGE.format(name="Аня", text="Отлично")


async def test_relayed_messages_have_reply_report_and_block(new_chat):
    anya, oleg = await chatting_pair(new_chat)

    last_buttons = oleg.buttons[-3:]
    assert last_buttons == [
        write_button(oleg),
        f"report:{anya.user_id}",
        f"block:{anya.user_id}",
    ]


async def test_no_usernames_are_shared(new_chat):
    anya, oleg = await chatting_pair(new_chat)
    sent_to_oleg = " ".join(oleg.texts)

    assert "@" not in sent_to_oleg
    assert str(anya.user_id) not in sent_to_oleg


async def test_message_text_is_not_stored(new_chat, sessionmaker):
    anya, oleg = await chatting_pair(new_chat)
    await anya.send_text("Секрет")

    async with sessionmaker() as session:
        rows = (await session.scalars(select(ChatMessage))).all()
    assert [(r.sender_id, r.length) for r in rows] == [(anya.user_id, 7), (anya.user_id, 6)]
    assert not hasattr(ChatMessage, "text")


async def test_stop_leaves_the_chat(new_chat):
    anya, oleg = await chatting_pair(new_chat)
    received = len(oleg.texts)

    await anya.send_text("/stop")
    await anya.send_text("Это не должно уйти")

    assert anya.texts[-2:] == [strings.CHAT_LEFT, strings.UNKNOWN]
    assert len(oleg.texts) == received


async def test_stop_outside_a_chat(chat):
    await chat.send_text("/stop")

    assert chat.last_text == strings.NOTHING_TO_CANCEL


async def test_browse_works_from_inside_a_chat(new_chat):
    anya, oleg = await chatting_pair(new_chat)

    await anya.send_text("/browse")

    assert anya.last_text == strings.NO_MORE_PROFILES


async def test_matches_shows_open_chat_button_for_active(new_chat):
    anya, oleg = await chatting_pair(new_chat)

    await oleg.send_text("/matches")

    assert oleg.last_text == strings.MATCH_LINE_ACTIVE.format(name="Аня")
    assert oleg.buttons[-3] == write_button(oleg)
