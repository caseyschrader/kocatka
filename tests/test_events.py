"""Events logged by real bot flows."""

from datetime import timedelta

from sqlalchemy import or_, select

from bot.db.models import Event, utcnow
from bot.jobs import expire_matches_once
from tests.test_chat import chatting_pair
from tests.test_matching import like_each_other, woman_and_man, write_button


async def all_events(sessionmaker) -> list[Event]:
    async with sessionmaker() as session:
        return list((await session.scalars(select(Event).order_by(Event.event_id))).all())


async def types(sessionmaker) -> list[str]:
    return [e.event_type for e in await all_events(sessionmaker)]


async def of_type(sessionmaker, event_type: str) -> list[Event]:
    return [e for e in await all_events(sessionmaker) if e.event_type == event_type]


async def test_signup_events(chat, sessionmaker):
    await chat.register(age="27", photos=2)

    started, completed = await all_events(sessionmaker)
    assert (started.event_type, started.user_id) == ("signup_started", None)
    assert (completed.event_type, completed.user_id) == ("signup_completed", chat.user_id)
    assert completed.properties == {"gender": "female", "age": 27, "photos": 2}


async def test_stopped_signup_leaves_no_user_id(chat, sessionmaker):
    await chat.send_text("/start")
    await chat.press("adult:no")

    events = await all_events(sessionmaker)
    assert [(e.event_type, e.user_id, e.properties) for e in events] == [
        ("signup_started", None, {}),
        ("signup_stopped", None, {"reason": "underage"}),
    ]


async def test_stop_reasons(new_chat, sessionmaker):
    no_consent, cancelled, elsewhere = new_chat("А"), new_chat("Б"), new_chat("В")
    await no_consent.send_text("/start")
    await no_consent.press("adult:yes")
    await no_consent.press("consent:no")
    await cancelled.send_text("/start")
    await cancelled.send_text("/cancel")
    await elsewhere.send_text("/start")
    for step in ("adult:yes", "consent:yes", "gender:male", "pref:women"):
        await elsewhere.press(step)
    await elsewhere.send_text("30")
    await elsewhere.send_text("20-30")
    await elsewhere.press("city:other")

    reasons = [e.properties["reason"] for e in await of_type(sessionmaker, "signup_stopped")]
    assert reasons == ["no_consent", "cancelled", "other_city"]


async def test_redo_logs_profile_updated(chat, sessionmaker):
    await chat.register()
    await chat.send_text("/profile")
    await chat.press("profile:redo")
    for step in ("gender:female", "pref:everyone"):
        await chat.press(step)
    await chat.send_text("28")
    await chat.send_text("20-40")
    await chat.press("city:spb")
    await chat.send_text("Снова я")
    await chat.send_photo("p")
    await chat.press("photos:done")

    assert await types(sessionmaker) == ["signup_started", "signup_completed", "profile_updated"]


async def test_browse_match_and_chat_events(new_chat, sessionmaker):
    anya, oleg = await chatting_pair(new_chat)
    await oleg.press(write_button(oleg))
    await oleg.send_text("Привет!")

    seen = [t for t in await types(sessionmaker) if not t.startswith("signup")]
    assert seen == [
        "profile_viewed", "like",  # Олег sees and likes Аня
        "profile_viewed", "like", "match_created",  # Аня likes back
        "first_message_sent", "message_sent",  # Аня writes first
        "message_sent",  # Олег replies
    ]
    like = (await of_type(sessionmaker, "like"))[0]
    assert (like.user_id, like.target_id) == (oleg.user_id, anya.user_id)

    match_created, = await of_type(sessionmaker, "match_created")
    assert match_created.properties["same_gender"] is False
    first, = await of_type(sessionmaker, "first_message_sent")
    assert (first.user_id, first.target_id) == (anya.user_id, oleg.user_id)
    assert first.properties["match_id"] == match_created.properties["match_id"]
    assert 0 <= first.properties["seconds_since_match"] < 60
    lengths = [e.properties["length"] for e in await of_type(sessionmaker, "message_sent")]
    assert lengths == [len("Привет!"), len("Привет!")]


async def test_pass_and_expiry_events(new_chat, sessionmaker, bot):
    anya, oleg = await woman_and_man(new_chat)
    ivan = new_chat("Иван")
    await ivan.register(gender="male", pref="women")
    await like_each_other(oleg, anya)
    await ivan.send_text("/browse")
    await ivan.press(f"swipe:pass:{anya.user_id}")

    await expire_matches_once(bot, sessionmaker, utcnow() + timedelta(hours=25))

    assert len(await of_type(sessionmaker, "pass")) == 1
    expired, = await of_type(sessionmaker, "match_expired")
    assert {expired.user_id, expired.target_id} == {anya.user_id, oleg.user_id}


async def test_block_report_and_ban_events(new_chat, sessionmaker, admin):
    anya, oleg = await chatting_pair(new_chat)
    await oleg.press(f"reportwhy:{anya.user_id}:rude")
    await admin.send_text(f"/ban {anya.user_id}")

    report, = await of_type(sessionmaker, "report")
    assert (report.user_id, report.target_id, report.properties) == (
        oleg.user_id, anya.user_id, {"reason": "rude"}
    )
    block, = await of_type(sessionmaker, "block")
    assert block.properties == {"via_report": True}
    closed, = await of_type(sessionmaker, "match_closed")
    assert closed.properties["reason"] == "report"
    banned, = await of_type(sessionmaker, "user_banned")
    assert banned.user_id == anya.user_id


async def test_plain_block_closes_with_reason_block(new_chat, sessionmaker):
    anya, oleg = await woman_and_man(new_chat)
    await like_each_other(oleg, anya)
    await anya.press(f"blockyes:{oleg.user_id}")

    block, = await of_type(sessionmaker, "block")
    assert block.properties == {"via_report": False}
    closed, = await of_type(sessionmaker, "match_closed")
    assert closed.properties["reason"] == "block"


async def test_delete_me_anonymises_events(new_chat, sessionmaker):
    anya, oleg = await chatting_pair(new_chat)
    async with sessionmaker() as session:
        signup = (await session.scalars(
            select(Event).where(
                Event.event_type == "signup_completed", Event.user_id == anya.user_id
            )
        )).one()
        signup_id = signup.event_id
    before = len(await all_events(sessionmaker))

    await anya.send_text("/delete_me")
    await anya.press("delete:yes")

    events = await all_events(sessionmaker)
    uid = anya.user_id
    assert not [e for e in events if uid in (e.user_id, e.target_id)]
    assert len(events) == before + 1  # history kept, plus account_deleted

    deleted, = [e for e in events if e.event_type == "account_deleted"]
    pseudonym = deleted.user_id
    assert pseudonym < 0
    # The same pseudonym everywhere, so retention and conversion still add up.
    assert next(e for e in events if e.event_id == signup_id).user_id == pseudonym
    oleg_like = next(e for e in events if e.event_type == "like" and e.user_id == oleg.user_id)
    assert oleg_like.target_id == pseudonym


async def test_two_deletions_get_different_pseudonyms(new_chat, sessionmaker):
    anya, oleg = await woman_and_man(new_chat)
    for person in (anya, oleg):
        await person.send_text("/delete_me")
        await person.press("delete:yes")

    async with sessionmaker() as session:
        ids = (await session.scalars(
            select(Event.user_id).where(Event.event_type == "account_deleted")
        )).all()
        leftover = (await session.scalars(
            select(Event).where(or_(Event.user_id > 0, Event.target_id > 0))
        )).all()
    assert len(set(ids)) == 2
    assert leftover == []
