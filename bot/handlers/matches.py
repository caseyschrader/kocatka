"""Match announcements, the first message, /matches, and expiry notices."""

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

MAX_FIRST_MESSAGE = 1000

CANNOT_WRITE = {
    matching.NOT_ALLOWED: strings.CANNOT_WRITE_NOT_ALLOWED,
    matching.TOO_LATE: strings.CANNOT_WRITE_TOO_LATE,
    matching.ALREADY_STARTED: strings.CANNOT_WRITE_ALREADY_STARTED,
    matching.NOT_FOUND: strings.STALE_BUTTON,
}


class WriteFirst(StatesGroup):
    text = State()


async def notify(
    bot: Bot, user_id: int, text: str, reply_markup: InlineKeyboardMarkup | None = None
) -> None:
    """Sends a message to a user. If they blocked the bot, logs it and moves on."""
    try:
        await bot.send_message(user_id, text, reply_markup=reply_markup)
    except TelegramAPIError:
        logger.warning("could not message user %s", user_id, exc_info=True)


async def _name(session: AsyncSession, user_id: int) -> str:
    user = await session.get(User, user_id)
    return user.first_name if user else "?"


async def announce_match(bot: Bot, session: AsyncSession, match) -> None:
    starters = await matching.allowed_starters(session, match)
    for user_id in (match.user_a, match.user_b):
        name = await _name(session, matching.other_user(match, user_id))
        if len(starters) == 2:
            await notify(
                bot, user_id, strings.MATCH_EITHER_WRITES.format(name=name),
                keyboards.write(match.id),
            )
        elif user_id in starters:
            await notify(
                bot, user_id, strings.MATCH_YOU_WRITE_FIRST.format(name=name),
                keyboards.write(match.id),
            )
        else:
            await notify(bot, user_id, strings.MATCH_SHE_WRITES_FIRST.format(name=name))


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


@router.callback_query(F.data.regexp(r"^write:(\d+)$").as_("found"))
async def on_write(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, found
) -> None:
    match_id = int(found.group(1))
    outcome, match = await matching.check_can_start(session, match_id, callback.from_user.id)
    await callback.answer()
    if outcome != matching.OK:
        await callback.message.answer(CANNOT_WRITE[outcome])
        return
    name = await _name(session, matching.other_user(match, callback.from_user.id))
    await state.clear()
    await state.set_state(WriteFirst.text)
    await state.update_data(match_id=match_id)
    await callback.message.answer(strings.ASK_FIRST_MESSAGE.format(name=name))


@router.message(WriteFirst.text, Command("cancel"))
async def on_write_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(strings.WRITE_CANCELLED)


@router.message(WriteFirst.text, F.text, ~F.text.startswith("/"))
async def on_first_message(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if len(message.text) > MAX_FIRST_MESSAGE:
        await message.answer(strings.FIRST_MESSAGE_TOO_LONG)
        return
    match_id = (await state.get_data())["match_id"]
    await state.clear()

    sender_id = message.from_user.id
    outcome = await matching.start_conversation(session, match_id, sender_id)
    if outcome != matching.OK:
        await message.answer(CANNOT_WRITE[outcome])
        return

    match = await matching.get_match(session, match_id)
    await notify(
        message.bot,
        matching.other_user(match, sender_id),
        strings.FIRST_MESSAGE_RECEIVED.format(
            name=await _name(session, sender_id), text=message.text
        ),
    )
    await message.answer(strings.FIRST_MESSAGE_SENT)


@router.message(WriteFirst.text, ~F.text)
async def on_first_message_not_text(message: Message) -> None:
    await message.answer(strings.TEXT_ONLY)


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
        name = await _name(session, matching.other_user(match, user_id))
        if match.status == matching.ACTIVE:
            await message.answer(strings.MATCH_LINE_ACTIVE.format(name=name))
            continue
        seconds_left = (as_utc(match.expires_at) - now).total_seconds()
        hours = max(1, math.ceil(seconds_left / 3600))
        if user_id in await matching.allowed_starters(session, match):
            await message.answer(
                strings.MATCH_LINE_YOUR_TURN.format(name=name, hours=hours),
                reply_markup=keyboards.write(match.id),
            )
        else:
            await message.answer(strings.MATCH_LINE_WAITING.format(name=name, hours=hours))
