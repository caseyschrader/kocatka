"""Builds the dispatcher. Shared by the real bot and the tests."""

from aiogram import Dispatcher
from aiogram.fsm.storage.memory import SimpleEventIsolation

from bot.db.session import DbSessionMiddleware
from bot.handlers import build_router


def build_dispatcher() -> Dispatcher:
    # SimpleEventIsolation handles one update per user at a time. Without it,
    # an album of three photos would be processed in parallel and could race.
    dispatcher = Dispatcher(events_isolation=SimpleEventIsolation())
    dispatcher.update.outer_middleware(DbSessionMiddleware())
    dispatcher.include_router(build_router())
    return dispatcher
