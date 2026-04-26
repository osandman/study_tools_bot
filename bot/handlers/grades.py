from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from database.models.subject import Subject
from database.models.grade import Grade, PERIODS, get_current_period

router = Router()


# ─── /grades — показать оценки ────────────────────────────────────────────

@router.message(Command("grades"))
async def cmd_grades(message: types.Message, session: AsyncSession):
    """Show all subjects with average grades."""
    user_id = await get_user_id(session, message.from_user.id)

    result = await session.execute(
        select(Subject)
        .where(Subject.user_id == user_id)
        .order_by(Subject.sort_order, Subject.name)
    )
    subjects = result.scalars().all()

    if not subjects:
        await message.answer("📚 У тебя пока нет предметов. Добавь через /subjects")
        return

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
    parts = callback.data.split(":")
    subject_id = int(parts[1])
    period = parts[2] if len(parts) > 2 else get_current_period()
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
        .where(Grade.subject_id == subject_id, Grade.user_id == user_id, Grade.period == period)
        .order_by(desc(Grade.date), desc(Grade.created_at))
        .limit(20)
    )
    grades = grades_result.scalars().all()

    avg_result = await session.execute(
        select(func.avg(Grade.value))
        .where(Grade.subject_id == subject_id, Grade.user_id == user_id, Grade.period == period)
    )
    avg = avg_result.scalar()

    period_label = PERIODS.get(period, period)
    text = f"📚 <b>{subject.name}</b> | {period_label}\n"
    if avg is not None:
        emoji = "🟢" if avg >= 4.0 else "🟡" if avg >= 3.0 else "🔴"
        text += f"Средний балл: {emoji} <b>{avg:.2f}</b>\n\n"
    else:
        text += "Оценок пока нет\n\n"

    if grades:
        for g in grades:
            text += f"  <b>{g.value}</b>\n"
    else:
        text += "  Пока пусто\n"

    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Добавить оценку", callback_data=f"add_grade:{subject_id}")
    if grades:
        kb.button(text="🗑 Удалить оценку", callback_data=f"del_grade_list:{subject_id}")

    # Period switcher
    for p_key, p_label in PERIODS.items():
        marker = "• " if p_key == period else ""
        kb.button(text=f"{marker}{p_label}", callback_data=f"subject:{subject_id}:{p_key}")

    kb.button(text="⬅️ Назад", callback_data="back_to_grades")
    kb.adjust(1, 1, 4, 1)

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
        kb.button(text=str(g.value), callback_data=f"del_grade_confirm:{g.id}:{subject_id}")

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


# ─── Добавление оценки — выбор значения ────────────────────────────────────

@router.callback_query(F.data.startswith("add_grade:"))
async def cb_add_grade_value(callback: types.CallbackQuery, session: AsyncSession):
    """Show grade value selection (1-5)."""
    subject_id = int(callback.data.split(":")[1])
    user_id = await get_user_id(session, callback.from_user.id)

    result = await session.execute(
        select(Subject).where(Subject.id == subject_id, Subject.user_id == user_id)
    )
    subject = result.scalar_one_or_none()
    if not subject:
        await callback.answer("Предмет не найден", show_alert=True)
        return

    kb = InlineKeyboardBuilder()
    for val in range(1, 6):
        emoji = ["😞", "😐", "🙂", "😊", "🤩"][val - 1]
        kb.button(text=f"{emoji} {val}", callback_data=f"grade_val:{subject_id}:{val}")
    kb.button(text="❌ Отмена", callback_data=f"subject:{subject_id}")
    kb.adjust(5, 1)

    await callback.message.edit_text(
        f"📝 Оценка по <b>{subject.name}</b>",
        reply_markup=kb.as_markup()
    )
    await callback.answer()


# ─── Добавление оценки — сохранение ────────────────────────────────────────

@router.callback_query(F.data.startswith("grade_val:"))
async def cb_save_grade(callback: types.CallbackQuery, session: AsyncSession):
    """Save the grade."""
    parts = callback.data.split(":")
    subject_id = int(parts[1])
    value = int(parts[2])
    user_id = await get_user_id(session, callback.from_user.id)

    grade = Grade(
        user_id=user_id,
        subject_id=subject_id,
        value=value,
        period=get_current_period(),
        grade_type="other",
    )
    session.add(grade)
    await session.commit()

    result = await session.execute(select(Subject.name).where(Subject.id == subject_id))
    subject_name = result.scalar()

    emoji = ["😞", "😐", "🙂", "😊", "🤩"][value - 1]
    await callback.answer(f"✅ {emoji} {value} по {subject_name}", show_alert=True)

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

_pending_renames: dict[int, int] = {}


@router.message(Command("subjects"))
async def cmd_subjects(message: types.Message, session: AsyncSession):
    """Show subjects as buttons."""
    user_id = await get_user_id(session, message.from_user.id)

    result = await session.execute(
        select(Subject)
        .where(Subject.user_id == user_id)
        .order_by(Subject.sort_order, Subject.name)
    )
    subjects = result.scalars().all()

    if not subjects:
        await message.answer("📚 Нет предметов. Добавь командой /subjects или просто напиши название.")
        return

    kb = InlineKeyboardBuilder()
    for subj in subjects:
        kb.button(text=subj.name, callback_data=f"subj:{subj.id}")
    kb.button(text="➕ Добавить", callback_data="add_subject")
    kb.adjust(2)

    await message.answer("📚 <b>Твои предметы</b>", reply_markup=kb.as_markup())


# ─── Карточка предмета ────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("subj:"))
async def cb_subject_card(callback: types.CallbackQuery, session: AsyncSession):
    """Show subject card with edit/delete options."""
    subject_id = int(callback.data.split(":")[1])
    user_id = await get_user_id(session, callback.from_user.id)

    result = await session.execute(
        select(Subject).where(Subject.id == subject_id, Subject.user_id == user_id)
    )
    subject = result.scalar_one_or_none()
    if not subject:
        await callback.answer("Предмет не найден", show_alert=True)
        return

    count_result = await session.execute(
        select(func.count(Grade.id))
        .where(Grade.subject_id == subject_id, Grade.user_id == user_id)
    )
    count = count_result.scalar()

    text = f"📚 <b>{subject.name}</b>\nОценок: {count}"

    kb = InlineKeyboardBuilder()
    kb.button(text="✏️ Изменить", callback_data=f"edit_subject:{subject_id}")
    kb.button(text="🗑 Удалить", callback_data=f"del_subject:{subject_id}")
    kb.button(text="⬅️ Назад", callback_data="back_to_subjects")
    kb.adjust(2, 1)

    await callback.message.edit_text(text, reply_markup=kb.as_markup())
    await callback.answer()


# ─── Назад к списку предметов ────────────────────────────────────────────

@router.callback_query(F.data == "back_to_subjects")
async def cb_back_to_subjects(callback: types.CallbackQuery, session: AsyncSession):
    """Go back to subjects list."""
    user_id = await get_user_id(session, callback.from_user.id)

    result = await session.execute(
        select(Subject)
        .where(Subject.user_id == user_id)
        .order_by(Subject.sort_order, Subject.name)
    )
    subjects = result.scalars().all()

    kb = InlineKeyboardBuilder()
    for subj in subjects:
        kb.button(text=subj.name, callback_data=f"subj:{subj.id}")
    kb.button(text="➕ Добавить", callback_data="add_subject")
    kb.adjust(2)

    await callback.message.edit_text("📚 <b>Твои предметы</b>", reply_markup=kb.as_markup())
    await callback.answer()


# ─── Переименование предмета ─────────────────────────────────────────────

@router.callback_query(F.data.startswith("edit_subject:"))
async def cb_edit_subject_prompt(callback: types.CallbackQuery, session: AsyncSession):
    """Prompt user to type a new name for the subject."""
    subject_id = int(callback.data.split(":")[1])
    user_id = await get_user_id(session, callback.from_user.id)

    result = await session.execute(
        select(Subject).where(Subject.id == subject_id, Subject.user_id == user_id)
    )
    subject = result.scalar_one_or_none()
    if not subject:
        await callback.answer("Предмет не найден", show_alert=True)
        return

    _pending_renames[callback.from_user.id] = subject_id

    await callback.message.edit_text(
        f"✏️ Текущее название: <b>{subject.name}</b>\n"
        "Отправь новое название одним сообщением:"
    )
    await callback.answer()


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
        await callback.answer("Предмет не найден", show_alert=True)
        return

    name = subject.name
    await session.delete(subject)
    await session.commit()

    await callback.answer(f"🗑 Удалён: {name}", show_alert=True)

    await cb_back_to_subjects(
        types.CallbackQuery(
            id=callback.id,
            from_user=callback.from_user,
            chat_instance=callback.chat_instance,
            message=callback.message,
            data="back_to_subjects",
        ),
        session,
    )


# ─── Добавление предмета (кнопка) ────────────────────────────────────────

@router.callback_query(F.data == "add_subject")
async def cb_add_subject_prompt(callback: types.CallbackQuery):
    """Prompt user to type a new subject name."""
    _pending_renames[callback.from_user.id] = -1  # -1 = adding new
    await callback.message.edit_text("📝 Напиши название нового предмета:")
    await callback.answer()


# ─── Обработка текста: переименование или добавление предмета ─────────────

@router.message(F.text & ~F.text.startswith("/"))
async def handle_subject_text(message: types.Message, session: AsyncSession):
    """Handle rename or new subject input."""
    pending = _pending_renames.pop(message.from_user.id, None)
    if pending is None:
        return

    text = message.text.strip()
    if len(text) > 100 or len(text) < 2:
        await message.answer("❌ Название должно быть от 2 до 100 символов.")
        return

    user_id = await get_user_id(session, message.from_user.id)

    if pending == -1:
        result = await session.execute(
            select(Subject).where(Subject.user_id == user_id, Subject.name.ilike(text))
        )
        if result.scalar_one_or_none():
            await message.answer(f"❌ Предмет «{text}» уже существует.")
            return

        max_order_result = await session.execute(
            select(func.max(Subject.sort_order)).where(Subject.user_id == user_id)
        )
        max_order = max_order_result.scalar() or 0

        subject = Subject(user_id=user_id, name=text, is_default=False, sort_order=max_order + 1)
        session.add(subject)
        await session.commit()
        await message.answer(f"✅ Предмет «{text}» добавлен!\n\nСписок: /subjects")
    else:
        result = await session.execute(
            select(Subject).where(Subject.id == pending, Subject.user_id == user_id)
        )
        subject = result.scalar_one_or_none()
        if not subject:
            await message.answer("❌ Предмет не найден.")
            return

        dup_result = await session.execute(
            select(Subject).where(
                Subject.user_id == user_id,
                Subject.name.ilike(text),
                Subject.id != pending,
            )
        )
        if dup_result.scalar_one_or_none():
            await message.answer(f"❌ Предмет «{text}» уже существует.")
            return

        old_name = subject.name
        subject.name = text
        await session.commit()
        await message.answer(f"✅ «{old_name}» → «{text}»\n\nСписок: /subjects")


# ─── /calc — калькулятор оценок ───────────────────────────────────────────

@router.message(Command("calc"))
async def cmd_calc(message: types.Message, session: AsyncSession):
    """Grade calculator with forecasts and period stats."""
    user_id = await get_user_id(session, message.from_user.id)
    period = get_current_period()

    # Get all subjects
    subj_result = await session.execute(
        select(Subject)
        .where(Subject.user_id == user_id)
        .order_by(Subject.sort_order, Subject.name)
    )
    subjects = subj_result.scalars().all()

    if not subjects:
        await message.answer("📊 Нет предметов. Добавь через /subjects")
        return

    period_label = PERIODS.get(period, period)
    text = f"📊 <b>Калькулятор оценок</b>\n{period_label}\n\n"
    has_grades = False

    for subj in subjects:
        # Grade counts for this period
        counts_result = await session.execute(
            select(Grade.value, func.count(Grade.id))
            .where(Grade.subject_id == subj.id, Grade.user_id == user_id, Grade.period == period)
            .group_by(Grade.value)
        )
        counts = {row[0]: row[1] for row in counts_result.all()}

        total = sum(counts.values())
        if total == 0:
            text += f"⚪ <b>{subj.name}</b> — нет оценок\n\n"
            continue

        has_grades = True
        c5 = counts.get(5, 0)
        c4 = counts.get(4, 0)
        c3 = counts.get(3, 0)
        c2 = counts.get(2, 0)
        c1 = counts.get(1, 0)

        avg = (5*c5 + 4*c4 + 3*c3 + 2*c2 + 1*c1) / total
        recommended = round(avg)

        emoji = "🟢" if avg >= 4.0 else "🟡" if avg >= 3.0 else "🔴"

        text += f"{emoji} <b>{subj.name}</b>\n"
        text += f"  5×{c5}  4×{c4}  3×{c3}  2×{c2}  1×{c1}\n"
        text += f"  Средний: <b>{avg:.2f}</b> → {recommended}\n"

        # Forecast: how many more grades needed to reach next level
        if avg < 4.0:
            # How many 5s to reach 4.0?
            needed = 0
            test_avg = avg
            while test_avg < 4.0 and needed < 50:
                needed += 1
                test_avg = (5*c5 + 4*c4 + 3*c3 + 2*c2 + 1*c1 + 5*needed) / (total + needed)
            if needed < 50:
                text += f"  До 4.0: ещё {needed}×5\n"
        if avg < 5.0:
            needed = 0
            test_avg = avg
            while test_avg < 5.0 and needed < 50:
                needed += 1
                test_avg = (5*c5 + 4*c4 + 3*c3 + 2*c2 + 1*c1 + 5*needed) / (total + needed)
            if needed < 50:
                text += f"  До 5.0: ещё {needed}×5\n"

        text += "\n"

    if not has_grades:
        text += "Оценок пока нет за этот период.\n"

    # Period switcher
    kb = InlineKeyboardBuilder()
    for p_key, p_label in PERIODS.items():
        marker = "• " if p_key == period else ""
        kb.button(text=f"{marker}{p_label}", callback_data=f"calc:{p_key}")
    kb.adjust(4)

    await message.answer(text, reply_markup=kb.as_markup())


@router.callback_query(F.data.startswith("calc:"))
async def cb_calc_period(callback: types.CallbackQuery, session: AsyncSession):
    """Switch calculator period."""
    period = callback.data.split(":")[1]
    user_id = await get_user_id(session, callback.from_user.id)

    subj_result = await session.execute(
        select(Subject)
        .where(Subject.user_id == user_id)
        .order_by(Subject.sort_order, Subject.name)
    )
    subjects = subj_result.scalars().all()

    period_label = PERIODS.get(period, period)
    text = f"📊 <b>Калькулятор оценок</b>\n{period_label}\n\n"
    has_grades = False

    for subj in subjects:
        counts_result = await session.execute(
            select(Grade.value, func.count(Grade.id))
            .where(Grade.subject_id == subj.id, Grade.user_id == user_id, Grade.period == period)
            .group_by(Grade.value)
        )
        counts = {row[0]: row[1] for row in counts_result.all()}

        total = sum(counts.values())
        if total == 0:
            text += f"⚪ <b>{subj.name}</b> — нет оценок\n\n"
            continue

        has_grades = True
        c5 = counts.get(5, 0)
        c4 = counts.get(4, 0)
        c3 = counts.get(3, 0)
        c2 = counts.get(2, 0)
        c1 = counts.get(1, 0)

        avg = (5*c5 + 4*c4 + 3*c3 + 2*c2 + 1*c1) / total
        recommended = round(avg)

        emoji = "🟢" if avg >= 4.0 else "🟡" if avg >= 3.0 else "🔴"

        text += f"{emoji} <b>{subj.name}</b>\n"
        text += f"  5×{c5}  4×{c4}  3×{c3}  2×{c2}  1×{c1}\n"
        text += f"  Средний: <b>{avg:.2f}</b> → {recommended}\n"

        if avg < 4.0:
            needed = 0
            test_avg = avg
            while test_avg < 4.0 and needed < 50:
                needed += 1
                test_avg = (5*c5 + 4*c4 + 3*c3 + 2*c2 + 1*c1 + 5*needed) / (total + needed)
            if needed < 50:
                text += f"  До 4.0: ещё {needed}×5\n"
        if avg < 5.0:
            needed = 0
            test_avg = avg
            while test_avg < 5.0 and needed < 50:
                needed += 1
                test_avg = (5*c5 + 4*c4 + 3*c3 + 2*c2 + 1*c1 + 5*needed) / (total + needed)
            if needed < 50:
                text += f"  До 5.0: ещё {needed}×5\n"

        text += "\n"

    if not has_grades:
        text += "Оценок пока нет за этот период.\n"

    kb = InlineKeyboardBuilder()
    for p_key, p_label in PERIODS.items():
        marker = "• " if p_key == period else ""
        kb.button(text=f"{marker}{p_label}", callback_data=f"calc:{p_key}")
    kb.adjust(4)

    await callback.message.edit_text(text, reply_markup=kb.as_markup())
    await callback.answer()


# ─── Helpers ──────────────────────────────────────────────────────────────

async def get_user_id(session: AsyncSession, telegram_id: int) -> int:
    """Get internal user ID from telegram ID."""
    from database.models.user import User
    result = await session.execute(select(User.id).where(User.telegram_id == telegram_id))
    return result.scalar_one()
