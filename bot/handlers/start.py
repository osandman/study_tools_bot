from aiogram import Router, types
from aiogram.filters import CommandStart
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards import get_main_menu
from database.models.user import User
from database.models.subject import Subject, DEFAULT_SUBJECTS

router = Router()


@router.message(CommandStart())
async def cmd_start(message: types.Message, session: AsyncSession):
    """Handle /start command — auto-register or welcome back."""
    telegram_id = message.from_user.id

    # Check if user exists
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()

    if user is None:
        # Register new user
        user = User(
            telegram_id=telegram_id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name,
            language_code=message.from_user.language_code,
        )
        session.add(user)
        await session.flush()  # получаем user.id

        # Create default subjects
        for i, name in enumerate(DEFAULT_SUBJECTS):
            session.add(Subject(user_id=user.id, name=name, is_default=True, sort_order=i))

        await session.commit()

        await message.answer(
            f"👋 Привет, {message.from_user.first_name}!\n\n"
            "Я — Study Tools Bot, твой помощник в учёбе.\n\n"
            "📚 Что я умею:\n"
            "• Вести список предметов\n"
            "• Сохранять и считать оценки\n"
            "• Показывать средний балл\n"
            "• Подсказывать, сколько оценок нужно до цели\n\n"
            "Главное меню уже доступно кнопками ниже.",
            reply_markup=get_main_menu(),
        )
    else:
        # Update user info if changed
        if user.username != message.from_user.username:
            user.username = message.from_user.username
            await session.commit()

        await message.answer(
            f"С возвращением, {message.from_user.first_name}! 👋\n\n"
            "Выбирай нужный раздел в меню ниже.",
            reply_markup=get_main_menu(),
        )
