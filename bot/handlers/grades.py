from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.models.subject import Subject
from database.models.grade import Grade, GRADE_TYPES

router = Router()


# ─── /grades — показать оценки ────────────────────────────────────────────

@router.message(Command("grades"))
async def cmd_grades(message: types.Message, session: AsyncSession):
    """Show all subjects with average grades."""
    result = await session.execute(
        select(Subject)
        .where(Subject.user_id == (await get_user_id(session, message.from_user.id)))
        .order_by(Subject.sort_order, Subject.name)
    )
    subjects = result.scalars().all()

    if not subjects:
        await message.answer("📚 У тебя пока нет предметов. Добавь через /subjects")
        return

    user_id = await get_user_id(session, message.from_user.id)

    text = "📊 <b>Твои оценки</b>\n\n"
    kb = InlineKeyboardBuilder()

    for subj in subjects:
        avg_result = await session.execute(
            select(func.avg(Grade.value))
            .where(Grade.subject_id == subj.id, Grade.user_id == user_id)
        )
        avg = avg_result.scalar()
        count_result = await session.execute(
            select(func.count(Grade.id))
            .where(Grade.subject_id == subj.id, Grade.user_id == user_id)
        )
        count = count_result.scalar()

        if avg is not None:
            emoji = "🟢" if avg >= 4.0 else "🟡" if avg >= 3.0 else "🔴"
            text += f"{emoji} <b>{subj.name}</b> — {avg:.2f} ({count} оц.)\n"
        else:
            text += f"⚪ <b>{subj.name}</b> — нет оценок\n"

        kb.button(text=subj.name, callback_data=f"subject:{subj.id}")

    kb.adjust(2)
    await message.answer(text, reply_markup=kb.as_markup())


# ─── Выбор предмета → показать оценки ─────────────────────────────────────

@router.callback_query(F.data.startswith("subject:"))
async def cb_subject_grades(callback: types.CallbackQuery, session: AsyncSession):
    """Show grades for a specific subject."""
    subject_id = int(callback.data.split(":")[1])
    user_id = await get_user_id(session, callback.from_user.id)

    # Get subject
    result = await session.execute(
        select(Subject).where(Subject.id == subject_id, Subject.user_id == user_id)
    )
    subject = result.scalar_one_or_none()

    if not subject:
        await callback.answer("Предмет не найден", show_alert=True)
        return

    # Get grades
    grades_result = await session.execute(
        select(Grade)
        .where(Grade.subject_id == subject_id, Grade.user_id == user_id)
        .order_by(desc(Grade.date), desc(Grade.created_at))
        .limit(20)
    )
    grades = grades_result.scalars().all()

    # Calculate average
    avg_result = await session.execute(
        select(func.avg(Grade.value))
        .where(Grade.subject_id == subject_id, Grade.user_id == user_id)
    )
    avg = avg_result.scalar()

    text = f"📚 <b>{subject.name}</b>\n"
    if avg is not None:
        emoji = "🟢" if avg >= 4.0 else "🟡" if avg >= 3.0 else "🔴"
        text += f"Средний балл: {emoji} <b>{avg:.2f}</b>\n\n"
    else:
        text += "Оценок пока нет\n\n"

    if grades:
        for g in grades:
            type_label = GRADE_TYPES.get(g.grade_type, g.grade_type)
            desc_text = f" — {g.description}" if g.description else ""
            text += f"  {type_label}: <b>{g.value}</b>{desc_text} ({g.date.strftime('%d.%m')})\n"
    else:
        text += "  Пока пусто\n"

    # Buttons
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Добавить оценку", callback_data=f"add_grade:{subject_id}")
    if grades:
        kb.button(text="🗑 Удалить оценку", callback_data=f"del_grade_list:{subject_id}")
    kb.button(text="⬅️ Назад", callback_data="back_to_grades")
    kb.adjust(1)

    await callback.message.edit_text(text, reply_markup=kb.as_markup())
    await callback.answer()


# ─── Удаление оценки — список ─────────────────────────────────────────────

@router.callback_query(F.data.startswith("del_grade_list:"))
async def cb_del_grade_list(callback: types.CallbackQuery, session: AsyncSession):
    """Show grades with delete buttons."""
    subject_id = int(callback.data.split(":")[1])
    user_id = await get_user_id(session, callback.from_user.id)

    result = await session.execute(
        select(Subject).where(Subject.id == subject_id, Subject.user_id == user_id)
    )
    subject = result.scalar_one_or_none()
    if not subject:
        await callback.answer("Предмет не найден", show_alert=True)
        return

    grades_result = await session.execute(
        select(Grade)
        .where(Grade.subject_id == subject_id, Grade.user_id == user_id)
        .order_by(desc(Grade.date), desc(Grade.created_at))
        .limit(25)
    )
    grades = grades_result.scalars().all()

    if not grades:
        await callback.answer("Нет оценок для удаления", show_alert=True)
        return

    text = f"🗑 <b>Удалить оценку ({subject.name})</b>\nНажми на оценку, чтобы удалить:\n\n"
    kb = InlineKeyboardBuilder()

    for g in grades:
        type_label = GRADE_TYPES.get(g.grade_type, g.grade_type)
        label = f"{g.value} · {type_label} · {g.date.strftime('%d.%m')}"
        kb.button(text=label, callback_data=f"del_grade_confirm:{g.id}:{subject_id}")

    kb.button(text="❌ Отмена", callback_data=f"subject:{subject_id}")
    kb.adjust(1)

    await callback.message.edit_text(text, reply_markup=kb.as_markup())
    await callback.answer()


# ─── Удаление оценки — подтверждение ──────────────────────────────────────

@router.callback_query(F.data.startswith("del_grade_confirm:"))
async def cb_del_grade_confirm(callback: types.CallbackQuery, session: AsyncSession):
    """Confirm and delete a grade."""
    parts = callback.data.split(":")
    grade_id = int(parts[1])
    subject_id = int(parts[2])
    user_id = await get_user_id(session, callback.from_user.id)

    result = await session.execute(
        select(Grade).where(Grade.id == grade_id, Grade.user_id == user_id)
    )
    grade = result.scalar_one_or_none()

    if not grade:
        await callback.answer("Оценка не найдена", show_alert=True)
        return

    value = grade.value
    await session.delete(grade)
    await session.commit()

    await callback.answer(f"🗑 Удалена оценка {value}", show_alert=True)

    # Refresh subject view
    await cb_subject_grades(
        types.CallbackQuery(
            id=callback.id,
            from_user=callback.from_user,
            chat_instance=callback.chat_instance,
            message=callback.message,
            data=f"subject:{subject_id}",
        ),
        session,
    )


# ─── Добавление оценки — выбор типа ────────────────────────────────────────

@router.callback_query(F.data.startswith("add_grade:"))
async def cb_add_grade_type(callback: types.CallbackQuery, session: AsyncSession):
    """Show grade type selection."""
    subject_id = int(callback.data.split(":")[1])
    user_id = await get_user_id(session, callback.from_user.id)

    # Verify subject belongs to user
    result = await session.execute(
        select(Subject).where(Subject.id == subject_id, Subject.user_id == user_id)
    )
    subject = result.scalar_one_or_none()
    if not subject:
        await callback.answer("Предмет не найден", show_alert=True)
        return

    kb = InlineKeyboardBuilder()
    for key, label in GRADE_TYPES.items():
        kb.button(text=label, callback_data=f"grade_type:{subject_id}:{key}")
    kb.button(text="❌ Отмена", callback_data=f"subject:{subject_id}")
    kb.adjust(2)

    await callback.message.edit_text(
        f"📝 Тип оценки по <b>{subject.name}</b>:",
        reply_markup=kb.as_markup()
    )
    await callback.answer()


# ─── Добавление оценки — выбор значения ────────────────────────────────────

@router.callback_query(F.data.startswith("grade_type:"))
async def cb_add_grade_value(callback: types.CallbackQuery, session: AsyncSession):
    """Show grade value selection (1-5)."""
    parts = callback.data.split(":")
    subject_id = int(parts[1])
    grade_type = parts[2]

    type_label = GRADE_TYPES.get(grade_type, grade_type)

    kb = InlineKeyboardBuilder()
    for val in range(1, 6):
        emoji = ["😞", "😐", "🙂", "😊", "🤩"][val - 1]
        kb.button(text=f"{emoji} {val}", callback_data=f"grade_val:{subject_id}:{grade_type}:{val}")
    kb.button(text="❌ Отмена", callback_data=f"subject:{subject_id}")
    kb.adjust(5, 1)

    await callback.message.edit_text(
        f"Оценка ({type_label}):",
        reply_markup=kb.as_markup()
    )
    await callback.answer()


# ─── Добавление оценки — сохранение ────────────────────────────────────────

@router.callback_query(F.data.startswith("grade_val:"))
async def cb_save_grade(callback: types.CallbackQuery, session: AsyncSession):
    """Save the grade."""
    parts = callback.data.split(":")
    subject_id = int(parts[1])
    grade_type = parts[2]
    value = int(parts[3])
    user_id = await get_user_id(session, callback.from_user.id)

    grade = Grade(
        user_id=user_id,
        subject_id=subject_id,
        value=value,
        grade_type=grade_type,
    )
    session.add(grade)
    await session.commit()

    # Get subject name
    result = await session.execute(select(Subject.name).where(Subject.id == subject_id))
    subject_name = result.scalar()

    type_label = GRADE_TYPES.get(grade_type, grade_type)
    emoji = ["😞", "😐", "🙂", "😊", "🤩"][value - 1]

    await callback.answer(f"✅ {emoji} {value} — {type_label} по {subject_name}", show_alert=True)

    # Refresh subject view
    await cb_subject_grades(
        types.CallbackQuery(
            id=callback.id,
            from_user=callback.from_user,
            chat_instance=callback.chat_instance,
            message=callback.message,
            data=f"subject:{subject_id}",
        ),
        session,
    )


# ─── Кнопка «Назад» ──────────────────────────────────────────────────────

@router.callback_query(F.data == "back_to_grades")
async def cb_back_to_grades(callback: types.CallbackQuery, session: AsyncSession):
    """Go back to grades overview."""
    await callback.message.delete()
    await callback.answer()


# ─── /gpa — средний балл ─────────────────────────────────────────────────

@router.message(Command("gpa"))
async def cmd_gpa(message: types.Message, session: AsyncSession):
    """Calculate overall GPA across all subjects."""
    user_id = await get_user_id(session, message.from_user.id)

    result = await session.execute(
        select(
            Subject.name,
            func.avg(Grade.value).label("avg"),
            func.count(Grade.id).label("count"),
        )
        .join(Grade, Grade.subject_id == Subject.id)
        .where(Grade.user_id == user_id)
        .group_by(Subject.id, Subject.name)
        .order_by(Subject.sort_order, Subject.name)
    )
    rows = result.all()

    if not rows:
        await message.answer("📊 У тебя пока нет оценок. Добавь через /grades")
        return

    text = "📊 <b>Средний балл (GPA)</b>\n\n"
    total_sum = 0
    total_count = 0

    for name, avg, count in rows:
        emoji = "🟢" if avg >= 4.0 else "🟡" if avg >= 3.0 else "🔴"
        text += f"{emoji} <b>{name}</b>: {avg:.2f} ({count} оц.)\n"
        total_sum += avg * count
        total_count += count

    overall = total_sum / total_count if total_count > 0 else 0
    overall_emoji = "🟢" if overall >= 4.0 else "🟡" if overall >= 3.0 else "🔴"

    text += f"\n{overall_emoji} <b>Общий средний балл: {overall:.2f}</b>"
    text += f"\nВсего оценок: {total_count}"

    await message.answer(text)


# ─── /subjects — управление предметами ────────────────────────────────────

@router.message(Command("subjects"))
async def cmd_subjects(message: types.Message, session: AsyncSession):
    """Show and manage subjects."""
    user_id = await get_user_id(session, message.from_user.id)

    result = await session.execute(
        select(Subject)
        .where(Subject.user_id == user_id)
        .order_by(Subject.sort_order, Subject.name)
    )
    subjects = result.scalars().all()

    if not subjects:
        await message.answer("📚 Нет предметов. Напиши название, и я добавлю!")
        return

    text = "📚 <b>Твои предметы</b>\n\n"
    kb = InlineKeyboardBuilder()

    for subj in subjects:
        text += f"• {subj.name}\n"
        kb.button(text=f"🗑 {subj.name}", callback_data=f"del_subject:{subj.id}")

    kb.button(text="➕ Добавить предмет", callback_data="add_subject")
    kb.adjust(1)

    await message.answer(text, reply_markup=kb.as_markup())


# ─── Удаление предмета ────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("del_subject:"))
async def cb_delete_subject(callback: types.CallbackQuery, session: AsyncSession):
    """Delete a subject (and its grades)."""
    subject_id = int(callback.data.split(":")[1])
    user_id = await get_user_id(session, callback.from_user.id)

    result = await session.execute(
        select(Subject).where(Subject.id == subject_id, Subject.user_id == user_id)
    )
    subject = result.scalar_one_or_none()

    if not subject:
        await callback.answer("Нельзя удалить этот предмет", show_alert=True)
        return

    name = subject.name
    await session.delete(subject)
    await session.commit()

    await callback.answer(f"🗑 Удалён: {name}", show_alert=True)
    await callback.message.delete()


# ─── Добавление предмета (текст) ──────────────────────────────────────────

@router.callback_query(F.data == "add_subject")
async def cb_add_subject_prompt(callback: types.CallbackQuery):
    """Prompt user to type a new subject name."""
    await callback.message.edit_text(
        "📝 Напиши название нового предмета одним сообщением:"
    )
    await callback.answer()


@router.message(F.text & ~F.text.startswith("/"))
async def handle_new_subject(message: types.Message, session: AsyncSession):
    """Handle new subject name input."""
    # Check if user has subjects (to determine if this might be a subject add)
    user_id = await get_user_id(session, message.from_user.id)

    # Simple heuristic: if message is short and looks like a subject name
    text = message.text.strip()
    if len(text) > 100 or len(text) < 2:
        return  # Not a subject name

    # Check if it looks like a subject name (no commands, not too long)
    # This is a simplified version — in production you'd use FSM states
    result = await session.execute(
        select(Subject).where(Subject.user_id == user_id, Subject.name.ilike(text))
    )
    existing = result.scalar_one_or_none()

    if existing:
        return  # Subject already exists, skip silently

    # Check if this is a duplicate of a default subject
    for default_name in ["Математика", "Русский язык", "Литература", "Физика",
                         "Химия", "Биология", "История", "Обществознание",
                         "География", "Английский язык", "Информатика", "Физкультура"]:
        if text.lower() == default_name.lower():
            return

    # Get max sort order
    max_order_result = await session.execute(
        select(func.max(Subject.sort_order)).where(Subject.user_id == user_id)
    )
    max_order = max_order_result.scalar() or 0

    # Create new subject
    subject = Subject(
        user_id=user_id,
        name=text,
        is_default=False,
        sort_order=max_order + 1,
    )
    session.add(subject)
    await session.commit()

    await message.answer(f"✅ Предмет «{text}» добавлен!\n\nПосмотри все предметы: /subjects")


# ─── Helpers ──────────────────────────────────────────────────────────────

async def get_user_id(session: AsyncSession, telegram_id: int) -> int:
    """Get internal user ID from telegram ID."""
    from database.models.user import User
    result = await session.execute(select(User.id).where(User.telegram_id == telegram_id))
    return result.scalar_one()
