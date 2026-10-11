"""Периоды: триместры/четверти, ручной выбор периода, автоопределение по календарю."""

import pytest

from harness import put_grades


@pytest.fixture
async def anya(e2e):
    user = e2e.user("Аня")
    await user.send("/start")
    return user


async def test_switch_to_quarters_and_pick_period(anya):
    """Перешла на четверти и выбрала 2 четверть: /grades и счётчик работают в ней."""
    await anya.send("/settings")
    switched = await anya.click("Четверти")
    assert "Система периодов: Четверти" in switched.text

    picked = await anya.click("2 четверть")
    assert "Активный период: 2 четверть" in picked.text

    saved = await put_grades(anya, "Алгебра", 5)
    assert "2 четверть" in saved.text and "Алгебра — 5.00 (1)" in saved.text

    await anya.send("/settings")
    await anya.click("1 четверть")
    assert "Алгебра —\n" in (await anya.send("/grades")).text


@pytest.mark.parametrize("button", ["Триместры", "1 триместр", "🔄 Авто"])
async def test_tapping_already_selected_option_is_harmless(anya, button):
    """Повторное нажатие на уже выбранный вариант в /settings не роняет бота и отвечает на нажатие."""
    await anya.send("/settings")

    await anya.click(button)


QUARTERS = {9: 1, 10: 1, 11: 2, 12: 2, 1: 3, 2: 3, 3: 3, 4: 4, 5: 4}
TRIMESTERS = {9: 1, 10: 1, 11: 1, 12: 2, 1: 2, 2: 2, 3: 3, 4: 3, 5: 3}
MONTHS = {1: "январь", 2: "февраль", 3: "март", 4: "апрель", 5: "май", 9: "сентябрь",
          10: "октябрь", 11: "ноябрь", 12: "декабрь"}


@pytest.mark.parametrize(
    ("system", "month", "expected"),
    [("Четверти", m, f"{q} четверть") for m, q in QUARTERS.items()]
    + [("Триместры", m, f"{t} триместр") for m, t in TRIMESTERS.items()],
    ids=lambda value: MONTHS.get(value, value) if isinstance(value, int) else value,
)
async def test_auto_period_follows_school_calendar(e2e, school_month, system, month, expected):
    """Режим «Авто» выбирает период по школьному календарю: 1 четверть — сентябрь–октябрь,
    2 — ноябрь–декабрь, 3 — январь–март, 4 — апрель–май; триместры по три месяца."""
    school_month(month)
    anya = e2e.user("Аня")
    await anya.send("/start")
    await anya.send("/settings")
    if system == "Четверти":
        await anya.click("Четверти")

    assert f"Активный период: {expected}" in anya.last_message.text
