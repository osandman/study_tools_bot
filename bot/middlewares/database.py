from datetime import datetime, timezone
from typing import Callable, Dict, Any, Awaitable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from database.base import async_session
from database.models.user import User


class DatabaseMiddleware(BaseMiddleware):
    """Provides a database session to handlers via data["session"]."""

    def __init__(self, session_factory: async_sessionmaker = async_session):
        self.session_factory = session_factory

    @staticmethod
    def _extract_telegram_id(event: TelegramObject) -> int | None:
        if isinstance(event, Message) and event.from_user:
            return event.from_user.id
        if isinstance(event, CallbackQuery) and event.from_user:
            return event.from_user.id
        return None

    @staticmethod
    async def _deny_blocked(event: TelegramObject) -> None:
        if isinstance(event, Message):
            await event.answer("Ваш доступ к боту ограничен.")
        elif isinstance(event, CallbackQuery):
            await event.answer("Ваш доступ к боту ограничен.")

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        async with self.session_factory() as session:
            data["session"] = session
            telegram_id = self._extract_telegram_id(event)
            user = None

            if telegram_id is not None:
                result = await session.execute(select(User).where(User.telegram_id == telegram_id))
                user = result.scalar_one_or_none()
                if user is not None:
                    user.last_seen_at = datetime.now(timezone.utc)
                    if user.is_blocked:
                        await session.commit()
                        await self._deny_blocked(event)
                        return None

            response = await handler(event, data)
            await session.commit()
            return response
