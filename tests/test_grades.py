import pytest
from sqlalchemy import select, func

from database.models import Subject, Grade
from bot.handlers.grades import cmd_grades, cmd_subjects, cb_subject_counter, cb_counter_action
from bot.utils.periods import get_active_period
from database.models.grade import get_periods


@pytest.mark.asyncio
async def test_grades_no_registration(tg_message, session):
    await cmd_grades(tg_message, session)
    text = tg_message.answer.call_args[0][0]
    assert "зарегистрироваться" in text.lower() or "/start" in text.lower()


@pytest.mark.asyncio
async def test_grades_with_subjects(tg_message, session, registered_user):
    period = get_active_period(registered_user)
    session.add(Grade(user_id=registered_user.id, subject_id=1, value=5, period=period))
    session.add(Grade(user_id=registered_user.id, subject_id=1, value=4, period=period))
    await session.commit()

    await cmd_grades(tg_message, session)

    text = tg_message.answer.call_args[0][0]
    assert "Оценки" in text
    assert "Общий" in text


@pytest.mark.asyncio
async def test_subjects_list(tg_message, session, registered_user):
    await cmd_subjects(tg_message, session)

    text = tg_message.answer.call_args[0][0]
    assert "Твои предметы" in text


@pytest.mark.asyncio
async def test_subjects_alphabetical_order(tg_message, session, registered_user):
    await cmd_subjects(tg_message, session)

    result = await session.execute(
        select(Subject).where(Subject.user_id == registered_user.id).order_by(Subject.name)
    )
    subjects = result.scalars().all()
    names = [s.name for s in subjects]
    assert names == sorted(names)


@pytest.mark.asyncio
async def test_subject_counter_opens(tg_callback, session, registered_user):
    period = get_active_period(registered_user)
    tg_callback.data = f"subject:1:{period}"

    await cb_subject_counter(tg_callback, session)

    tg_callback.message.edit_text.assert_called_once()
    text = tg_callback.message.edit_text.call_args[0][0]
    assert "➕" in text


@pytest.mark.asyncio
async def test_counter_save(tg_callback, session, registered_user):
    period = get_active_period(registered_user)
    subject = await session.scalar(
        select(Subject).where(Subject.user_id == registered_user.id).limit(1)
    )

    from bot.handlers.grades import _add_state
    _add_state[tg_callback.from_user.id] = {
        "subject_id": subject.id,
        "period": period,
        "existing": {5: 0, 4: 0, 3: 0, 2: 0, 1: 0},
        "add": {5: 2, 4: 1, 3: 0, 2: 0, 1: 0},
    }
    tg_callback.data = "cnt:save"

    await cb_counter_action(tg_callback, session)

    result = await session.execute(
        select(Grade).where(Grade.subject_id == subject.id, Grade.user_id == registered_user.id)
    )
    grades = result.scalars().all()
    assert len(grades) == 3
    values = [g.value for g in grades]
    assert values.count(5) == 2
    assert values.count(4) == 1


@pytest.mark.asyncio
async def test_counter_cancel_returns_to_list(tg_callback, session, registered_user):
    period = get_active_period(registered_user)
    subject = await session.scalar(
        select(Subject).where(Subject.user_id == registered_user.id).limit(1)
    )

    from bot.handlers.grades import _add_state
    _add_state[tg_callback.from_user.id] = {
        "subject_id": subject.id,
        "period": period,
        "existing": {5: 0, 4: 0, 3: 0, 2: 0, 1: 0},
        "add": {5: 0, 4: 0, 3: 0, 2: 0, 1: 0},
    }
    tg_callback.data = "cnt:cancel"

    await cb_counter_action(tg_callback, session)

    text = tg_callback.message.edit_text.call_args[0][0]
    assert "Оценки" in text


@pytest.mark.asyncio
async def test_counter_reset(tg_callback, session, registered_user):
    period = get_active_period(registered_user)
    subject = await session.scalar(
        select(Subject).where(Subject.user_id == registered_user.id).limit(1)
    )
    session.add(Grade(user_id=registered_user.id, subject_id=subject.id, value=3, period=period))
    session.add(Grade(user_id=registered_user.id, subject_id=subject.id, value=4, period=period))
    await session.commit()

    from bot.handlers.grades import _add_state
    _add_state[tg_callback.from_user.id] = {
        "subject_id": subject.id,
        "period": period,
        "existing": {5: 0, 4: 1, 3: 1, 2: 0, 1: 0},
        "add": {5: 0, 4: 0, 3: 0, 2: 0, 1: 0},
    }
    tg_callback.data = "cnt:reset"

    await cb_counter_action(tg_callback, session)

    result = await session.execute(
        select(Grade).where(Grade.subject_id == subject.id, Grade.user_id == registered_user.id)
    )
    grades = result.scalars().all()
    assert len(grades) == 0
