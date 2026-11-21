from aiogram import Router

from bot.handlers import start


def build_router() -> Router:
    """Collects every feature router into one. New features get added here."""
    router = Router()
    router.include_router(start.router)
    return router
