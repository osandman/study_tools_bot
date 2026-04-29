from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


def get_main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="/subjects"), KeyboardButton(text="/grades")],
            [KeyboardButton(text="/gpa"), KeyboardButton(text="/calc")],
            [KeyboardButton(text="/settings"), KeyboardButton(text="/help")],
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Выберите раздел",
    )
