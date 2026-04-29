from aiogram import Router, types
from aiogram.filters import Command

from bot.keyboards import get_main_menu

router = Router()


@router.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer(
        "📖 <b>Команды Study Tools Bot</b>\n\n"
        "Для первого запуска нажми /start.\n\n"
        "🏠 <b>Основные:</b>\n"
        "/start — Начать работу\n"
        "/help — Показать справку\n\n"
        "📚 <b>Учёба:</b>\n"
        "/subjects — Мои предметы\n"
        "/grades — Оценки по предметам\n"
        "/gpa — Средний балл\n"
        "/calc — Калькулятор оценок\n\n"
        "⚙️ <b>Настройки:</b>\n"
        "/settings — Система периодов",
        parse_mode="HTML",
        reply_markup=get_main_menu(),
    )
