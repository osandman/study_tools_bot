import math

from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from database.models.subject import Subject
from database.models.grade import Grade, PERIOD_SYSTEMS, get_periods
from bot.utils.users import require_registered_message, require_registered_callback
from bot.utils.periods import get_active_period
from bot.utils.grades import grade_emoji
from bot.utils.subjects import format_subject_name

router = Router()


def _pluralize_ru(count: int, one: str, few: str, many: str) -> str:
    remainder10 = count % 10
    remainder100 = count % 100
    if remainder10 == 1 and remainder100 != 11:
        return one
    if 2 <= remainder10 <= 4 and not 12 <= remainder100 <= 14:
        return few
    return many


def _format_forecast_option(grade_value: int, count: int) -> str:
    words = {
        5: ("пятёрка", "пятёрки", "пятёрок"),
        4: ("четвёрка", "четвёрки", "четвёрок"),
        3: ("тройка", "тройки", "троек"),
    }
    one, few, many = words.get(grade_value, (f"оценка {grade_value}",) * 3)
    return f"{count} {_pluralize_ru(count, one, few, many)}"


def _needed_count(total_sum: int, total: int, target_avg: float, grade_value: int) -> int | None:
    if grade_value <= target_avg:
        return None
    needed = (target_avg * total - total_sum) / (grade_value - target_avg)
    return max(0, math.ceil(needed))


def _build_counter_forecast(counts: dict[int, int]) -> dict[int, list[tuple[int, int]]]:
    total = sum(counts.values())
    if total == 0:
        return {}

    total_sum = sum(value * counts.get(value, 0) for value in range(1, 6))
    avg = total_sum / total
    thresholds = {
        5: (4.5, [5]),
        4: (3.5, [5, 4]),
    }
    results: dict[int, list[tuple[int, int]]] = {}

    for target, (threshold, grades) in thresholds.items():
        if avg >= threshold:
            results[target] = []
            continue

        options = []
        for grade_value in grades:
            needed = _needed_count(total_sum, total, threshold, grade_value)
            if needed is not None:
                options.append((grade_value, needed))
        results[target] = options

    return results


def _format_counter_forecast_line(target_label: str, options: list[tuple[int, int]]) -> str:
    if not options:
        return f"До «{target_label}»: <b>уже хватает</b>"
    return f"До «{target_label}»: <b>{' или '.join(_format_forecast_option(grade, count) for grade, count in options)}</b>"


def _format_counts_header() -> str:
    return " ".join(f"[{val}]" for val in [1, 2, 3, 4, 5])


def _format_counts_values(counts: dict[int, int]) -> str:
    return " ".join(f"{counts[val]:^3}" for val in [1, 2, 3, 4, 5])


def _format_counts_diff_row(add: dict[int, int]) -> str:
    return " ".join(f"{add[val]:+d}".ljust(3) if add.get(val, 0) else " " * 3 for val in [1, 2, 3, 4, 5])


async def _render_grades_list(
    message: types.Message,
    session: AsyncSession,
    user_id: int,
    period_system: str,
    period: str,
    periods: dict,
) -> None:
    """Render the grades summary for the given period."""
    result = await session.execute(
        select(Subject)
        .where(Subject.user_id == user_id)
        .order_by(Subject.name)
    )
    subjects = result.scalars().all()

    if not subjects:
        await message.edit_text("📚 Нет предметов. Добавь через /subjects")
        return

    period_label = periods.get(period, period)
    text = f"📊 <b>Оценки</b>\n📅 {period_label}\n\n"
    kb = InlineKeyboardBuilder()
    has_undo = False
    if _last_saved_action.get(user_id, {}).get("period") == period:
        kb.button(text="↩️ Отменить последнее сохранение", callback_data="undo_last_save")
        has_undo = True

    for subj in subjects:
        avg_result = await session.execute(
            select(func.avg(Grade.value))
            .where(Grade.subject_id == subj.id, Grade.user_id == user_id, Grade.period == period)
        )
        avg = avg_result.scalar()
        count_result = await session.execute(
            select(func.count(Grade.id))
            .where(Grade.subject_id == subj.id, Grade.user_id == user_id, Grade.period == period)
        )
        count = count_result.scalar()

        if avg is not None:
            emoji = grade_emoji(avg)
            text += f"{emoji} {subj.name} — {avg:.2f} ({count})\n"
        else:
            text += f"⚪ {subj.name} —\n"

        kb.button(text=format_subject_name(subj.name), callback_data=f"subject:{subj.id}:{period}")

    # Overall average
    if subjects:
        overall_result = await session.execute(
            select(func.avg(Grade.value))
            .where(Grade.user_id == user_id, Grade.period == period)
        )
        overall_avg = overall_result.scalar()
        if overall_avg is not None:
            overall_emoji = grade_emoji(overall_avg)
            text += f"\n{overall_emoji} <b>Общий: {overall_avg:.2f}</b>\n"

    if has_undo:
        kb.adjust(1, *[2] * ((len(subjects) + 1) // 2))
    else:
        kb.adjust(*[2] * ((len(subjects) + 1) // 2))
    await message.edit_text(text, reply_markup=kb.as_markup())


# ─── /settings — настройки ────────────────────────────────────────────────

@router.message(Command("settings"))
async def cmd_settings(message: types.Message, session: AsyncSession):
    user = await require_registered_message(message, session)
    if user is None:
        return
    system_label = PERIOD_SYSTEMS[user.period_system]["name"]
    periods = get_periods(user.period_system)
    active = get_active_period(user)

    text = (
        f"⚙️ <b>Настройки</b>\n\n"
        f"Система периодов: <b>{system_label}</b>\n"
        f"Активный период: <b>{periods.get(active, active)}</b>"
    )

    kb = InlineKeyboardBuilder()
    for key, cfg in PERIOD_SYSTEMS.items():
        marker = "✅ " if key == user.period_system else ""
        kb.button(text=f"{marker}{cfg['name']}", callback_data=f"set_period:{key}")

    for p_key, p_label in periods.items():
        marker = "✅ " if p_key == active else ""
        kb.button(text=f"{marker}{p_label}", callback_data=f"set_active_period:{p_key}")
    kb.button(text="🔄 Авто", callback_data="set_active_period:auto")
    kb.adjust(2, 3)

    await message.answer(text, reply_markup=kb.as_markup())


@router.callback_query(F.data.startswith("set_period:"))
async def cb_set_period(callback: types.CallbackQuery, session: AsyncSession):
    system = callback.data.split(":")[1]
    if system not in PERIOD_SYSTEMS:
        await callback.answer("Неизвестная система")
        return

    user = await require_registered_callback(callback, session)
    if user is None:
        return
    user.period_system = system
    user.active_period = None  # reset when changing system
    await session.commit()

    system_label = PERIOD_SYSTEMS[system]["name"]
    periods = get_periods(system)
    active = get_active_period(user)

    text = (
        f"⚙️ <b>Настройки</b>\n\n"
        f"Система периодов: <b>{system_label}</b>\n"
        f"Активный период: <b>{periods.get(active, active)}</b>"
    )

    kb = InlineKeyboardBuilder()
    for key, cfg in PERIOD_SYSTEMS.items():
        marker = "✅ " if key == system else ""
        kb.button(text=f"{marker}{cfg['name']}", callback_data=f"set_period:{key}")

    for p_key, p_label in periods.items():
        marker = "✅ " if p_key == active else ""
        kb.button(text=f"{marker}{p_label}", callback_data=f"set_active_period:{p_key}")
    kb.button(text="🔄 Авто", callback_data="set_active_period:auto")
    kb.adjust(2, 3)

    await callback.message.edit_text(text, reply_markup=kb.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("set_active_period:"))
async def cb_set_active_period(callback: types.CallbackQuery, session: AsyncSession):
    value = callback.data.split(":")[1]
    user = await require_registered_callback(callback, session)
    if user is None:
        return

    if value == "auto":
        user.active_period = None
    else:
        periods = get_periods(user.period_system)
        if value not in periods:
            await callback.answer("Неизвестный период")
            return
        user.active_period = value
    await session.commit()

    periods = get_periods(user.period_system)
    active = get_active_period(user)
    system_label = PERIOD_SYSTEMS[user.period_system]["name"]

    text = (
        f"⚙️ <b>Настройки</b>\n\n"
        f"Система периодов: <b>{system_label}</b>\n"
        f"Активный период: <b>{periods.get(active, active)}</b>"
    )

    kb = InlineKeyboardBuilder()
    for key, cfg in PERIOD_SYSTEMS.items():
        marker = "✅ " if key == user.period_system else ""
        kb.button(text=f"{marker}{cfg['name']}", callback_data=f"set_period:{key}")

    for p_key, p_label in periods.items():
        marker = "✅ " if p_key == active else ""
        kb.button(text=f"{marker}{p_label}", callback_data=f"set_active_period:{p_key}")
    kb.button(text="🔄 Авто", callback_data="set_active_period:auto")
    kb.adjust(2, 3)

    await callback.message.edit_text(text, reply_markup=kb.as_markup())
    await callback.answer()


# ─── /grades — показать оценки ────────────────────────────────────────────

@router.message(Command("grades"))
async def cmd_grades(message: types.Message, session: AsyncSession):
    user = await require_registered_message(message, session)
    if user is None:
        return
    period = get_active_period(user)
    periods_labels = get_periods(user.period_system)

    result = await session.execute(
        select(Subject)
        .where(Subject.user_id == user.id)
        .order_by(Subject.name)
    )
    subjects = result.scalars().all()

    if not subjects:
        await message.answer("📚 Нет предметов. Добавь через /subjects")
        return

    period_label = periods_labels.get(period, period)
    text = f"📊 <b>Оценки</b>\n📅 {period_label}\n\n"
    kb = InlineKeyboardBuilder()
    has_undo = False
    if _last_saved_action.get(user.id, {}).get("period") == period:
        kb.button(text="↩️ Отменить последнее сохранение", callback_data="undo_last_save")
        has_undo = True

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
            emoji = grade_emoji(avg)
            text += f"{emoji} {subj.name} — {avg:.2f} ({count})\n"
        else:
            text += f"⚪ {subj.name} —\n"

        kb.button(text=format_subject_name(subj.name), callback_data=f"subject:{subj.id}:{period}")

    # Overall average
    overall_result = await session.execute(
        select(func.avg(Grade.value))
        .where(Grade.user_id == user.id, Grade.period == period)
    )
    overall_avg = overall_result.scalar()
    if overall_avg is not None:
        overall_emoji = "🟢" if overall_avg >= 4.0 else "🟡" if overall_avg >= 3.0 else "🔴"
        text += f"\n{overall_emoji} <b>Общий: {overall_avg:.2f}</b>\n"

    if has_undo:
        kb.adjust(1, *[2] * ((len(subjects) + 1) // 2))
    else:
        kb.adjust(*[2] * ((len(subjects) + 1) // 2))
    await message.answer(text, reply_markup=kb.as_markup())



# ─── Карточка предмета → сразу счетчики ──────────────────────────────────

# In-memory state: {telegram_id: {subject_id, period, counts: {5:0, 4:0, 3:0, 2:0, 1:0}}}
_add_state: dict[int, dict] = {}
_last_saved_action: dict[int, dict] = {}


@router.callback_query(F.data.startswith("subject:"))
async def cb_subject_counter(callback: types.CallbackQuery, session: AsyncSession):
    """Open subject card directly as the counter interface."""
    parts = callback.data.split(":")
    subject_id = int(parts[1])
    period = parts[2] if len(parts) > 2 else None
    user = await require_registered_callback(callback, session)
    if user is None:
        return

    if period is None:
        period = get_active_period(user)

    result = await session.execute(
        select(Subject).where(Subject.id == subject_id, Subject.user_id == user.id)
    )
    subject = result.scalar_one_or_none()
    if not subject:
        await callback.answer("Предмет не найден", )
        return

    existing_result = await session.execute(
        select(Grade.value, func.count(Grade.id))
        .where(Grade.subject_id == subject_id, Grade.user_id == user.id, Grade.period == period)
        .group_by(Grade.value)
    )
    existing = {row[0]: row[1] for row in existing_result.all()}

    _add_state[callback.from_user.id] = {
        "subject_id": subject_id,
        "period": period,
        "existing": {
            5: existing.get(5, 0),
            4: existing.get(4, 0),
            3: existing.get(3, 0),
            2: existing.get(2, 0),
            1: existing.get(1, 0),
        },
        "add": {5: 0, 4: 0, 3: 0, 2: 0, 1: 0},
    }

    await _render_counter(callback.message, callback.from_user.id, subject.name)
    await callback.answer()


async def _render_counter(message: types.Message, telegram_id: int, subject_name: str):
    state = _add_state.get(telegram_id)
    if not state:
        return

    ex = state["existing"]
    ad = state["add"]

    current_counts = {val: ex[val] + ad[val] for val in [1, 2, 3, 4, 5]}
    new_total = sum(ad.values())
    exist_total = sum(ex.values())
    total_grades = exist_total + new_total
    has_changes = any(v != 0 for v in ad.values())

    text = f"<b>{format_subject_name(subject_name)}</b>\n"
    if exist_total > 0:
        text += f"Всего: <b>{total_grades}</b>"
    else:
        text += f"Всего: <b>{new_total}</b>"

    if has_changes:
        parts = []
        added = sum(v for v in ad.values() if v > 0)
        removed = sum(abs(v) for v in ad.values() if v < 0)
        if added:
            parts.append(f"+{added}")
        if removed:
            parts.append(f"−{removed}")
        text += f"  (изменения: {', '.join(parts)})"

    if total_grades > 0:
        current_sum = sum(val * count for val, count in current_counts.items())
        current_avg = current_sum / total_grades
        forecast = _build_counter_forecast(current_counts)

        text += f"\n📊 Средний балл: <b>{current_avg:.2f}</b> {grade_emoji(current_avg)}"
        text += f"\n🎯 {_format_counter_forecast_line('4', forecast.get(4, []))}"
        text += f"\n🏆 {_format_counter_forecast_line('5', forecast.get(5, []))}"
    else:
        text += "\n📊 Средний балл: <b>—</b>"
        text += "\n🎯 До «4»: <b>добавь хотя бы одну оценку</b>"
        text += "\n🏆 До «5»: <b>добавь хотя бы одну оценку</b>"

    text += "\n\n"
    header_line = _format_counts_header()
    counts_line = _format_counts_values(current_counts)
    if has_changes:
        diff_line = _format_counts_diff_row(ad)
        text += f"<code>{header_line}\n{counts_line}\n{diff_line}</code>\n\n"
    else:
        text += f"<code>{header_line}\n{counts_line}</code>\n\n"

    kb = InlineKeyboardBuilder()

    # Header with digit emojis
    for val in [1, 2, 3, 4, 5]:
        digit_emoji = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"][val - 1]
        kb.button(text=digit_emoji, callback_data="cnt:noop")

    # Plus buttons
    for val in [1, 2, 3, 4, 5]:
        kb.button(text="  +  ", callback_data=f"cnt:{val}:+")

    # Minus buttons
    for val in [1, 2, 3, 4, 5]:
        kb.button(text="  −  ", callback_data=f"cnt:{val}:-")

    # Action buttons: secondary on the left, primary on the right
    kb.button(text="❌ Отмена", callback_data="cnt:cancel")
    if has_changes:
        kb.button(text="✅ Сохранить", callback_data="cnt:save")
    else:
        kb.button(text="💾 Сохранить", callback_data="cnt:noop")

    if has_changes:
        kb.button(text="🗑 Сбросить", callback_data="cnt:reset")
    kb.adjust(5, 5, 5, 2, 1)

    await message.edit_text(text, reply_markup=kb.as_markup())


@router.callback_query(F.data.startswith("cnt:"))
async def cb_counter_action(callback: types.CallbackQuery, session: AsyncSession):
    user = await require_registered_callback(callback, session)
    if user is None:
        _add_state.pop(callback.from_user.id, None)
        return

    state = _add_state.get(callback.from_user.id)
    if not state:
        await callback.answer("Сессия истекла, начни заново", )
        return

    action = callback.data.split(":")[1]

    if action == "cancel":
        _add_state.pop(callback.from_user.id, None)
        await callback.answer("Отменено")

        period = state["period"]
        await _render_grades_list(
            callback.message,
            session,
            user.id,
            user.period_system,
            period,
            get_periods(user.period_system),
        )
        return

    if action == "reset":
        state["add"] = {5: 0, 4: 0, 3: 0, 2: 0, 1: 0}

        result = await session.execute(
            select(Subject.name).where(Subject.id == state["subject_id"])
        )
        name = result.scalar() or "?"
        await callback.answer("↺ Изменения сброшены")
        await _render_counter(callback.message, callback.from_user.id, name)
        return

    if action == "noop":
        await callback.answer()
        return

    if action == "save":
        subject_id = state["subject_id"]
        period = state["period"]
        add_counts = state["add"]

        grades_to_add = []
        deleted_values = []
        added_grade_ids = []
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
                to_delete = await session.execute(
                    select(Grade)
                    .where(Grade.subject_id == subject_id, Grade.user_id == user.id,
                           Grade.period == period, Grade.value == val)
                    .order_by(Grade.created_at.desc())
                    .limit(abs(count))
                )
                for g in to_delete.scalars().all():
                    deleted_values.append(g.value)
                    await session.delete(g)

        if grades_to_add:
            session.add_all(grades_to_add)
            await session.flush()
            added_grade_ids = [grade.id for grade in grades_to_add if grade.id is not None]
        await session.commit()

        _add_state.pop(callback.from_user.id, None)
        _last_saved_action[user.id] = {
            "subject_id": subject_id,
            "period": period,
            "added_grade_ids": added_grade_ids,
            "deleted_values": deleted_values,
        }

        added = sum(v for v in add_counts.values() if v > 0)
        removed = sum(abs(v) for v in add_counts.values() if v < 0)

        parts = []
        if added:
            parts.append(f"+{added}")
        if removed:
            parts.append(f"−{removed}")
        summary = ", ".join(parts) if parts else "без изменений"

        await callback.answer(f"✅ {summary}", )

        # Return to grades list
        await _render_grades_list(
            callback.message,
            session,
            user.id,
            user.period_system,
            period,
            get_periods(user.period_system),
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
            if ex_val + ad_val > 0:
                state["add"][val] -= 1

    result = await session.execute(
        select(Subject.name).where(Subject.id == state["subject_id"])
    )
    name = result.scalar() or "?"
    await _render_counter(callback.message, callback.from_user.id, name)
    await callback.answer()


@router.callback_query(F.data == "undo_last_save")
async def cb_undo_last_save(callback: types.CallbackQuery, session: AsyncSession):
    user = await require_registered_callback(callback, session)
    if user is None:
        return

    action = _last_saved_action.get(user.id)
    if not action:
        await callback.answer("Нечего отменять")
        return

    subject_id = action["subject_id"]
    period = action["period"]
    added_grade_ids = action.get("added_grade_ids", [])
    deleted_values = action.get("deleted_values", [])

    if deleted_values:
        subject_exists = await session.scalar(
            select(Subject.id).where(Subject.id == subject_id, Subject.user_id == user.id)
        )
        if subject_exists is None:
            _last_saved_action.pop(user.id, None)
            await callback.answer("Предмет уже удалён — отмена недоступна")
            return

    if added_grade_ids:
        added_rows = await session.execute(
            select(Grade).where(Grade.user_id == user.id, Grade.id.in_(added_grade_ids))
        )
        for grade in added_rows.scalars().all():
            await session.delete(grade)

    for value in deleted_values:
        session.add(Grade(
            user_id=user.id,
            subject_id=subject_id,
            value=value,
            period=period,
        ))

    await session.commit()
    _last_saved_action.pop(user.id, None)

    await callback.answer("↩️ Последнее сохранение отменено")
    await _render_grades_list(
        callback.message,
        session,
        user.id,
        user.period_system,
        period,
        get_periods(user.period_system),
    )


# ─── /subjects — управление предметами ────────────────────────────────────

_pending_renames: dict[int, int] = {}


@router.message(Command("subjects"))
async def cmd_subjects(message: types.Message, session: AsyncSession):
    user = await require_registered_message(message, session)
    if user is None:
        return

    result = await session.execute(
        select(Subject).where(Subject.user_id == user.id).order_by(Subject.name)
    )
    subjects = result.scalars().all()

    if not subjects:
        await message.answer("📚 Нет предметов. Добавь командой /subjects или просто напиши название.")
        return

    kb = InlineKeyboardBuilder()
    for subj in subjects:
        kb.button(text=format_subject_name(subj.name), callback_data=f"subj:{subj.id}")
    kb.button(text="➕ Добавить", callback_data="add_subject")
    kb.adjust(2)

    await message.answer("📚 <b>Твои предметы</b>", reply_markup=kb.as_markup())


@router.callback_query(F.data.startswith("subj:"))
async def cb_subject_card(callback: types.CallbackQuery, session: AsyncSession):
    subject_id = int(callback.data.split(":")[1])
    user = await require_registered_callback(callback, session)
    if user is None:
        return

    result = await session.execute(
        select(Subject).where(Subject.id == subject_id, Subject.user_id == user.id)
    )
    subject = result.scalar_one_or_none()
    if not subject:
        await callback.answer("Предмет не найден", )
        return

    count_result = await session.execute(
        select(func.count(Grade.id)).where(Grade.subject_id == subject_id, Grade.user_id == user.id)
    )
    count = count_result.scalar()

    text = f"<b>{format_subject_name(subject.name)}</b>\nОценок: {count}"

    kb = InlineKeyboardBuilder()
    kb.button(text="✏️ Изменить", callback_data=f"edit_subject:{subject_id}")
    kb.button(text="🗑 Удалить", callback_data=f"del_subject:{subject_id}")
    kb.button(text="⬅️ Назад", callback_data="back_to_subjects")
    kb.adjust(2, 1)

    await callback.message.edit_text(text, reply_markup=kb.as_markup())
    await callback.answer()


@router.callback_query(F.data == "back_to_subjects")
async def cb_back_to_subjects(callback: types.CallbackQuery, session: AsyncSession):
    user = await require_registered_callback(callback, session)
    if user is None:
        return

    result = await session.execute(
        select(Subject).where(Subject.user_id == user.id).order_by(Subject.name)
    )
    subjects = result.scalars().all()

    kb = InlineKeyboardBuilder()
    for subj in subjects:
        kb.button(text=format_subject_name(subj.name), callback_data=f"subj:{subj.id}")
    kb.button(text="➕ Добавить", callback_data="add_subject")
    kb.adjust(2)

    await callback.message.edit_text("📚 <b>Твои предметы</b>", reply_markup=kb.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("edit_subject:"))
async def cb_edit_subject_prompt(callback: types.CallbackQuery, session: AsyncSession):
    subject_id = int(callback.data.split(":")[1])
    user = await require_registered_callback(callback, session)
    if user is None:
        return

    result = await session.execute(
        select(Subject).where(Subject.id == subject_id, Subject.user_id == user.id)
    )
    subject = result.scalar_one_or_none()
    if not subject:
        await callback.answer("Предмет не найден", )
        return

    _pending_renames[callback.from_user.id] = subject_id

    kb = InlineKeyboardBuilder()
    kb.button(
        text="📋 Скопировать текущее имя",
        copy_text=types.CopyTextButton(text=subject.name),
    )
    kb.button(text="❌ Отмена", callback_data="cancel_subject_edit")
    kb.adjust(1, 1)

    await callback.message.edit_text(
        f"Текущее название: <b>{format_subject_name(subject.name)}</b>\n"
        "Нажми «Скопировать текущее имя», вставь и поправь только нужные буквы, затем отправь новое название сообщением:",
        reply_markup=kb.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data == "cancel_subject_edit")
async def cb_cancel_subject_edit(callback: types.CallbackQuery, session: AsyncSession):
    pending = _pending_renames.pop(callback.from_user.id, None)
    user = await require_registered_callback(callback, session)
    if user is None:
        return

    if pending and pending != -1:
        result = await session.execute(
            select(Subject).where(Subject.id == pending, Subject.user_id == user.id)
        )
        subject = result.scalar_one_or_none()
        if subject:
            count_result = await session.execute(
                select(func.count(Grade.id)).where(Grade.subject_id == pending, Grade.user_id == user.id)
            )
            count = count_result.scalar()

            text = f"<b>{format_subject_name(subject.name)}</b>\nОценок: {count}"
            kb = InlineKeyboardBuilder()
            kb.button(text="✏️ Изменить", callback_data=f"edit_subject:{pending}")
            kb.button(text="🗑 Удалить", callback_data=f"del_subject:{pending}")
            kb.button(text="⬅️ Назад", callback_data="back_to_subjects")
            kb.adjust(2, 1)

            await callback.message.edit_text(text, reply_markup=kb.as_markup())
            await callback.answer("Изменение отменено")
            return

    await cb_back_to_subjects(callback, session)


@router.callback_query(F.data.startswith("del_subject:"))
async def cb_delete_subject(callback: types.CallbackQuery, session: AsyncSession):
    subject_id = int(callback.data.split(":")[1])
    user = await require_registered_callback(callback, session)
    if user is None:
        return

    result = await session.execute(
        select(Subject).where(Subject.id == subject_id, Subject.user_id == user.id)
    )
    subject = result.scalar_one_or_none()
    if not subject:
        await callback.answer("Предмет не найден", )
        return

    name = subject.name
    await session.delete(subject)
    await session.commit()

    await callback.answer(f"🗑 Удалён: {name}", )

    await cb_back_to_subjects(
        types.CallbackQuery(
            id=callback.id, from_user=callback.from_user,
            chat_instance=callback.chat_instance, message=callback.message,
            data="back_to_subjects",
        ),
        session,
    )


@router.callback_query(F.data == "add_subject")
async def cb_add_subject_prompt(callback: types.CallbackQuery, session: AsyncSession):
    user = await require_registered_callback(callback, session)
    if user is None:
        return

    _pending_renames[callback.from_user.id] = -1
    await callback.message.edit_text("📝 Напиши название нового предмета:")
    await callback.answer()


@router.message(F.text & ~F.text.startswith("/"))
async def handle_subject_text(message: types.Message, session: AsyncSession):
    pending = _pending_renames.get(message.from_user.id)
    if pending is None:
        return

    text = message.text.strip()
    if len(text) > 100 or len(text) < 2:
        await message.answer("❌ Название должно быть от 2 до 100 символов.")
        return

    user = await require_registered_message(message, session)
    if user is None:
        return

    if pending == -1:
        result = await session.execute(
            select(Subject).where(Subject.user_id == user.id, Subject.name.ilike(text))
        )
        if result.scalar_one_or_none():
            await message.answer(f"❌ Предмет «{text}» уже существует.")
            return

        subject = Subject(user_id=user.id, name=text, is_default=False)
        session.add(subject)
        await session.commit()
        _pending_renames.pop(message.from_user.id, None)
        await message.answer(f"✅ Предмет «{text}» добавлен!\n\nСписок: /subjects")
    else:
        result = await session.execute(
            select(Subject).where(Subject.id == pending, Subject.user_id == user.id)
        )
        subject = result.scalar_one_or_none()
        if not subject:
            _pending_renames.pop(message.from_user.id, None)
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
        _pending_renames.pop(message.from_user.id, None)
        await message.answer(f"✅ «{old_name}» → «{text}»\n\nСписок: /subjects")
