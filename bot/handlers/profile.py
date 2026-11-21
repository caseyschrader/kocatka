from aiogram import Router
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot import keyboards, strings
from bot.db.models import Profile
from bot.services import profiles

router = Router()


def format_card(profile: Profile) -> str:
    return strings.PROFILE_CARD.format(
        name=profile.user.first_name,
        age=profile.age,
        city=profile.city,
        bio=profile.bio,
    )


async def send_profile_card(
    message: Message, profile: Profile, reply_markup: InlineKeyboardMarkup | None = None
) -> None:
    """Sends the first photo with the profile text as its caption."""
    await message.answer_photo(
        profile.photos[0].file_id, caption=format_card(profile), reply_markup=reply_markup
    )


@router.message(Command("profile"))
async def cmd_profile(message: Message, session: AsyncSession) -> None:
    profile = await profiles.get_profile(session, message.from_user.id)
    if profile is None:
        await message.answer(strings.NO_PROFILE)
        return
    await send_profile_card(message, profile, reply_markup=keyboards.redo())
