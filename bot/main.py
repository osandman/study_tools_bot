import asyncio
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.base import BaseSession
from aiogram.enums import ParseMode
from aiogram.types import BotCommand, BotCommandScopeDefault, BotCommandScopeAllPrivateChats
from loguru import logger

from config import settings
from database.base import engine
from database.schema import apply_migrations
from bot.middlewares import DatabaseMiddleware, IgnoreMessageNotModified
from bot.handlers import get_handlers_router


def setup_logging():
    logger.remove()
    logger.add(
        sys.stderr,
        level=settings.log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    )


async def on_startup(bot: Bot):
    logger.info("Starting Study Tools Bot...")
    await apply_migrations()
    logger.info("Database migrations applied.")
    commands = [
        BotCommand(command="start", description="Начать работу"),
        BotCommand(command="subjects", description="Мои предметы"),
        BotCommand(command="grades", description="Оценки по предметам"),
        BotCommand(command="summary", description="Сводка оценок"),
        BotCommand(command="settings", description="Настройки"),
        BotCommand(command="help", description="Справка"),
    ]
    # Clear old scopes
    try:
        await bot.delete_my_commands(scope=BotCommandScopeDefault())
        await bot.delete_my_commands(scope=BotCommandScopeAllPrivateChats())
    except Exception:
        pass
    # Set both scopes
    await bot.set_my_commands(commands, scope=BotCommandScopeDefault())
    await bot.set_my_commands(commands, scope=BotCommandScopeAllPrivateChats())
    existing = await bot.get_my_commands(scope=BotCommandScopeDefault())
    logger.info(f"Commands in default scope: {[(c.command, c.description) for c in existing]}")
    existing_private = await bot.get_my_commands(scope=BotCommandScopeAllPrivateChats())
    logger.info(f"Commands in private-chats scope: {[(c.command, c.description) for c in existing_private]}")
    me = await bot.get_me()
    logger.info(f"Bot started: @{me.username}")


async def on_shutdown(bot: Bot):
    logger.info("Shutting down...")
    await engine.dispose()


BOT_DEFAULTS = DefaultBotProperties(parse_mode=ParseMode.HTML)


def build_bot(token: str, session: BaseSession | None = None) -> Bot:
    """Bot with production defaults; e2e tests pass a Telegram API emulator as the session."""
    bot = Bot(token=token, session=session, default=BOT_DEFAULTS)
    bot.session.middleware(IgnoreMessageNotModified())
    return bot


def build_dispatcher() -> Dispatcher:
    """Dispatcher wired exactly as in production; e2e tests reuse it instead of copying the wiring."""
    dp = Dispatcher()

    # Register middleware
    dp.message.middleware(DatabaseMiddleware())
    dp.callback_query.middleware(DatabaseMiddleware())

    # Register routers
    dp.include_router(get_handlers_router())

    # Lifecycle hooks
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    return dp


async def main():
    setup_logging()

    bot = build_bot(settings.bot_token)
    dp = build_dispatcher()

    # Start polling
    await dp.start_polling(bot, allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    asyncio.run(main())
