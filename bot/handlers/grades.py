from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from database.models.user import User
from database.models.subject import Subject
from database.models.grade import Grade, PERIOD_SYSTEMS, get_current_period, get_periods

router = Router()


async def get_user(session: AsyncSession, telegram_id: int) -> User:
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    return result.scalar_one()


# ─── /settings — настройки ────────────────────────────────────────────────

@router.message(Command("settings"))
async def cmd_settings(message: types.Message, session: AsyncSession):
    user = await get_user(session, message.from_user.id)
    system_label = PERIOD_SYSTEMS[user.period_system]["name"]

    kb = InlineKeyboardBuilder()
    for key, cfg in PERIOD_SYSTEMS.items():
        marker = "✅ " if key == user.period_system else ""
        kb.button(text=f"{marker}{cfg['name']}", callback_data=f"set_period:{key}")
    kb.adjust(2)

    await message.answer(
        f"⚙️ <b>Настройки</b>\n\n"
        f"Система периодов: <b>{system_label}</b>",
        reply_markup=kb.as_markup()
    )


@router.callback_query(F.data.startswith("set_period:"))
async def cb_set_period(callback: types.CallbackQuery, session: AsyncSession):
    system = callback.data.split(":")[1]
    if system not in PERIOD_SYSTEMS:
        await callback.answer("Неизвестная система", show_alert=True)
        return

    user = await get_user(session, callback.from_user.id)
    user.period_system = system
    await session.commit()

    system_label = PERIOD_SYSTEMS[system]["name"]
    await callback.answer(f"✅ Выбрано: {system_label}", show_alert=True)

    kb = InlineKeyboardBuilder()
    for key, cfg in PERIOD_SYSTEMS.items():
        marker = "✅ " if key == system else ""
        kb.button(text=f"{marker}{cfg['name']}", callback_data=f"set_period:{key}")
    kb.adjust(2)

    await callback.message.edit_text(
        f"⚙️ <b>Настройки</b>\n\n"
        f"Система периодов: <b>{system_label}</b>",
        reply_markup=kb.as_markup()
    )


# ─── /grades — показать оценки ────────────────────────────────────────────

@router.message(Command("grades"))
async def cmd_grades(message: types.Message, session: AsyncSession):
    user = await get_user(session, message.from_user.id)
    period = get_current_period(user.period_system)
    periods = get_periods(user.period_system)

    result = await session.execute(
        select(Subject)
        .where(Subject.user_id == user.id)
        .order_by(Subject.sort_order, Subject.name)
    )
    subjects = result.scalars().all()

    if not subjects:
        await message.answer("📚 Нет предметов. Добавь через /subjects")
        return

    period_label = periods.get(period, period)
    text = f"📊 <b>Оценки</b>\n📅 {period_label}\n\n"
    kb = InlineKeyboardBuilder()

    for subj in subjects:
        avg_result = await session.execute(
            select(func.avg(Grade.value))
            .where(Grade.subject_id == subj.id, Grade.user_id == user.id, Grade.period == period)
        )
        avg = avg_result.scalar()
        count_result = await session.execute(
            select(func.count(Grade.id))
            .where(Grade.subject_id == subj.id, Grade.user_id == user.id, Grade.period == period)
        )
        count = count_result.scalar()

        if avg is not None:
            emoji = "🟢" if avg >= 4.0 else "🟡" if avg >= 3.0 else "🔴"
            text += f"{emoji} {subj.name} — {avg:.2f} ({count})\n"
        else:
            text += f"⚪ {subj.name} —\n"

        kb.button(text=subj.name, callback_data=f"subject:{subj.id}:{period}")

    for p_key, p_label in periods.items():
        marker = "• " if p_key == period else ""
        kb.button(text=f"{marker}{p_label}", callback_data=f"grades_period:{p_key}")

    kb.adjust(*[2] * ((len(subjects) + 1) // 2), len(periods))
    await message.answer(text, reply_markup=kb.as_markup())


@router.callback_query(F.data.startswith("grades_period:"))
async def cb_grades_period(callback: types.CallbackQuery, session: AsyncSession):
    period = callback.data.split(":")[1]
    user = await get_user(session, callback.from_user.id)
    periods = get_periods(user.period_system)

    result = await session.execute(
        select(Subject).where(Subject.user_id == user.id).order_by(Subject.sort_order, Subject.name)
    )
    subjects = result.scalars().all()

    period_label = periods.get(period, period)
    text = f"📊 <b>Оценки</b>\n📅 {period_label}\n\n"
    kb = InlineKeyboardBuilder()

    for subj in subjects:
        avg_result = await session.execute(
            select(func.avg(Grade.value))
            .where(Grade.subject_id == subj.id, Grade.user_id == user.id, Grade.period == period)
        )
        avg = avg_result.scalar()
        count_result = await session.execute(
            select(func.count(Grade.id))
            .where(Grade.subject_id == subj.id, Grade.user_id == user.id, Grade.period == period)
        )
        count = count_result.scalar()

        if avg is not None:
            emoji = "🟢" if avg >= 4.0 else "🟡" if avg >= 3.0 else "🔴"
            text += f"{emoji} {subj.name} — {avg:.2f} ({count})\n"
        else:
            text += f"⚪ {subj.name} —\n"

        kb.button(text=subj.name, callback_data=f"subject:{subj.id}:{period}")

    for p_key, p_label in periods.items():
        marker = "• " if p_key == period else ""
        kb.button(text=f"{marker}{p_label}", callback_data=f"grades_period:{p_key}")

    kb.adjust(*[2] * ((len(subjects) + 1) // 2), len(periods))
    await callback.message.edit_text(text, reply_markup=kb.as_markup())
    await callback.answer()


# ─── Карточка предмета с оценками ─────────────────────────────────────────

@router.callback_query(F.data.startswith("subject:"))
async def cb_subject_grades(callback: types.CallbackQuery, session: AsyncSession):
    parts = callback.data.split(":")
    subject_id = int(parts[1])
    period = parts[2] if len(parts) > 2 else None
    user = await get_user(session, callback.from_user.id)

    if period is None:
        period = get_current_period(user.period_system)
    periods = get_periods(user.period_system)

    result = await session.execute(
        select(Subject).where(Subject.id == subject_id, Subject.user_id == user.id)
    )
    subject = result.scalar_one_or_none()
    if not subject:
        await callback.answer("Предмет не найден", show_alert=True)
        return

    # Get grade counts for this period
    counts_result = await session.execute(
        select(Grade.value, func.count(Grade.id))
        .where(Grade.subject_id == subject_id, Grade.user_id == user.id, Grade.period == period)
        .group_by(Grade.value)
    )
    counts = {row[0]: row[1] for row in counts_result.all()}
    total = sum(counts.values())

    period_label = periods.get(period, period)
    text = f"📚 <b>{subject.name}</b>\n📅 {period_label}\n"

    if total > 0:
        c5, c4, c3, c2, c1 = counts.get(5, 0), counts.get(4, 0), counts.get(3, 0), counts.get(2, 0), counts.get(1, 0)
        avg = (5*c5 + 4*c4 + 3*c3 + 2*c2 + 1*c1) / total
        emoji = "🟢" if avg >= 4.0 else "🟡" if avg >= 3.0 else "🔴"

        text += f"\n  ⠀5⃣⠀  ⠀4⃣⠀  ⠀3⃣⠀  ⠀2⃣⠀  ⠀1⃣\n"
        text += f"  ⠀{c5}⠀  ⠀{c4}⠀  ⠀{c3}⠀  ⠀{c2}⠀  ⠀{c1}\n"
        text += f"\n  Средний: {emoji} <b>{avg:.2f}</b>\n  Всего: <b>{total}</b>"
    else:
        text += "\nОценок пока нет"

    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Добавить оценки", callback_data=f"add:{subject_id}:{period}")
    if total > 0:
        kb.button(text="🗑 Сбросить за период", callback_data=f"reset_grades:{subject_id}:{period}")
    kb.button(text="⬅️ Назад", callback_data="back_to_grades")
    kb.adjust(1)

    await callback.message.edit_text(text, reply_markup=kb.as_markup())
    await callback.answer()


# ─── Добавление оценок — счётчики ─────────────────────────────────────────

# In-memory state: {telegram_id: {subject_id, period, counts: {5:0, 4:0, 3:0, 2:0, 1:0}}}
_add_state: dict[int, dict] = {}


@router.callback_query(F.data.startswith("add:"))
async def cb_add_start(callback: types.CallbackQuery, session: AsyncSession):
    parts = callback.data.split(":")
    subject_id = int(parts[1])
    period = parts[2]
    user = await get_user(session, callback.from_user.id)

    result = await session.execute(
        select(Subject).where(Subject.id == subject_id, Subject.user_id == user.id)
    )
    subject = result.scalar_one_or_none()
    if not subject:
        await callback.answer("Предмет не найден", show_alert=True)
        return

    # Fetch existing counts
    existing_result = await session.execute(
        select(Grade.value, func.count(Grade.id))
        .where(Grade.subject_id == subject_id, Grade.user_id == user.id, Grade.period == period)
        .group_by(Grade.value)
    )
    existing = {row[0]: row[1] for row in existing_result.all()}

    _add_state[callback.from_user.id] = {
        "subject_id": subject_id,
        "period": period,
        "existing": {5: existing.get(5, 0), 4: existing.get(4, 0), 3: existing.get(3, 0), 2: existing.get(2, 0), 1: existing.get(1, 0)},
        "add": {5: 0, 4: 0, 3: 0, 2: 0, 1: 0},
    }

    await _render_add_grades(callback.message, callback.from_user.id, subject.name)
    await callback.answer()


async def _render_add_grades(message: types.Message, telegram_id: int, subject_name: str):
    state = _add_state.get(telegram_id)
    if not state:
        return

    ex = state["existing"]
    ad = state["add"]
    new_total = sum(ad.values())
    exist_total = sum(ex.values())

    text = f"➕ <b>{subject_name}</b>\n"
    if exist_total > 0:
        text += f"Всего: <b>{exist_total + new_total}</b>\n\n"
    else:
        text += "\n"

    kb = InlineKeyboardBuilder()

    # Header with digit emojis
    for val in [1, 2, 3, 4, 5]:
        digit_emoji = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"][val - 1]
        kb.button(text=digit_emoji, callback_data="cnt:noop")

    # Plus buttons
    for val in [1, 2, 3, 4, 5]:
        kb.button(text="+", callback_data=f"cnt:{val}:+")

    # Counts row
    for val in [1, 2, 3, 4, 5]:
        total_val = ex[val] + ad[val]
        kb.button(text=str(total_val), callback_data="cnt:noop")

    # Minus buttons
    for val in [1, 2, 3, 4, 5]:
        kb.button(text="−", callback_data=f"cnt:{val}:-")

    # Save always visible
    if new_total != 0:
        kb.button(text=f"✅ Сохранить ({'+' if new_total > 0 else ''}{new_total})", callback_data="cnt:save")
    else:
        kb.button(text="💾 Сохранить", callback_data="cnt:noop")
    kb.button(text="❌ Отмена", callback_data="cnt:cancel")
    kb.adjust(5, 5, 5, 5, 2, 1)

    await message.edit_text(text, reply_markup=kb.as_markup())


@router.callback_query(F.data.startswith("cnt:"))
async def cb_count_action(callback: types.CallbackQuery, session: AsyncSession):
    state = _add_state.get(callback.from_user.id)
    if not state:
        await callback.answer("Сессия истекла, начни заново", show_alert=True)
        return

    action = callback.data.split(":")[1]

    if action == "cancel":
        _add_state.pop(callback.from_user.id, None)
        await callback.answer("Отменено")
        # Go back to subject
        result = await session.execute(
            select(Subject.name).where(Subject.id == state["subject_id"])
        )
        name = result.scalar() or "?"
        await callback.message.edit_text(f"📚 <b>{name}</b>\nОтменено.")
        return

    if action == "noop":
        await callback.answer()
        return

    if action == "save":
        subject_id = state["subject_id"]
        period = state["period"]
        add_counts = state["add"]
        user = await get_user(session, callback.from_user.id)

        grades_to_add = []
        deleted = 0
        for val, count in add_counts.items():
            if count > 0:
                for _ in range(count):
                    grades_to_add.append(Grade(
                        user_id=user.id,
                        subject_id=subject_id,
                        value=val,
                        period=period,
                    ))
            elif count < 0:
                # Delete N grades of this value
                to_delete = await session.execute(
                    select(Grade)
                    .where(Grade.subject_id == subject_id, Grade.user_id == user.id,
                           Grade.period == period, Grade.value == val)
                    .order_by(Grade.created_at.desc())
                    .limit(abs(count))
                )
                for g in to_delete.scalars().all():
                    await session.delete(g)
                    deleted += 1

        if grades_to_add:
            session.add_all(grades_to_add)
        await session.commit()

        net = sum(add_counts.values())
        _add_state.pop(callback.from_user.id, None)

        if net > 0:
            await callback.answer(f"✅ Добавлено {net} оценок", show_alert=True)
        elif net < 0:
            await callback.answer(f"🗑 Удалено {abs(net)} оценок", show_alert=True)
        else:
            await callback.answer("Ничего не изменилось", show_alert=True)

        # Show subject card
        result = await session.execute(
            select(Subject).where(Subject.id == subject_id)
        )
        subject = result.scalar_one_or_none()
        if subject:
            await cb_subject_grades(
                types.CallbackQuery(
                    id=callback.id,
                    from_user=callback.from_user,
                    chat_instance=callback.chat_instance,
                    message=callback.message,
                    data=f"subject:{subject_id}:{period}",
                ),
                session,
            )
        return

    # Increment/decrement
    parts = callback.data.split(":")
    val = int(parts[1])
    direction = parts[2]

    if val in state["add"]:
        if direction == "+":
            state["add"][val] += 1
        elif direction == "-":
            ex_val = state["existing"][val]
            ad_val = state["add"][val]
            if ex_val + ad_val > 0:  # can't go below 0 total
                state["add"][val] -= 1

    result = await session.execute(
        select(Subject.name).where(Subject.id == state["subject_id"])
    )
    name = result.scalar() or "?"
    await _render_add_grades(callback.message, callback.from_user.id, name)
    await callback.answer()


# ─── Сброс оценок за период ──────────────────────────────────────────────

@router.callback_query(F.data.startswith("reset_grades:"))
async def cb_reset_grades(callback: types.CallbackQuery, session: AsyncSession):
    parts = callback.data.split(":")
    subject_id = int(parts[1])
    period = parts[2]
    user = await get_user(session, callback.from_user.id)

    result = await session.execute(
        select(Subject).where(Subject.id == subject_id, Subject.user_id == user.id)
    )
    subject = result.scalar_one_or_none()
    if not subject:
        await callback.answer("Предмет не найден", show_alert=True)
        return

    # Delete grades for this period
    from sqlalchemy import delete
    await session.execute(
        delete(Grade).where(
            Grade.subject_id == subject_id,
            Grade.user_id == user.id,
            Grade.period == period,
        )
    )
    await session.commit()

    await callback.answer("🗑 Оценки сброшены", show_alert=True)

    # Refresh
    await cb_subject_grades(
        types.CallbackQuery(
            id=callback.id,
            from_user=callback.from_user,
            chat_instance=callback.chat_instance,
            message=callback.message,
            data=f"subject:{subject_id}:{period}",
        ),
        session,
    )


# ─── Кнопка «Назад» ──────────────────────────────────────────────────────

@router.callback_query(F.data == "back_to_grades")
async def cb_back_to_grades(callback: types.CallbackQuery, session: AsyncSession):
    await callback.message.delete()
    await callback.answer()


# ─── /gpa — средний балл ─────────────────────────────────────────────────

@router.message(Command("gpa"))
async def cmd_gpa(message: types.Message, session: AsyncSession):
    user = await get_user(session, message.from_user.id)
    period = get_current_period(user.period_system)
    periods = get_periods(user.period_system)

    result = await session.execute(
        select(
            Subject.name,
            func.avg(Grade.value).label("avg"),
            func.count(Grade.id).label("count"),
        )
        .join(Grade, Grade.subject_id == Subject.id)
        .where(Grade.user_id == user.id, Grade.period == period)
        .group_by(Subject.id, Subject.name)
        .order_by(Subject.sort_order, Subject.name)
    )
    rows = result.all()

    if not rows:
        await message.answer("📊 Нет оценок за текущий период.")
        return

    period_label = periods.get(period, period)
    text = f"📊 <b>Средний балл</b> | {period_label}\n\n"
    total_sum, total_count = 0, 0

    for name, avg, count in rows:
        emoji = "🟢" if avg >= 4.0 else "🟡" if avg >= 3.0 else "🔴"
        text += f"{emoji} <b>{name}</b>: {avg:.2f} ({count})\n"
        total_sum += avg * count
        total_count += count

    overall = total_sum / total_count if total_count > 0 else 0
    overall_emoji = "🟢" if overall >= 4.0 else "🟡" if overall >= 3.0 else "🔴"
    text += f"\n{overall_emoji} <b>Общий: {overall:.2f}</b>"

    await message.answer(text)


# ─── /calc — калькулятор оценок ───────────────────────────────────────────

@router.message(Command("calc"))
async def cmd_calc(message: types.Message, session: AsyncSession):
    user = await get_user(session, message.from_user.id)
    await _render_calc(message, user, session)


async def _render_calc(message_or_callback_msg, user: User, session: AsyncSession, period: str = None):
    if period is None:
        period = get_current_period(user.period_system)
    periods = get_periods(user.period_system)

    result = await session.execute(
        select(Subject).where(Subject.user_id == user.id).order_by(Subject.sort_order, Subject.name)
    )
    subjects = result.scalars().all()

    period_label = periods.get(period, period)
    text = f"📊 <b>Калькулятор</b> | {period_label}\n\n"
    has_grades = False

    for subj in subjects:
        counts_result = await session.execute(
            select(Grade.value, func.count(Grade.id))
            .where(Grade.subject_id == subj.id, Grade.user_id == user.id, Grade.period == period)
            .group_by(Grade.value)
        )
        counts = {row[0]: row[1] for row in counts_result.all()}
        total = sum(counts.values())

        if total == 0:
            text += f"⚪ <b>{subj.name}</b> — нет оценок\n\n"
            continue

        has_grades = True
        c5, c4, c3, c2, c1 = counts.get(5, 0), counts.get(4, 0), counts.get(3, 0), counts.get(2, 0), counts.get(1, 0)
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
    for p_key, p_label in periods.items():
        marker = "• " if p_key == period else ""
        kb.button(text=f"{marker}{p_label}", callback_data=f"calc:{p_key}")
    kb.adjust(len(periods))

    await message_or_callback_msg.answer(text, reply_markup=kb.as_markup())


@router.callback_query(F.data.startswith("calc:"))
async def cb_calc_period(callback: types.CallbackQuery, session: AsyncSession):
    period = callback.data.split(":")[1]
    user = await get_user(session, callback.from_user.id)
    periods = get_periods(user.period_system)

    result = await session.execute(
        select(Subject).where(Subject.user_id == user.id).order_by(Subject.sort_order, Subject.name)
    )
    subjects = result.scalars().all()

    period_label = periods.get(period, period)
    text = f"📊 <b>Калькулятор</b> | {period_label}\n\n"
    has_grades = False

    for subj in subjects:
        counts_result = await session.execute(
            select(Grade.value, func.count(Grade.id))
            .where(Grade.subject_id == subj.id, Grade.user_id == user.id, Grade.period == period)
            .group_by(Grade.value)
        )
        counts = {row[0]: row[1] for row in counts_result.all()}
        total = sum(counts.values())

        if total == 0:
            text += f"⚪ <b>{subj.name}</b> — нет оценок\n\n"
            continue

        has_grades = True
        c5, c4, c3, c2, c1 = counts.get(5, 0), counts.get(4, 0), counts.get(3, 0), counts.get(2, 0), counts.get(1, 0)
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
    for p_key, p_label in periods.items():
        marker = "• " if p_key == period else ""
        kb.button(text=f"{marker}{p_label}", callback_data=f"calc:{p_key}")
    kb.adjust(len(periods))

    await callback.message.edit_text(text, reply_markup=kb.as_markup())
    await callback.answer()


# ─── /subjects — управление предметами ────────────────────────────────────

_pending_renames: dict[int, int] = {}


@router.message(Command("subjects"))
async def cmd_subjects(message: types.Message, session: AsyncSession):
    user = await get_user(session, message.from_user.id)

    result = await session.execute(
        select(Subject).where(Subject.user_id == user.id).order_by(Subject.sort_order, Subject.name)
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


@router.callback_query(F.data.startswith("subj:"))
async def cb_subject_card(callback: types.CallbackQuery, session: AsyncSession):
    subject_id = int(callback.data.split(":")[1])
    user = await get_user(session, callback.from_user.id)

    result = await session.execute(
        select(Subject).where(Subject.id == subject_id, Subject.user_id == user.id)
    )
    subject = result.scalar_one_or_none()
    if not subject:
        await callback.answer("Предмет не найден", show_alert=True)
        return

    count_result = await session.execute(
        select(func.count(Grade.id)).where(Grade.subject_id == subject_id, Grade.user_id == user.id)
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


@router.callback_query(F.data == "back_to_subjects")
async def cb_back_to_subjects(callback: types.CallbackQuery, session: AsyncSession):
    user = await get_user(session, callback.from_user.id)

    result = await session.execute(
        select(Subject).where(Subject.user_id == user.id).order_by(Subject.sort_order, Subject.name)
    )
    subjects = result.scalars().all()

    kb = InlineKeyboardBuilder()
    for subj in subjects:
        kb.button(text=subj.name, callback_data=f"subj:{subj.id}")
    kb.button(text="➕ Добавить", callback_data="add_subject")
    kb.adjust(2)

    await callback.message.edit_text("📚 <b>Твои предметы</b>", reply_markup=kb.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("edit_subject:"))
async def cb_edit_subject_prompt(callback: types.CallbackQuery, session: AsyncSession):
    subject_id = int(callback.data.split(":")[1])
    user = await get_user(session, callback.from_user.id)

    result = await session.execute(
        select(Subject).where(Subject.id == subject_id, Subject.user_id == user.id)
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


@router.callback_query(F.data.startswith("del_subject:"))
async def cb_delete_subject(callback: types.CallbackQuery, session: AsyncSession):
    subject_id = int(callback.data.split(":")[1])
    user = await get_user(session, callback.from_user.id)

    result = await session.execute(
        select(Subject).where(Subject.id == subject_id, Subject.user_id == user.id)
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
            id=callback.id, from_user=callback.from_user,
            chat_instance=callback.chat_instance, message=callback.message,
            data="back_to_subjects",
        ),
        session,
    )


@router.callback_query(F.data == "add_subject")
async def cb_add_subject_prompt(callback: types.CallbackQuery):
    _pending_renames[callback.from_user.id] = -1
    await callback.message.edit_text("📝 Напиши название нового предмета:")
    await callback.answer()


@router.message(F.text & ~F.text.startswith("/"))
async def handle_subject_text(message: types.Message, session: AsyncSession):
    pending = _pending_renames.pop(message.from_user.id, None)
    if pending is None:
        return

    text = message.text.strip()
    if len(text) > 100 or len(text) < 2:
        await message.answer("❌ Название должно быть от 2 до 100 символов.")
        return

    user = await get_user(session, message.from_user.id)

    if pending == -1:
        result = await session.execute(
            select(Subject).where(Subject.user_id == user.id, Subject.name.ilike(text))
        )
        if result.scalar_one_or_none():
            await message.answer(f"❌ Предмет «{text}» уже существует.")
            return

        max_order_result = await session.execute(
            select(func.max(Subject.sort_order)).where(Subject.user_id == user.id)
        )
        max_order = max_order_result.scalar() or 0

        subject = Subject(user_id=user.id, name=text, is_default=False, sort_order=max_order + 1)
        session.add(subject)
        await session.commit()
        await message.answer(f"✅ Предмет «{text}» добавлен!\n\nСписок: /subjects")
    else:
        result = await session.execute(
            select(Subject).where(Subject.id == pending, Subject.user_id == user.id)
        )
        subject = result.scalar_one_or_none()
        if not subject:
            await message.answer("❌ Предмет не найден.")
            return

        dup_result = await session.execute(
            select(Subject).where(
                Subject.user_id == user.id,
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
