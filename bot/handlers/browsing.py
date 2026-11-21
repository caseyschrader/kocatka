"""Browsing: /browse shows one profile at a time with Like and Pass buttons."""

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InputMediaPhoto, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot import keyboards, strings
from bot.db.models import Profile
from bot.handlers.matches import announce_match
from bot.handlers.profile import format_card
from bot.services import browsing, matching, profiles

router = Router()


async def show_next(message: Message, session: AsyncSession, viewer: Profile) -> None:
    candidate = await browsing.next_candidate(session, viewer)
    if candidate is None:
        await message.answer(strings.NO_MORE_PROFILES)
        return

    card = format_card(candidate)
    buttons = keyboards.swipe(candidate.user_id)
    if len(candidate.photos) == 1:
        await message.answer_photo(
            candidate.photos[0].file_id, caption=card, reply_markup=buttons
        )
        return
    # Telegram albums cannot carry buttons, so the card follows as its own message.
    await message.answer_media_group(
        [InputMediaPhoto(media=photo.file_id) for photo in candidate.photos]
    )
    await message.answer(card, reply_markup=buttons)


@router.message(Command("browse"))
async def cmd_browse(message: Message, session: AsyncSession) -> None:
    viewer = await profiles.get_profile(session, message.from_user.id)
    if viewer is None:
        await message.answer(strings.NO_PROFILE)
        return
    await show_next(message, session, viewer)


@router.callback_query(F.data.regexp(r"^swipe:(like|pass):(\d+)$").as_("match"))
async def on_swipe(callback: CallbackQuery, session: AsyncSession, match) -> None:
    action, target_id = match.group(1), int(match.group(2))
    viewer = await profiles.get_profile(session, callback.from_user.id)
    if viewer is None or target_id == viewer.user_id:
        await callback.answer(strings.STALE_BUTTON)
        return

    # The other person may have deleted their account since the card was shown.
    target_exists = await session.get(Profile, target_id) is not None
    if target_exists:
        is_new = await browsing.record_swipe(session, viewer.user_id, target_id, action)
        if not is_new:
            # An old card pressed twice. Do not open a second card.
            await callback.answer(strings.STALE_BUTTON)
            await callback.message.edit_reply_markup(reply_markup=None)
            return

    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)
    if target_exists and action == browsing.LIKE:
        match = await matching.create_match_if_mutual(session, viewer.user_id, target_id)
        if match is not None:
            await announce_match(callback.bot, session, match)
    await show_next(callback.message, session, viewer)
