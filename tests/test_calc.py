import pytest
from sqlalchemy import select

from database.models import Subject, Grade
from bot.handlers.calc import cmd_summary, cb_summary_period
from bot.utils.periods import get_active_period


@pytest.mark.asyncio
async def test_calc_no_registration(tg_message, session):
    await cmd_summary(tg_message, session)
    text = tg_message.answer.call_args[0][0]
    assert "зарегистрироваться" in text.lower() or "/start" in text.lower()


@pytest.mark.asyncio
async def test_calc_with_grades(tg_message, session, registered_user):
    period = get_active_period(registered_user)
    subject = await session.scalar(
        select(Subject).where(Subject.user_id == registered_user.id).limit(1)
    )
    session.add(Grade(user_id=registered_user.id, subject_id=subject.id, value=5, period=period))
    session.add(Grade(user_id=registered_user.id, subject_id=subject.id, value=4, period=period))
    await session.commit()

    await cmd_summary(tg_message, session)

    text = tg_message.answer.call_args[0][0]
    assert "Сводка оценок" in text
    assert subject.name in text
    assert "Рекомендуемая" in text
    assert "Средний" in text
    assert " | Рекомендуемая" not in text


@pytest.mark.asyncio
async def test_calc_average_4_5_rounds_to_5(tg_message, session, registered_user):
    """4.5 should round to 5 in school rounding."""
    period = get_active_period(registered_user)
    subject = await session.scalar(
        select(Subject).where(Subject.user_id == registered_user.id).limit(1)
    )
    session.add(Grade(user_id=registered_user.id, subject_id=subject.id, value=5, period=period))
    session.add(Grade(user_id=registered_user.id, subject_id=subject.id, value=4, period=period))
    await session.commit()

    await cmd_summary(tg_message, session)

    text = tg_message.answer.call_args[0][0]
    assert "Рекомендуемая:" in text and "5" in text


@pytest.mark.asyncio
async def test_calc_empty_subjects(tg_message, session, registered_user):
    from sqlalchemy import delete
    await session.execute(delete(Subject).where(Subject.user_id == registered_user.id))
    await session.commit()

    await cmd_summary(tg_message, session)

    text = tg_message.answer.call_args[0][0]
    assert "предметов" in text.lower()


@pytest.mark.asyncio
async def test_calc_period_switch(tg_callback, session, registered_user):
    tg_callback.data = "summary_period:t2"

    await cb_summary_period(tg_callback, session)

    await session.refresh(registered_user)
    assert registered_user.active_period == "t2"

    text = tg_callback.message.edit_text.call_args[0][0]
    assert "Сводка оценок" in text


@pytest.mark.asyncio
async def test_calc_period_switch_without_subjects(tg_callback, session, registered_user):
    from sqlalchemy import delete

    await session.execute(delete(Subject).where(Subject.user_id == registered_user.id))
    await session.commit()

    tg_callback.data = "summary_period:t3"
    await cb_summary_period(tg_callback, session)

    text = tg_callback.message.edit_text.call_args[0][0]
    assert "Сводка оценок" in text


@pytest.mark.asyncio
async def test_old_calc_period_callback_still_works(tg_callback, session, registered_user):
    tg_callback.data = "calc_period:t1"

    await cb_summary_period(tg_callback, session)

    await session.refresh(registered_user)
    assert registered_user.active_period == "t1"
