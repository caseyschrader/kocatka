"""Onboarding conversation: /start through to a saved profile.

Answers are kept in memory (the FSM state) until the last step. Nothing is
written to the database before the user has consented and finished the flow.
"""

from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message, User
from sqlalchemy.ext.asyncio import AsyncSession

from bot import keyboards, strings
from bot.handlers.profile import send_profile_card
from bot.services import events, profiles

router = Router()


class Onboarding(StatesGroup):
    adult = State()
    consent = State()
    gender = State()
    preference = State()
    age = State()
    age_range = State()
    city = State()
    bio = State()
    photos = State()


BUTTON_STEPS = (
    Onboarding.adult,
    Onboarding.consent,
    Onboarding.gender,
    Onboarding.preference,
    Onboarding.city,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _signup_stopped(session: AsyncSession, reason: str) -> None:
    """Logged without a user id: the person has not consented, so nothing identifies them."""
    events.log_event(session, "signup_stopped", reason=reason)
    await session.commit()


async def _close_keyboard(callback: CallbackQuery) -> None:
    """Stops the button spinner and removes the buttons so they cannot be reused."""
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)


# --- Commands. Registered first so they win over the text steps below. ---


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, session: AsyncSession) -> None:
    profile = await profiles.get_profile(session, message.from_user.id)
    if profile is not None:
        await message.answer(strings.ALREADY_REGISTERED)
        await send_profile_card(message, profile, reply_markup=keyboards.redo())
        return

    await state.clear()
    await state.set_state(Onboarding.adult)
    events.log_event(session, "signup_started")  # no user id before consent
    await session.commit()
    await message.answer(strings.WELCOME)
    await message.answer(strings.ASK_ADULT, reply_markup=keyboards.adult())


@router.callback_query(F.data == "profile:redo")
async def on_redo(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    """Fills the profile in again. 18+ and consent were already given, so they are skipped.

    The old profile stays live until the new one is finished.
    """
    profile = await profiles.get_profile(session, callback.from_user.id)
    if profile is None:
        await callback.answer(strings.STALE_BUTTON)
        return
    await _close_keyboard(callback)
    await state.clear()
    await state.update_data(
        redo=True,
        adult_confirmed_at=profile.user.adult_confirmed_at.isoformat(),
        consented_at=profile.user.consented_at.isoformat(),
    )
    await state.set_state(Onboarding.gender)
    await callback.message.answer(strings.REDO_START)
    await callback.message.answer(strings.ASK_GENDER, reply_markup=keyboards.gender())


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if await state.get_state() is None:
        await message.answer(strings.NOTHING_TO_CANCEL)
        return
    is_redo = (await state.get_data()).get("redo", False)
    await state.clear()
    if not is_redo:
        await _signup_stopped(session, "cancelled")
    await message.answer(strings.REDO_CANCELLED if is_redo else strings.CANCELLED)


# --- Steps ---


@router.callback_query(Onboarding.adult, F.data.in_({"adult:yes", "adult:no"}))
async def on_adult(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    await _close_keyboard(callback)
    if callback.data == "adult:no":
        await state.clear()
        await _signup_stopped(session, "underage")
        await callback.message.answer(strings.UNDERAGE)
        return
    await state.update_data(adult_confirmed_at=_now())
    await state.set_state(Onboarding.consent)
    await callback.message.answer(strings.ASK_CONSENT, reply_markup=keyboards.consent())


@router.callback_query(Onboarding.consent, F.data.in_({"consent:yes", "consent:no"}))
async def on_consent(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    await _close_keyboard(callback)
    if callback.data == "consent:no":
        await state.clear()
        await _signup_stopped(session, "no_consent")
        await callback.message.answer(strings.CONSENT_DECLINED)
        return
    await state.update_data(consented_at=_now())
    await state.set_state(Onboarding.gender)
    await callback.message.answer(strings.ASK_GENDER, reply_markup=keyboards.gender())


@router.callback_query(Onboarding.gender, F.data.in_({"gender:female", "gender:male"}))
async def on_gender(callback: CallbackQuery, state: FSMContext) -> None:
    await _close_keyboard(callback)
    await state.update_data(gender=callback.data.split(":")[1])
    await state.set_state(Onboarding.preference)
    await callback.message.answer(
        strings.ASK_PREFERENCE, reply_markup=keyboards.preference()
    )


@router.callback_query(
    Onboarding.preference, F.data.in_({"pref:women", "pref:men", "pref:everyone"})
)
async def on_preference(callback: CallbackQuery, state: FSMContext) -> None:
    await _close_keyboard(callback)
    await state.update_data(preference=callback.data.split(":")[1])
    await state.set_state(Onboarding.age)
    await callback.message.answer(strings.ASK_AGE)


@router.message(Onboarding.age, F.text)
async def on_age(message: Message, state: FSMContext, session: AsyncSession) -> None:
    age = profiles.parse_age(message.text)
    if age is None:
        await message.answer(strings.AGE_INVALID)
        return
    if age < profiles.MIN_AGE:
        await state.clear()
        await _signup_stopped(session, "underage")
        await message.answer(strings.UNDERAGE)
        return
    await state.update_data(age=age)
    await state.set_state(Onboarding.age_range)
    await message.answer(strings.ASK_AGE_RANGE)


@router.message(Onboarding.age)
async def on_age_not_text(message: Message) -> None:
    await message.answer(strings.AGE_INVALID)


@router.message(Onboarding.age_range, F.text)
async def on_age_range(message: Message, state: FSMContext) -> None:
    age_range = profiles.parse_age_range(message.text)
    if age_range is None:
        await message.answer(strings.AGE_RANGE_INVALID)
        return
    await state.update_data(age_min=age_range[0], age_max=age_range[1])
    await state.set_state(Onboarding.city)
    await message.answer(strings.ASK_CITY, reply_markup=keyboards.city())


@router.message(Onboarding.age_range)
async def on_age_range_not_text(message: Message) -> None:
    await message.answer(strings.AGE_RANGE_INVALID)


@router.callback_query(Onboarding.city, F.data.in_({"city:spb", "city:other"}))
async def on_city(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    await _close_keyboard(callback)
    if callback.data == "city:other":
        is_redo = (await state.get_data()).get("redo", False)
        await state.clear()
        if not is_redo:
            await _signup_stopped(session, "other_city")
        await callback.message.answer(
            strings.CITY_NOT_SUPPORTED_REDO if is_redo else strings.CITY_NOT_SUPPORTED
        )
        return
    await state.update_data(city=profiles.CITY_SPB)
    await state.set_state(Onboarding.bio)
    await callback.message.answer(strings.ASK_BIO)


@router.message(Onboarding.bio, F.text, ~F.text.startswith("/"))
async def on_bio(message: Message, state: FSMContext) -> None:
    bio = profiles.clean_bio(message.text)
    if bio is None:
        await message.answer(strings.BIO_INVALID)
        return
    await state.update_data(bio=bio, photos=[])
    await state.set_state(Onboarding.photos)
    await message.answer(strings.ASK_PHOTOS)


@router.message(Onboarding.bio)
async def on_bio_not_text(message: Message) -> None:
    await message.answer(strings.BIO_INVALID)


@router.message(Onboarding.photos, F.photo)
async def on_photo(message: Message, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    # Telegram sends several sizes of each photo. The last one is the largest.
    photos = data["photos"] + [message.photo[-1].file_id]
    await state.update_data(photos=photos)

    if len(photos) >= profiles.MAX_PHOTOS:
        await _finish(message, message.from_user, state, session)
        return
    await message.answer(
        strings.PHOTO_ADDED.format(count=len(photos), max=profiles.MAX_PHOTOS),
        reply_markup=keyboards.photos_done(),
    )


@router.message(Onboarding.photos)
async def on_photo_expected(message: Message) -> None:
    await message.answer(strings.PHOTO_EXPECTED)


@router.callback_query(Onboarding.photos, F.data == "photos:done")
async def on_photos_done(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    await _close_keyboard(callback)
    data = await state.get_data()
    if not data.get("photos"):
        await callback.message.answer(strings.PHOTO_NEEDED)
        return
    await _finish(callback.message, callback.from_user, state, session)


@router.message(StateFilter(*BUTTON_STEPS))
async def on_text_instead_of_button(message: Message) -> None:
    await message.answer(strings.USE_BUTTONS)


async def _finish(
    message: Message, user: User, state: FSMContext, session: AsyncSession
) -> None:
    """Writes everything to the database in one go and shows the result."""
    data = await state.get_data()
    profile = await profiles.save_profile(
        session,
        profiles.NewProfile(
            user_id=user.id,
            first_name=user.first_name,
            adult_confirmed_at=datetime.fromisoformat(data["adult_confirmed_at"]),
            consented_at=datetime.fromisoformat(data["consented_at"]),
            gender=data["gender"],
            preference=data["preference"],
            age=data["age"],
            age_min=data["age_min"],
            age_max=data["age_max"],
            city=data["city"],
            bio=data["bio"],
            photo_file_ids=data["photos"],
        ),
    )
    await state.clear()
    await message.answer(strings.PROFILE_SAVED)
    await send_profile_card(message, profile)
    await message.answer(strings.BROWSE_HINT)
