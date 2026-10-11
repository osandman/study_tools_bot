"""Handler for /summary — grade summary with forecast."""

import math

from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from bot.utils.users import require_registered_message, require_registered_callback
from bot.utils.periods import get_active_period
from bot.utils.grades import grade_emoji
from bot.utils.subjects import subject_title
from database.models import Subject, Grade
from database.models.grade import current_school_year, format_school_year, get_periods

router = Router()


def _school_round(value: float) -> int:
    """Round halves up like a standard school gradebook."""
    return math.floor(value + 0.5)


def _format_counts_table(counts: dict[int, int]) -> str:
    headers = "".join(f"{grade:>4}" for grade in range(1, 6))
    values = "".join(f"{counts.get(grade, 0):>4}" for grade in range(1, 6))
    return f"<code>Оценки{headers}\nКол-во{values}</code>"


def _pluralize(count: int, one: str, few: str, many: str) -> str:
    last_two = count % 100
    last_one = count % 10

    if 11 <= last_two <= 14:
        return many
    if last_one == 1:
        return one
    if 2 <= last_one <= 4:
        return few
    return many


def _format_forecast_option(grade_value: int, count: int) -> str:
    words = {
        5: ("пятёрка", "пятёрки", "пятёрок"),
        4: ("четвёрка", "четвёрки", "четвёрок"),
        3: ("тройка", "тройки", "троек"),
    }
    one, few, many = words.get(grade_value, (f"оценка {grade_value}",) * 3)
    return f"{count} {_pluralize(count, one, few, many)}"


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


def _format_forecast_lines(forecast: dict[int, list[tuple[int, int]]], current_recommendation: int) -> list[str]:
    lines = []

    for target in [5, 4, 3]:
        if current_recommendation >= target:
            continue

        options = forecast.get(target, [])
        if not options:
            continue

        option_text = " или ".join(_format_forecast_option(grade, count) for grade, count in options)
        lines.append(f"До {target}: {option_text}")

    return lines


def _build_summary_text(subjects: list, school_year: int, period: str, periods: dict) -> str:
    """Build the summary message text."""
    period_label = periods.get(period, period)
    text = f"📊 <b>Сводка оценок</b>\n📅 {period_label} · {format_school_year(school_year)}\n\n"

    graded = []
    ungraded_names = []

    for subj in subjects:
        counts = {}
        for row in subj._grade_rows:
            counts[row[0]] = row[1]
        total = sum(counts.values())

        if total == 0:
            ungraded_names.append(subject_title(subj.name))
            continue

        normalized_counts = {v: counts.get(v, 0) for v in range(1, 6)}
        total_sum = sum(v * normalized_counts[v] for v in range(1, 6))
        avg = total_sum / total
        rec = _school_round(avg)

        graded.append(
            {
                "name": subject_title(subj.name),
                "counts": normalized_counts,
                "total": total,
                "avg": avg,
                "rec": rec,
                "forecast": _forecast(normalized_counts, total, avg),
            }
        )

    if graded:
        overall_sum = sum(item["avg"] * item["total"] for item in graded)
        overall_count = sum(item["total"] for item in graded)
        overall_avg = overall_sum / overall_count
        overall_rec = _school_round(overall_avg)
        emoji = grade_emoji(overall_rec)

        text += f"📈 <b>Средний по всем:</b> {emoji} {overall_avg:.2f}\n"
        text += f"⭐ <b>Рекомендуемая:</b> {overall_rec}\n"

        overall_counts = {grade: 0 for grade in range(1, 6)}
        for item in graded:
            for grade in range(1, 6):
                overall_counts[grade] += item["counts"][grade]

        overall_lines = _format_forecast_lines(
            _forecast(overall_counts, overall_count, overall_avg),
            overall_rec,
        )
        if overall_lines:
            text += "📌 <b>Прогноз:</b>\n" + "\n".join(overall_lines) + "\n"

        text += "\n"

    for item in graded:
        emoji = grade_emoji(item["rec"])
        text += f"<b>{item['name']}</b>\n"
        text += f"{emoji} Средний: <b>{item['avg']:.2f}</b>\n"
        text += f"⭐ Рекомендуемая: <b>{item['rec']}</b>\n"
        text += _format_counts_table(item["counts"]) + "\n"

        forecast_lines = _format_forecast_lines(item["forecast"], item["rec"])
        if forecast_lines:
            text += "Прогноз:\n" + "\n".join(forecast_lines) + "\n"

        text += "\n"

    if ungraded_names:
        text += f"⬜ Без оценок: {', '.join(ungraded_names)}\n\n"

    return text


async def _summary_years(session: AsyncSession, user_id: int, shown_year: int) -> list[int]:
    """School years the summary can switch between: those with grades, plus the current one."""
    years = await session.scalars(select(Grade.school_year).where(Grade.user_id == user_id).distinct())
    return sorted(set(years.all()) | {current_school_year(), shown_year})


async def _latest_period_with_grades(session: AsyncSession, user, school_year: int) -> str:
    periods = list(get_periods(user.period_system))
    graded = set(
        (
            await session.scalars(
                select(Grade.period)
                .where(Grade.user_id == user.id, Grade.school_year == school_year)
                .distinct()
            )
        ).all()
    )
    return next((key for key in reversed(periods) if key in graded), periods[0])


async def _summary_view(
    session: AsyncSession, user, school_year: int, period: str
) -> tuple[str, types.InlineKeyboardMarkup]:
    periods = get_periods(user.period_system)

    subjects = await session.scalars(
        select(Subject).where(Subject.user_id == user.id).order_by(Subject.name)
    )
    subjects = subjects.all()

    subj_ids = [s.id for s in subjects]
    grade_rows = await session.execute(
        select(Grade.subject_id, Grade.value, func.count(Grade.id))
        .where(
            Grade.user_id == user.id,
            Grade.school_year == school_year,
            Grade.period == period,
            Grade.subject_id.in_(subj_ids),
        )
        .group_by(Grade.subject_id, Grade.value)
    )
    grade_map = {}
    for row in grade_rows.all():
        sid, val, cnt = row
        grade_map.setdefault(sid, []).append((val, cnt))

    for subj in subjects:
        subj._grade_rows = grade_map.get(subj.id, [])

    text = _build_summary_text(subjects, school_year, period, periods)

    kb = InlineKeyboardBuilder()
    for p_key, p_label in periods.items():
        marker = "• " if p_key == period else ""
        kb.button(text=f"{marker}{p_label}", callback_data=f"summary_period:{school_year}:{p_key}")

    # Past school years are only viewed here; /grades always works with the current one.
    years = await _summary_years(session, user.id, school_year)
    position = years.index(school_year)
    year_buttons = 0
    if position > 0:
        previous = years[position - 1]
        kb.button(text=f"◀ {format_school_year(previous)}", callback_data=f"summary_year:{previous}")
        year_buttons += 1
    if position < len(years) - 1:
        following = years[position + 1]
        kb.button(text=f"{format_school_year(following)} ▶", callback_data=f"summary_year:{following}")
        year_buttons += 1
    kb.adjust(len(periods), *([year_buttons] if year_buttons else []))
    return text, kb.as_markup()


@router.message(Command("summary"))
async def cmd_summary(message: types.Message, session: AsyncSession):
    user = await require_registered_message(message, session)
    if not user:
        return

    has_subjects = await session.scalar(select(func.count(Subject.id)).where(Subject.user_id == user.id))
    if not has_subjects:
        await message.answer("Нет предметов. Добавьте через /subjects")
        return

    text, markup = await _summary_view(session, user, current_school_year(), get_active_period(user))
    await message.answer(text, reply_markup=markup)


@router.callback_query(F.data.startswith("summary_period:") | F.data.startswith("calc_period:"))
async def cb_summary_period(callback: types.CallbackQuery, session: AsyncSession):
    """summary_period:{school_year}:{period}. Messages sent before school years existed carry
    summary_period:{period} or calc_period:{period} and mean the current school year."""
    parts = callback.data.split(":")
    user = await require_registered_callback(callback, session)
    if not user:
        return

    if len(parts) == 3:
        school_year, period = int(parts[1]), parts[2]
    else:
        school_year, period = current_school_year(), parts[1]

    # Only a view of another period's statistics: the active period is chosen in /settings.
    if period not in get_periods(user.period_system):
        await callback.answer("Неизвестный период")
        return

    text, markup = await _summary_view(session, user, school_year, period)
    await callback.message.edit_text(text, reply_markup=markup)
    await callback.answer()


@router.callback_query(F.data.startswith("summary_year:"))
async def cb_summary_year(callback: types.CallbackQuery, session: AsyncSession):
    school_year = int(callback.data.split(":")[1])
    user = await require_registered_callback(callback, session)
    if not user:
        return

    if school_year == current_school_year():
        period = get_active_period(user)
    else:
        period = await _latest_period_with_grades(session, user, school_year)

    text, markup = await _summary_view(session, user, school_year, period)
    await callback.message.edit_text(text, reply_markup=markup)
    await callback.answer()
