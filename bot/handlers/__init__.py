from aiogram import Router

from bot.handlers import browsing, fallback, matches, onboarding, profile, safety


def build_router() -> Router:
    """Collects every feature router into one. Order matters: first match wins."""
    router = Router()
    router.include_router(safety.router)  # /delete_me and admin commands work in any state
    router.include_router(profile.router)
    router.include_router(browsing.router)
    router.include_router(matches.router)  # before onboarding, for its own /cancel
    router.include_router(onboarding.router)
    router.include_router(fallback.router)  # always last
    return router
