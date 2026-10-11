from aiogram import Router

from bot.handlers.start import router as start_router
from bot.handlers.help import router as help_router
from bot.handlers.grades import router as grades_router, ResetPendingSubjectInput
from bot.handlers.calc import router as calc_router
from bot.handlers.fallback import router as fallback_router


def get_handlers_router() -> Router:
    router = Router()
    # Outer middleware sees every update before routing, whichever router ends up handling it.
    router.message.outer_middleware(ResetPendingSubjectInput())
    router.callback_query.outer_middleware(ResetPendingSubjectInput())
    router.include_router(start_router)
    router.include_router(help_router)
    router.include_router(grades_router)
    router.include_router(calc_router)
    router.include_router(fallback_router)
    return router
