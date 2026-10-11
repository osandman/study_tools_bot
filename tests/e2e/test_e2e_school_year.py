"""Учебный год: оценки разных лет не смешиваются, /grades работает с текущим годом,
прошлые годы видны только в /summary. Год начинается 1 сентября, лето — конец прошлого года."""

import pytest

from harness import ChatMessage, open_counter, press_grade, put_grades


@pytest.fixture
async def anya(e2e):
    user = e2e.user("Аня")
    await user.send("/start")
    return user


def rewrite_callbacks(message: ChatMessage, rewrite) -> None:
    """Превратить кнопки в такие, какие отправляла версия бота до учебных лет."""
    for button in message.buttons:
        if "callback_data" in button:
            button["callback_data"] = rewrite(button["callback_data"])


async def test_new_school_year_starts_clean(anya, today):
    """В мае поставила оценки. 1 сентября /grades пуст, а прошлый год виден в сводке."""
    today(2026, 5, 20)
    await put_grades(anya, "Алгебра", 5, 4)

    today(2026, 9, 1)
    grades = (await anya.send("/grades")).text
    assert "1 триместр · 2026/27" in grades
    assert "Алгебра —\n" in grades and "Общий" not in grades

    summary = (await anya.send("/summary")).message
    assert "1 триместр · 2026/27" in summary.text
    past = await anya.click("◀ 2025/26", on=summary)
    assert "3 триместр · 2025/26" in past.text and "Средний: 4.50" in past.text

    back = await anya.click("2026/27 ▶", on=summary)
    assert "1 триместр · 2026/27" in back.text


async def test_same_period_of_next_year_does_not_mix(anya, today):
    """Мартовские двойки прошлого года не портят март этого года."""
    today(2026, 3, 10)
    await put_grades(anya, "Алгебра", 2, 2)

    today(2027, 3, 10)
    saved = await put_grades(anya, "Алгебра", 5)

    assert "3 триместр · 2026/27" in saved.text
    assert "Алгебра — 5.00 (1)" in saved.text


async def test_period_pinned_last_school_year_expires(anya, today):
    """Закрепила в мае «2 триместр». В новом учебном году снова автовыбор по дате;
    закрепление этого года держится до его конца."""
    today(2026, 5, 20)
    await anya.send("/settings")
    await anya.click("2 триместр")

    today(2026, 10, 1)
    settings = (await anya.send("/settings")).text
    assert "Учебный год: 2026/27" in settings and "Активный период: 1 триместр" in settings
    assert "1 триместр · 2026/27" in (await anya.send("/grades")).text

    await anya.click("3 триместр", on=(await anya.send("/settings")).message)
    today(2026, 12, 20)
    assert "3 триместр · 2026/27" in (await anya.send("/grades")).text


async def test_counter_saves_into_the_year_on_screen(anya, today):
    """Открыла счётчик 31 августа, сохранила уже 1 сентября: оценка уходит в год, который был на экране."""
    today(2026, 8, 31)
    counter = await open_counter(anya, "Алгебра")
    await press_grade(anya, 5, on=counter)

    today(2026, 9, 1)
    saved = await anya.click("✅ Сохранить", on=counter)

    assert "3 триместр · 2025/26" in saved.text and "Алгебра — 5.00 (1)" in saved.text
    assert "Алгебра —\n" in (await anya.send("/grades")).text


async def test_undo_after_new_school_year_began(anya, today):
    """Сохранила 31 августа, отменила 1 сентября: отменяется то самое сохранение прошлого года."""
    today(2026, 8, 31)
    saved = await put_grades(anya, "Алгебра", 4)

    today(2026, 9, 1)
    undone = await anya.click("↩️ Отменить последнее сохранение", on=saved.message)

    assert "2025/26" in undone.text and "Алгебра —\n" in undone.text
    assert not any("2025/26" in text for text in (await anya.send("/summary")).message.button_texts)


async def test_summary_without_other_years_has_no_year_switch(anya):
    """Пока оценки есть только в текущем году, переключателя лет в сводке нет."""
    await put_grades(anya, "Алгебра", 5)

    buttons = (await anya.send("/summary")).message.button_texts

    assert not any("◀" in text or "▶" in text for text in buttons)


async def test_buttons_from_before_school_years_keep_working(anya):
    """Сообщения, отправленные до учебных лет, несут кнопки без года — они значат текущий год."""
    grades = (await anya.send("/grades")).message
    rewrite_callbacks(grades, lambda data: data.replace(":2026:", ":"))
    await anya.click("Алгебра", on=grades)
    await press_grade(anya, 5, on=grades)
    saved = await anya.click("✅ Сохранить", on=grades)
    assert "1 триместр · 2026/27" in saved.text and "Алгебра — 5.00 (1)" in saved.text

    summary = (await anya.send("/summary")).message
    rewrite_callbacks(summary, lambda data: data.replace("summary_period:2026:", "summary_period:"))
    assert "2 триместр · 2026/27" in (await anya.click("2 триместр", on=summary)).text
    rewrite_callbacks(summary, lambda data: data.replace("summary_period:2026:", "calc_period:"))
    assert "1 триместр · 2026/27" in (await anya.click("1 триместр", on=summary)).text
