from aiogram import Router, F, types

router = Router()


@router.message(F.text.startswith("/"))
async def cmd_unknown(message: types.Message):
    await message.answer(
        "Неизвестная команда 🤔\n"
        "Попробуй одну из доступных: /start, /subjects, /grades, /calc, /settings, /help"
    )
