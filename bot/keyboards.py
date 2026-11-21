"""Inline keyboards. Each button sends back a short code such as "gender:female"."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot import strings


def _keyboard(*rows: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=text, callback_data=data) for text, data in row]
            for row in rows
        ]
    )


def adult() -> InlineKeyboardMarkup:
    return _keyboard(
        [(strings.BTN_ADULT_YES, "adult:yes"), (strings.BTN_ADULT_NO, "adult:no")]
    )


def consent() -> InlineKeyboardMarkup:
    return _keyboard(
        [(strings.BTN_CONSENT_YES, "consent:yes"), (strings.BTN_CONSENT_NO, "consent:no")]
    )


def gender() -> InlineKeyboardMarkup:
    return _keyboard(
        [(strings.BTN_GENDER_FEMALE, "gender:female"), (strings.BTN_GENDER_MALE, "gender:male")]
    )


def preference() -> InlineKeyboardMarkup:
    return _keyboard(
        [(strings.BTN_PREF_WOMEN, "pref:women"), (strings.BTN_PREF_MEN, "pref:men")],
        [(strings.BTN_PREF_EVERYONE, "pref:everyone")],
    )


def city() -> InlineKeyboardMarkup:
    return _keyboard(
        [(strings.BTN_CITY_SPB, "city:spb"), (strings.BTN_CITY_OTHER, "city:other")]
    )


def _safety_row(user_id: int) -> list[tuple[str, str]]:
    """Report and Block, shown on every profile and conversation."""
    return [
        (strings.BTN_REPORT, f"report:{user_id}"),
        (strings.BTN_BLOCK, f"block:{user_id}"),
    ]


def swipe(target_id: int) -> InlineKeyboardMarkup:
    return _keyboard(
        [
            (strings.BTN_LIKE, f"swipe:like:{target_id}"),
            (strings.BTN_PASS, f"swipe:pass:{target_id}"),
        ],
        _safety_row(target_id),
    )


# All chat entry buttons send "write:<match id>". The handler decides whether
# that means writing the first message or continuing the conversation.


def write(match_id: int, other_id: int) -> InlineKeyboardMarkup:
    return _keyboard([(strings.BTN_WRITE, f"write:{match_id}")], _safety_row(other_id))


def open_chat(match_id: int, other_id: int) -> InlineKeyboardMarkup:
    return _keyboard([(strings.BTN_OPEN_CHAT, f"write:{match_id}")], _safety_row(other_id))


def reply(match_id: int, other_id: int) -> InlineKeyboardMarkup:
    return _keyboard([(strings.BTN_REPLY, f"write:{match_id}")], _safety_row(other_id))


def safety(user_id: int) -> InlineKeyboardMarkup:
    return _keyboard(_safety_row(user_id))


def report_reasons(user_id: int) -> InlineKeyboardMarkup:
    return _keyboard(
        *[
            [(label, f"reportwhy:{user_id}:{reason}")]
            for reason, label in strings.REPORT_REASON_LABELS.items()
        ]
    )


def block_confirm(user_id: int) -> InlineKeyboardMarkup:
    return _keyboard(
        [(strings.BTN_BLOCK_YES, f"blockyes:{user_id}"), (strings.BTN_BLOCK_NO, "blockno")]
    )


def delete_confirm() -> InlineKeyboardMarkup:
    return _keyboard(
        [(strings.BTN_DELETE_YES, "delete:yes"), (strings.BTN_DELETE_NO, "delete:no")]
    )


def ban(user_id: int) -> InlineKeyboardMarkup:
    return _keyboard([(strings.BTN_BAN, f"ban:{user_id}")])


def redo() -> InlineKeyboardMarkup:
    return _keyboard([(strings.BTN_REDO, "profile:redo")])


def photos_done() -> InlineKeyboardMarkup:
    return _keyboard([(strings.BTN_PHOTOS_DONE, "photos:done")])
