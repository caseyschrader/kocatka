"""Match announcements, the chat relay, /matches, and expiry notices.

Chat works like a mode: a "write:<match id>" button opens a chat with one
person, and every text message is relayed to them until /stop. The first
message in a pending match goes through the women-first check.
"""

import logging
import math

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot import keyboards, strings
from bot.db.models import User, as_utc, utcnow
from bot.services import matching, profiles

router = Router()
logger = logging.getLogger(__name__)

MAX_MESSAGE = 1000

CANNOT_WRITE = {
    matching.NOT_ALLOWED: strings.CANNOT_WRITE_NOT_ALLOWED,
    matching.TOO_LATE: strings.CANNOT_WRITE_TOO_LATE,
    matching.ALREADY_STARTED: strings.CANNOT_WRITE_ALREADY_STARTED,
    matching.UNAVAILABLE: strings.CANNOT_WRITE_UNAVAILABLE,
    matching.NOT_FOUND: strings.STALE_BUTTON,
}


class Chat(StatesGroup):
    active = State()


async def notify(
    bot: Bot, user_id: int, text: str, reply_markup: InlineKeyboardMarkup | None = None
) -> bool:
    """Sends a message to a user. If they stopped the bot, logs it and returns False."""
    try:
        await bot.send_message(user_id, text, reply_markup=reply_markup)
        return True
    except TelegramAPIError:
        logger.warning("could not message user %s", user_id, exc_info=True)
        return False


async def _name(session: AsyncSession, user_id: int) -> str:
    user = await session.get(User, user_id)
    return user.first_name if user else "?"


async def announce_match(bot: Bot, session: AsyncSession, match) -> None:
    starters = await matching.allowed_starters(session, match)
    for user_id in (match.user_a, match.user_b):
        other_id = matching.other_user(match, user_id)
        name = await _name(session, other_id)
        if len(starters) == 2:
            text, markup = strings.MATCH_EITHER_WRITES, keyboards.write(match.id, other_id)
        elif user_id in starters:
            text, markup = strings.MATCH_YOU_WRITE_FIRST, keyboards.write(match.id, other_id)
        else:
            text, markup = strings.MATCH_SHE_WRITES_FIRST, keyboards.safety(other_id)
        await notify(bot, user_id, text.format(name=name), markup)


async def announce_expiry(bot: Bot, session: AsyncSession, match) -> None:
    starters = await matching.allowed_starters(session, match)
    for user_id in (match.user_a, match.user_b):
        name = await _name(session, matching.other_user(match, user_id))
        if len(starters) == 1 and user_id in starters:
            text = strings.EXPIRED_STARTER
        elif len(starters) == 1:
            text = strings.EXPIRED_WAITER
        else:
            text = strings.EXPIRED_EITHER
        await notify(bot, user_id, text.format(name=name))


# --- Opening and leaving a chat ---


@router.callback_query(F.data.regexp(r"^write:(\d+)$").as_("found"))
async def on_write(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, found
) -> None:
    match_id = int(found.group(1))
    user_id = callback.from_user.id
    outcome, match = await matching.check_can_chat(session, match_id, user_id)
    await callback.answer()
    if outcome != matching.OK:
        await callback.message.answer(CANNOT_WRITE[outcome])
        return

    name = await _name(session, matching.other_user(match, user_id))
    await state.clear()
    await state.set_state(Chat.active)
    await state.update_data(match_id=match_id)
    prompt = strings.ASK_FIRST_MESSAGE if match.status == matching.PENDING else strings.CHAT_OPENED
    await callback.message.answer(prompt.format(name=name))


@router.message(Chat.active, Command("stop", "cancel"))
async def on_leave_chat(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(strings.CHAT_LEFT)


@router.message(Command("stop"))
async def on_stop_outside_chat(message: Message) -> None:
    await message.answer(strings.NOTHING_TO_CANCEL)


# --- Sending ---


@router.message(Chat.active, F.text, ~F.text.startswith("/"))
async def on_chat_text(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if len(message.text) > MAX_MESSAGE:
        await message.answer(strings.MESSAGE_TOO_LONG)
        return

    match_id = (await state.get_data())["match_id"]
    sender_id = message.from_user.id
    outcome, match = await matching.check_can_chat(session, match_id, sender_id)
    if outcome != matching.OK:
        await state.clear()
        await message.answer(CANNOT_WRITE[outcome])
        return

    is_first = match.status == matching.PENDING
    if is_first:
        outcome = await matching.start_conversation(session, match_id, sender_id)
        if outcome == matching.ALREADY_STARTED:
            # Same-gender pair and the other person was a moment faster.
            # The conversation is running now, so this goes through as a reply.
            is_first = False
        elif outcome != matching.OK:
            await state.clear()
            await message.answer(CANNOT_WRITE[outcome])
            return

    other_id = matching.other_user(match, sender_id)
    name = await _name(session, sender_id)
    template = strings.FIRST_MESSAGE_RECEIVED if is_first else strings.RELAYED_MESSAGE
    delivered = await notify(
        message.bot,
        other_id,
        template.format(name=name, text=message.text),
        keyboards.reply(match_id, sender_id),
    )
    await matching.record_message(session, match_id, sender_id, len(message.text))
    if not delivered:
        await message.answer(strings.NOT_DELIVERED)
    elif is_first:
        await message.answer(strings.FIRST_MESSAGE_SENT)


@router.message(Chat.active, ~F.text)
async def on_chat_not_text(message: Message) -> None:
    await message.answer(strings.TEXT_ONLY)


# --- /matches ---


@router.message(Command("matches"))
async def cmd_matches(message: Message, session: AsyncSession) -> None:
    user_id = message.from_user.id
    if await profiles.get_profile(session, user_id) is None:
        await message.answer(strings.NO_PROFILE)
        return
    matches = await matching.matches_for(session, user_id)
    if not matches:
        await message.answer(strings.NO_MATCHES)
        return

    await message.answer(strings.MATCHES_HEADER)
    now = utcnow()
    for match in matches:
        other_id = matching.other_user(match, user_id)
        name = await _name(session, other_id)
        if match.status == matching.ACTIVE:
            await message.answer(
                strings.MATCH_LINE_ACTIVE.format(name=name),
                reply_markup=keyboards.open_chat(match.id, other_id),
            )
            continue
        seconds_left = (as_utc(match.expires_at) - now).total_seconds()
        hours = max(1, math.ceil(seconds_left / 3600))
        if user_id in await matching.allowed_starters(session, match):
            await message.answer(
                strings.MATCH_LINE_YOUR_TURN.format(name=name, hours=hours),
                reply_markup=keyboards.write(match.id, other_id),
            )
        else:
            await message.answer(
                strings.MATCH_LINE_WAITING.format(name=name, hours=hours),
                reply_markup=keyboards.safety(other_id),
            )
