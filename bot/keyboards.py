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


def swipe(target_id: int) -> InlineKeyboardMarkup:
    return _keyboard(
        [
            (strings.BTN_LIKE, f"swipe:like:{target_id}"),
            (strings.BTN_PASS, f"swipe:pass:{target_id}"),
        ]
    )


def redo() -> InlineKeyboardMarkup:
    return _keyboard([(strings.BTN_REDO, "profile:redo")])


def photos_done() -> InlineKeyboardMarkup:
    return _keyboard([(strings.BTN_PHOTOS_DONE, "photos:done")])
