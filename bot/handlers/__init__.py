from aiogram import Router

from bot.handlers import browsing, fallback, onboarding, profile


def build_router() -> Router:
    """Collects every feature router into one. Order matters: first match wins."""
    router = Router()
    router.include_router(profile.router)
    router.include_router(browsing.router)
    router.include_router(onboarding.router)
    router.include_router(fallback.router)  # always last
    return router
