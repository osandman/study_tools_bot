import pytest
from sqlalchemy import select
from unittest.mock import AsyncMock

from database.models import Subject, Grade
from bot.handlers.grades import (
    cmd_grades,
    cmd_subjects,
    cmd_settings,
    cb_set_period,
    cb_set_active_period,
    cb_subject_counter,
    cb_counter_action,
    cb_add_subject_prompt,
    cb_edit_subject_prompt,
    cb_delete_subject,
    handle_subject_text,
)
from bot.utils.periods import get_active_period


@pytest.mark.asyncio
async def test_grades_no_registration(tg_message, session):
    await cmd_grades(tg_message, session)
    text = tg_message.answer.call_args[0][0]
    assert "зарегистрироваться" in text.lower() or "/start" in text.lower()


@pytest.mark.asyncio
async def test_grades_with_subjects(tg_message, session, registered_user):
    period = get_active_period(registered_user)
    subject = await session.scalar(
        select(Subject).where(Subject.user_id == registered_user.id).order_by(Subject.name).limit(1)
    )
    session.add(Grade(user_id=registered_user.id, subject_id=subject.id, value=5, period=period))
    session.add(Grade(user_id=registered_user.id, subject_id=subject.id, value=4, period=period))
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

    markup = tg_message.answer.call_args.kwargs["reply_markup"]
    button_names = [button.text for row in markup.inline_keyboard for button in row if button.callback_data != "add_subject"]
    assert button_names == sorted(button_names)


@pytest.mark.asyncio
async def test_grades_buttons_include_active_period(tg_message, session, registered_user):
    await cmd_grades(tg_message, session)

    active_period = get_active_period(registered_user)
    markup = tg_message.answer.call_args.kwargs["reply_markup"]
    callback_data = [button.callback_data for row in markup.inline_keyboard for button in row]
    subject_buttons = [data for data in callback_data if data.startswith("subject:")]

    assert subject_buttons
    assert all(data.endswith(f":{active_period}") for data in subject_buttons)


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


@pytest.mark.asyncio
async def test_settings_change_period_system(tg_callback, session, registered_user):
    tg_callback.data = "set_period:quarters"

    await cb_set_period(tg_callback, session)

    await session.refresh(registered_user)
    assert registered_user.period_system == "quarters"
    assert registered_user.active_period is None
    tg_callback.message.edit_text.assert_called_once()


@pytest.mark.asyncio
async def test_settings_set_active_period_invalid_value(tg_callback, session, registered_user):
    tg_callback.data = "set_active_period:invalid"

    await cb_set_active_period(tg_callback, session)

    tg_callback.answer.assert_called_once()
    assert "Неизвестный период" in tg_callback.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_settings_set_active_period_auto(tg_callback, session, registered_user):
    registered_user.active_period = "t2"
    await session.commit()

    tg_callback.data = "set_active_period:auto"

    await cb_set_active_period(tg_callback, session)

    await session.refresh(registered_user)
    assert registered_user.active_period is None


@pytest.mark.asyncio
async def test_subject_add_flow_creates_subject(tg_callback, tg_message, session, registered_user):
    from bot.handlers.grades import _pending_renames

    tg_callback.data = "add_subject"
    await cb_add_subject_prompt(tg_callback, session)

    assert _pending_renames[registered_user.telegram_id] == -1

    tg_message.text = "Астрономия"
    await handle_subject_text(tg_message, session)

    result = await session.execute(
        select(Subject).where(Subject.user_id == registered_user.id, Subject.name == "Астрономия")
    )
    subject = result.scalar_one_or_none()
    assert subject is not None
    assert registered_user.telegram_id not in _pending_renames


@pytest.mark.asyncio
async def test_subject_rename_flow_updates_name(tg_callback, tg_message, session, registered_user):
    subject = await session.scalar(
        select(Subject).where(Subject.user_id == registered_user.id).order_by(Subject.name).limit(1)
    )

    tg_callback.data = f"edit_subject:{subject.id}"
    await cb_edit_subject_prompt(tg_callback, session)

    tg_message.text = "Новый предмет"
    await handle_subject_text(tg_message, session)

    await session.refresh(subject)
    assert subject.name == "Новый предмет"


@pytest.mark.asyncio
async def test_subject_delete_flow_removes_subject(tg_callback, session, registered_user, monkeypatch):
    class DummyCallbackQuery:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)
            self.answer = AsyncMock()

    monkeypatch.setattr("bot.handlers.grades.types.CallbackQuery", DummyCallbackQuery)

    subject = await session.scalar(
        select(Subject).where(Subject.user_id == registered_user.id).order_by(Subject.name).limit(1)
    )

    tg_callback.data = f"del_subject:{subject.id}"
    await cb_delete_subject(tg_callback, session)

    result = await session.execute(select(Subject).where(Subject.id == subject.id))
    assert result.scalar_one_or_none() is None
