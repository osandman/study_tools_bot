import pytest

from bot.handlers.fallback import cmd_unknown


@pytest.mark.asyncio
async def test_unknown_command_gets_reply(tg_message):
    tg_message.text = "/abracadabra_test"

    await cmd_unknown(tg_message)

    text = tg_message.answer.call_args[0][0]
    assert "Неизвестная команда" in text
    assert "/help" in text
