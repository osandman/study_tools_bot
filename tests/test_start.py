import pytest
from sqlalchemy import select

from database.models import User, Subject, DEFAULT_SUBJECTS
from bot.handlers.start import cmd_start


@pytest.mark.asyncio
async def test_start_new_user(tg_message, session):
    await cmd_start(tg_message, session)

    tg_message.answer.assert_called_once()
    text = tg_message.answer.call_args[0][0]
    assert "Привет" in text

    result = await session.execute(
        select(User).where(User.telegram_id == tg_message.from_user.id)
    )
    user = result.scalar_one()
    assert user.username == "testuser"

    result = await session.execute(
        select(Subject).where(Subject.user_id == user.id)
    )
    subjects = result.scalars().all()
    assert len(subjects) == len(DEFAULT_SUBJECTS)


@pytest.mark.asyncio
async def test_start_existing_user(tg_message, session, registered_user):
    await cmd_start(tg_message, session)

    text = tg_message.answer.call_args[0][0]
    assert "возвращением" in text

    result = await session.execute(
        select(User).where(User.telegram_id == tg_message.from_user.id)
    )
    user = result.scalar_one()
    assert user.username == "testuser"


@pytest.mark.asyncio
async def test_start_blocked_user_denied(tg_message, session, registered_user):
    registered_user.is_blocked = True
    await session.commit()

    await cmd_start(tg_message, session)

    text = tg_message.answer.call_args[0][0]
    assert "ограничен" in text.lower()
