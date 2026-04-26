from aiogram import Router

from bot.handlers.start import router as start_router
from bot.handlers.help import router as help_router


def get_handlers_router() -> Router:
    router = Router()
    router.include_router(start_router)
    router.include_router(help_router)
    return router
