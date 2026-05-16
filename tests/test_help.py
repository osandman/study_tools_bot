import pytest

from bot.handlers.help import cmd_help


@pytest.mark.asyncio
async def test_help_command(tg_message):
    await cmd_help(tg_message)

    tg_message.answer.assert_called_once()
    text = tg_message.answer.call_args[0][0]
    assert "Как пользоваться ботом" in text
    assert "/subjects — Предметы" in text
    assert "/grades — Оценки" in text
    assert "/calc — Калькулятор" in text
    assert "/settings — Настройки" in text
