"""Report, block, /delete_me and admin bans."""

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot import keyboards, strings
from bot.db.models import Profile, Report, User
from bot.handlers.matches import notify
from bot.handlers.profile import format_card
from bot.services import profiles, safety

router = Router()


async def _name(session: AsyncSession, user_id: int) -> str:
    user = await session.get(User, user_id)
    return user.first_name if user else "?"


# --- Report ---


@router.callback_query(F.data.regexp(r"^report:(\d+)$").as_("found"))
async def on_report(callback: CallbackQuery, found) -> None:
    reported_id = int(found.group(1))
    await callback.answer()
    if reported_id == callback.from_user.id:
        return
    await callback.message.answer(
        strings.ASK_REPORT_REASON, reply_markup=keyboards.report_reasons(reported_id)
    )


@router.callback_query(F.data.regexp(r"^reportwhy:(\d+):(\w+)$").as_("found"))
async def on_report_reason(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    admin_ids: list[int],
    found,
) -> None:
    reported_id, reason = int(found.group(1)), found.group(2)
    reporter_id = callback.from_user.id
    if reason not in safety.REPORT_REASONS or reported_id == reporter_id:
        await callback.answer(strings.STALE_BUTTON)
        return
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)

    await safety.report(session, reporter_id, reported_id, reason)
    await state.clear()  # leaves the chat if they were in one
    await callback.message.answer(strings.REPORT_SENT)
    await _tell_admins(callback, session, admin_ids, reporter_id, reported_id, reason)


async def _tell_admins(callback, session, admin_ids, reporter_id, reported_id, reason) -> None:
    total = await session.scalar(
        select(func.count()).select_from(Report).where(Report.reported_id == reported_id)
    )
    text = strings.ADMIN_REPORT.format(
        reporter_name=await _name(session, reporter_id),
        reporter_id=reporter_id,
        reported_name=await _name(session, reported_id),
        reported_id=reported_id,
        reason=strings.REPORT_REASON_LABELS[reason],
        total=total,
    )
    profile = await profiles.get_profile(session, reported_id)
    for admin_id in admin_ids:
        await notify(callback.bot, admin_id, text, keyboards.ban(reported_id))
        if profile is not None:
            try:
                await callback.bot.send_photo(
                    admin_id, profile.photos[0].file_id, caption=format_card(profile)
                )
            except Exception:  # the report itself already went through
                pass


# --- Block ---


@router.callback_query(F.data.regexp(r"^block:(\d+)$").as_("found"))
async def on_block(callback: CallbackQuery, session: AsyncSession, found) -> None:
    blocked_id = int(found.group(1))
    await callback.answer()
    if blocked_id == callback.from_user.id:
        return
    await callback.message.answer(
        strings.ASK_BLOCK_CONFIRM.format(name=await _name(session, blocked_id)),
        reply_markup=keyboards.block_confirm(blocked_id),
    )


@router.callback_query(F.data.regexp(r"^blockyes:(\d+)$").as_("found"))
async def on_block_confirmed(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, found
) -> None:
    blocked_id = int(found.group(1))
    if blocked_id == callback.from_user.id:
        await callback.answer(strings.STALE_BUTTON)
        return
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)
    await safety.block(session, callback.from_user.id, blocked_id)
    await state.clear()
    await callback.message.answer(strings.BLOCKED.format(name=await _name(session, blocked_id)))


@router.callback_query(F.data == "blockno")
async def on_block_cancelled(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(strings.BLOCK_CANCELLED)


# --- Delete account ---


@router.message(Command("delete_me"))
async def cmd_delete_me(message: Message) -> None:
    await message.answer(strings.ASK_DELETE_CONFIRM, reply_markup=keyboards.delete_confirm())


@router.callback_query(F.data.in_({"delete:yes", "delete:no"}))
async def on_delete(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)
    if callback.data == "delete:no":
        await callback.message.answer(strings.DELETE_CANCELLED)
        return
    await profiles.delete_user_data(session, callback.from_user.id)
    await session.commit()
    await state.clear()
    await callback.message.answer(strings.DELETED)


# --- Admin ---


async def _ban(message_or_callback, session, admin_ids, user_id: int, reason: str) -> str:
    admin_id = message_or_callback.from_user.id
    if not await safety.ban(session, user_id, admin_id, reason):
        return strings.ADMIN_ALREADY_BANNED.format(user_id=user_id)
    await notify(message_or_callback.bot, user_id, strings.BANNED)
    return strings.ADMIN_BANNED.format(user_id=user_id)


@router.message(Command("ban", "unban"))
async def cmd_ban(
    message: Message, command: CommandObject, session: AsyncSession, admin_ids: list[int]
) -> None:
    if message.from_user.id not in admin_ids:
        await message.answer(strings.UNKNOWN)
        return
    parts = (command.args or "").split(maxsplit=1)
    if not parts or not parts[0].isdecimal():
        await message.answer(strings.ADMIN_USAGE)
        return
    user_id = int(parts[0])

    if command.command == "unban":
        done = await safety.unban(session, user_id)
        text = strings.ADMIN_UNBANNED if done else strings.ADMIN_NOT_BANNED
        await message.answer(text.format(user_id=user_id))
        return
    reason = parts[1] if len(parts) > 1 else ""
    await message.answer(await _ban(message, session, admin_ids, user_id, reason))


@router.callback_query(F.data.regexp(r"^ban:(\d+)$").as_("found"))
async def on_ban_button(
    callback: CallbackQuery, session: AsyncSession, admin_ids: list[int], found
) -> None:
    if callback.from_user.id not in admin_ids:
        await callback.answer(strings.STALE_BUTTON)
        return
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)
    text = await _ban(callback, session, admin_ids, int(found.group(1)), "report")
    await callback.message.answer(text)
