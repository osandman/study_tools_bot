"""Handler for /calc — grade calculator with performance forecast."""

import math

from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import User, Subject, Grade
from database.models.grade import get_current_period, get_periods
from bot.utils.users import require_registered_message, require_registered_callback

router = Router()


def _get_active_period(user: User) -> str:
    """Return active period for user, falling back to current month-based period."""
    if user.active_period:
        return user.active_period
    return get_current_period(user.period_system)


def _school_round(value: float) -> int:
    """Round halves up like a standard school gradebook."""
    return math.floor(value + 0.5)


def _format_percent(value: float) -> str:
    rounded = round(value, 1)
    if rounded.is_integer():
        return f"{int(rounded)}%"
    return f"{rounded:.1f}%"


def _format_counts_table(counts: dict[int, int]) -> str:
    headers = "".join(f"{grade:>4}" for grade in range(1, 6))
    values = "".join(f"{counts.get(grade, 0):>4}" for grade in range(1, 6))
    return f"<code>Оценки{headers}\nКол-во{values}</code>"


def _needed_count(total_sum: int, total: int, target_avg: float, grade_value: int) -> int | None:
    if grade_value <= target_avg:
        return None

    needed = (target_avg * total - total_sum) / (grade_value - target_avg)
    return max(0, math.ceil(needed))


def _forecast(counts: dict[int, int], total: int, avg: float) -> dict[int, list[tuple[int, int]]]:
    """Return ways to reach each target grade by adding better marks."""
    if total == 0:
        return {}

    total_sum = sum(v * counts.get(v, 0) for v in range(1, 6))
    thresholds = {
        5: (4.5, [5]),
        4: (3.5, [5, 4]),
        3: (2.5, [5, 4, 3]),
        2: (1.5, [5, 4, 3, 2]),
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


def _format_forecast_lines(forecast: dict[int, list[tuple[int, int]]]) -> list[str]:
    lines = []

    for target in [5, 4, 3, 2]:
        options = forecast.get(target, [])
        if not options:
            continue

        option_text = " или ".join(f"+{count}×{grade}" for grade, count in options)
        lines.append(f"🎯 До {target}: {option_text}")

    return lines


def _build_calc_text(subjects: list, period: str, periods: dict) -> str:
    """Build the calculator message text."""
    period_label = periods.get(period, period)
    text = f"📊 <b>Калькулятор оценок</b>\n📅 {period_label}\n\n"

    # Build per-subject data
    graded = []
    ungraded_names = []

    for subj in subjects:
        counts = {}
        for row in subj._grade_rows:
            counts[row[0]] = row[1]
        total = sum(counts.values())

        if total == 0:
            ungraded_names.append(subj.name)
            continue

        c = {v: counts.get(v, 0) for v in range(1, 6)}
        total_sum = sum(v * c[v] for v in range(1, 6))
        avg = total_sum / total
        rec = _school_round(avg)
        forecast = _forecast(c, total, avg)
        abs_perf = (c[3] + c[4] + c[5]) / total * 100
        qual_perf = (c[4] + c[5]) / total * 100

        graded.append({
            "name": subj.name,
            "c": c,
            "total": total,
            "avg": avg,
            "rec": rec,
            "forecast": forecast,
            "abs_perf": abs_perf,
            "qual_perf": qual_perf,
        })

    # Overall summary
    if graded:
        overall_sum = sum(s["avg"] * s["total"] for s in graded)
        overall_count = sum(s["total"] for s in graded)
        overall_avg = overall_sum / overall_count
        overall_rec = _school_round(overall_avg)
        emoji = "🟢" if overall_rec >= 4 else "🟡" if overall_rec >= 3 else "🔴"
        overall_abs_perf = sum(s["c"][3] + s["c"][4] + s["c"][5] for s in graded) / overall_count * 100
        overall_qual_perf = sum(s["c"][4] + s["c"][5] for s in graded) / overall_count * 100
        text += f"📈 <b>Средний по всем:</b> {emoji} {overall_avg:.2f}\n"
        text += f"⭐ <b>Рекомендуемая:</b> {overall_rec}\n"
        text += (
            f"📚 <b>Успеваемость:</b> абс. {_format_percent(overall_abs_perf)}, "
            f"кач. {_format_percent(overall_qual_perf)}\n"
        )

        # Overall forecast
        overall_c = {}
        for s in graded:
            for v in range(1, 6):
                overall_c[v] = overall_c.get(v, 0) + s["c"][v]
        overall_fc = _forecast(overall_c, overall_count, overall_avg)
        overall_lines = _format_forecast_lines(overall_fc)
        if overall_lines:
            text += "\n".join(overall_lines) + "\n"
        elif overall_rec == 5:
            text += "🎯 Максимальная оценка уже достигнута! 🏆\n"
        text += "\n"

    # Per-subject
    for sd in graded:
        emoji = "🟢" if sd["rec"] >= 4 else "🟡" if sd["rec"] >= 3 else "🔴"
        text += f"📕 <b>{sd['name']}</b>\n"
        text += f"{emoji} Средний: <b>{sd['avg']:.2f}</b> | Рекомендуемая: <b>{sd['rec']}</b>\n"
        text += _format_counts_table(sd["c"]) + "\n"
        text += (
            f"📚 Успеваемость: абс. {_format_percent(sd['abs_perf'])}, "
            f"кач. {_format_percent(sd['qual_perf'])}\n"
        )

        forecast_lines = _format_forecast_lines(sd["forecast"])
        if forecast_lines:
            text += "\n".join(forecast_lines) + "\n"
        elif sd["rec"] == 5:
            text += "✅ Пятёрка уже достигается\n"

        text += "\n"

    if ungraded_names:
        text += f"⬜ Без оценок: {', '.join(ungraded_names)}\n\n"

    return text


@router.message(Command("calc"))
async def cmd_calc(message: types.Message, session: AsyncSession):
    user = await require_registered_message(message, session)
    if not user:
        return

    period = _get_active_period(user)
    periods = get_periods(user.period_system)

    subjects = await session.scalars(
        select(Subject).where(Subject.user_id == user.id).order_by(Subject.sort_order)
    )
    subjects = subjects.all()

    if not subjects:
        await message.answer("Нет предметов. Добавьте через /subjects")
        return

    # Fetch grade data for all subjects in one query
    subj_ids = [s.id for s in subjects]
    grade_rows = await session.execute(
        select(Grade.subject_id, Grade.value, func.count(Grade.id))
        .where(Grade.user_id == user.id, Grade.period == period, Grade.subject_id.in_(subj_ids))
        .group_by(Grade.subject_id, Grade.value)
    )
    grade_map = {}
    for row in grade_rows.all():
        sid, val, cnt = row
        grade_map.setdefault(sid, []).append((val, cnt))

    # Attach grade data to subjects
    for subj in subjects:
        subj._grade_rows = grade_map.get(subj.id, [])

    text = _build_calc_text(subjects, period, periods)

    # Keyboard
    kb = InlineKeyboardBuilder()
    for p_key, p_label in periods.items():
        marker = "• " if p_key == period else ""
        kb.button(text=f"{marker}{p_label}", callback_data=f"calc_period:{p_key}")
    kb.adjust(len(periods))

    await message.answer(text, reply_markup=kb.as_markup())


@router.callback_query(F.data.startswith("calc_period:"))
async def cb_calc_period(callback: types.CallbackQuery, session: AsyncSession):
    period = callback.data.split(":")[1]
    user = await require_registered_callback(callback, session)
    if not user:
        return

    user.active_period = period
    await session.commit()

    periods = get_periods(user.period_system)

    subjects = await session.scalars(
        select(Subject).where(Subject.user_id == user.id).order_by(Subject.sort_order)
    )
    subjects = subjects.all()

    subj_ids = [s.id for s in subjects]
    grade_rows = await session.execute(
        select(Grade.subject_id, Grade.value, func.count(Grade.id))
        .where(Grade.user_id == user.id, Grade.period == period, Grade.subject_id.in_(subj_ids))
        .group_by(Grade.subject_id, Grade.value)
    )
    grade_map = {}
    for row in grade_rows.all():
        sid, val, cnt = row
        grade_map.setdefault(sid, []).append((val, cnt))

    for subj in subjects:
        subj._grade_rows = grade_map.get(subj.id, [])

    text = _build_calc_text(subjects, period, periods)

    kb = InlineKeyboardBuilder()
    for p_key, p_label in periods.items():
        marker = "• " if p_key == period else ""
        kb.button(text=f"{marker}{p_label}", callback_data=f"calc_period:{p_key}")
    kb.adjust(len(periods))

    await callback.message.edit_text(text, reply_markup=kb.as_markup())
    await callback.answer()
