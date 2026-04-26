"""Handler for /calc — grade calculator with performance forecast."""

from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import User, Subject, Grade
from database.models.grade import PERIOD_SYSTEMS, get_current_period, get_periods

router = Router()


def _get_active_period(user: User) -> str:
    """Return active period for user, falling back to current month-based period."""
    if user.active_period:
        return user.active_period
    return get_current_period(user.period_system)


def _forecast(counts: dict, total: int, avg: float) -> list[tuple[int, int]]:
    """Calculate how many additional 5s needed to reach each target grade.

    Returns [(target_grade, needed_count), ...] for grades 5, 4, 3, 2.
    If already achieved, needed_count = 0.
    """
    if total == 0:
        return []

    total_sum = sum(v * counts.get(v, 0) for v in range(1, 6))
    results = []

    # Thresholds: average must be >= threshold to round to that grade
    # Russian rounding: 4.5+ → 5, 3.5+ → 4, 2.5+ → 3, 1.5+ → 2
    thresholds = {5: 4.5, 4: 3.5, 3: 2.5, 2: 1.5}

    for target, threshold in thresholds.items():
        if avg >= threshold:
            results.append((target, 0))
        else:
            # Need (total_sum + 5*n) / (total + n) >= threshold
            # n * (5 - threshold) >= threshold * total - total_sum
            needed = (threshold * total - total_sum) / (5.0 - threshold)
            needed_int = int(needed) + (1 if needed > int(needed) else 0)
            results.append((target, max(0, needed_int)))

    return results


def _build_calc_text(user: User, subjects: list, period: str, periods: dict) -> str:
    """Build the calculator message text."""
    period_label = periods.get(period, period)
    text = f"📊 <b>Калькулятор оценок</b>\n📅 {period_label}\n\n"

    # Gather data for all subjects
    subject_data = []
    for subj in subjects:
        counts_result = []  # will be filled by caller
        subject_data.append(subj)

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
        rec = round(avg)
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
        overall_rec = round(overall_avg)
        emoji = "🟢" if overall_rec >= 4 else "🟡" if overall_rec >= 3 else "🔴"
        text += f"📈 <b>Средний по всем:</b> {emoji} {overall_avg:.2f} → {overall_rec}\n"

        # Overall forecast
        overall_c = {}
        for s in graded:
            for v in range(1, 6):
                overall_c[v] = overall_c.get(v, 0) + s["c"][v]
        overall_fc = _forecast(overall_c, overall_count, overall_avg)
        if overall_fc:
            fc_parts = [f"до {g}: +{n}×5" for g, n in overall_fc if n > 0]
            if fc_parts:
                text += f"🎯 <b>До целевой (пятёрками):</b> {', '.join(fc_parts)}\n"
            elif all(n == 0 for _, n in overall_fc):
                text += "🎯 Максимальная оценка уже достигнута! 🏆\n"
        text += "\n"

    # Per-subject
    for sd in graded:
        emoji = "🟢" if sd["rec"] >= 4 else "🟡" if sd["rec"] >= 3 else "🔴"
        text += f"📕 <b>{sd['name']}</b> {emoji} {sd['avg']:.2f} → {sd['rec']}\n"
        text += f"  <code>1️⃣ 2️⃣ 3️⃣ 4️⃣ 5️⃣</code>\n"
        text += f"  <code>{sd['c'][1]}  {sd['c'][2]}  {sd['c'][3]}  {sd['c'][4]}  {sd['c'][5]}</code>\n"

        if sd["forecast"]:
            fc_parts = [f"{g}: +{n}×5" for g, n in sd["forecast"] if n > 0]
            if fc_parts:
                text += f"  🎯 {', '.join(fc_parts)}\n"
            elif all(n == 0 for _, n in sd["forecast"]):
                text += f"  ✅ Пятёрка гарантирована\n"

        text += "\n"

    if ungraded_names:
        text += f"⬜ Без оценок: {', '.join(ungraded_names)}\n\n"

    return text


@router.message(Command("calc"))
async def cmd_calc(message: types.Message, session: AsyncSession):
    user = await session.scalar(select(User).where(User.telegram_id == message.from_user.id))
    if not user:
        await message.answer("Сначала нажмите /start")
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
    from sqlalchemy import tuple_
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

    text = _build_calc_text(user, subjects, period, periods)

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
    user = await session.scalar(select(User).where(User.telegram_id == callback.from_user.id))
    if not user:
        await callback.answer("Пользователь не найден", show_alert=True)
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

    text = _build_calc_text(user, subjects, period, periods)

    kb = InlineKeyboardBuilder()
    for p_key, p_label in periods.items():
        marker = "• " if p_key == period else ""
        kb.button(text=f"{marker}{p_label}", callback_data=f"calc_period:{p_key}")
    kb.adjust(len(periods))

    await callback.message.edit_text(text, reply_markup=kb.as_markup())
    await callback.answer()
