from aiogram import types
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models.user import User


async def get_user_by_telegram_id(session: AsyncSession, telegram_id: int) -> User | None:
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    return result.scalar_one_or_none()


async def require_registered_message(message: types.Message, session: AsyncSession) -> User | None:
    user = await get_user_by_telegram_id(session, message.from_user.id)
    if user is None:
        await message.answer("Сначала нажмите /start, чтобы зарегистрироваться.")
        return None
    return user


async def require_registered_callback(
    callback: types.CallbackQuery,
    session: AsyncSession,
) -> User | None:
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    if user is None:
        await callback.answer("Сначала нажмите /start, чтобы зарегистрироваться.", show_alert=True)
        return None
    return user
