from aiogram import Router, types
from aiogram.filters import Command

router = Router()


@router.message(Command("help"))
async def cmd_help(message: types.Message):
    """Show help message with all available commands."""
    await message.answer(
        "📖 <b>Команды Study Tools Bot</b>\n\n"
        "🏠 <b>Основные:</b>\n"
        "/start — Начать работу\n"
        "/help — Показать справку\n"
        "/profile — Мой профиль\n\n"
        "📚 <b>Учёба:</b>\n"
        "/subjects — Мои предметы\n"
        "/grades — Оценки по предметам\n"
        "/gpa — Средний балл\n"
        "/calc — Калькулятор оценок\n"
        "/schedule — Расписание\n"
        "/notes — Заметки\n"
        "/deadlines — Дедлайны\n\n"
        "⚙️ <b>Настройки:</b>\n"
        "/settings — Настройки бота",
        parse_mode="HTML",
    )
