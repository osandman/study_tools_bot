"""Оценки: счётчик в /grades, сохранение, отмена сохранения, общий средний."""

import re

import pytest

from harness import open_counter, press_grade, put_grades


@pytest.fixture
async def anya(e2e):
    user = e2e.user("Аня")
    await user.send("/start")
    return user


def overall_line(text: str) -> str:
    return next(line for line in text.splitlines() if "Общий:" in line)


async def test_add_grades_with_live_forecast(anya):
    """Открыла Алгебру, нажала +5 +5 +4: прогноз считается на лету, после сохранения — список."""
    counter = await open_counter(anya, "Алгебра")
    assert "Средний балл: —" in counter.text

    await press_grade(anya, 5, on=counter)
    await press_grade(anya, 5, on=counter)
    live = await press_grade(anya, 4, on=counter)
    assert "Средний балл: 4.67" in live.text
    assert "(изменения: +3)" in live.text
    assert "До «5»: уже хватает" in live.text

    saved = await anya.click("✅ Сохранить", on=counter)

    assert saved.answer["text"] == "✅ +3"
    assert "Алгебра — 4.67 (3)" in saved.text
    assert "Общий: 4.67" in saved.text
    assert "Алгебра — 4.67 (3)" in (await anya.send("/grades")).text


async def test_remove_grade_with_minus(anya):
    """Ошибочно поставленную двойку убирают кнопкой «−» под 2️⃣."""
    await put_grades(anya, "Физика", 5, 2)
    counter = await open_counter(anya, "Физика")

    await press_grade(anya, 2, "−", on=counter)
    saved = await anya.click("✅ Сохранить", on=counter)

    assert saved.answer["text"] == "✅ −1"
    assert "Физика — 5.00 (1)" in saved.text


async def test_minus_on_grade_with_zero_count_is_harmless(anya):
    """«−» под оценкой, которой нет: ничего не меняется, но кнопка отвечает и бот не падает."""
    counter = await open_counter(anya, "Алгебра")

    await press_grade(anya, 5, "−", on=counter)

    assert "Средний балл: —" in counter.text


async def test_reset_and_cancel_discard_changes(anya):
    """🗑 Сбросить возвращает счётчик в исходное, ❌ Отмена уходит в список без сохранения."""
    counter = await open_counter(anya, "Алгебра")
    await press_grade(anya, 3, on=counter)

    reset = await anya.click("🗑 Сбросить", on=counter)
    assert "Средний балл: —" in reset.text
    assert "🗑 Сбросить" not in counter.button_texts

    await press_grade(anya, 3, on=counter)
    cancelled = await anya.click("❌ Отмена", on=counter)

    assert "Алгебра —\n" in cancelled.text + "\n"
    assert "Общий" not in cancelled.text


async def test_save_without_changes_does_nothing(anya):
    """«💾 Сохранить» без изменений — просто отвечает на нажатие."""
    counter = await open_counter(anya, "Алгебра")

    pressed = await anya.click("💾 Сохранить", on=counter)

    assert not pressed.edited and "Средний балл: —" in counter.text


async def test_undo_last_save_of_added_grades(anya):
    """Сохранила лишнее → «↩️ Отменить последнее сохранение» → оценок снова нет."""
    saved = await put_grades(anya, "Алгебра", 2, 2)
    assert "↩️ Отменить последнее сохранение" in saved.message.button_texts

    undone = await anya.click("↩️ Отменить последнее сохранение")

    assert "Последнее сохранение отменено" in undone.answer["text"]
    assert "Алгебра —\n" in undone.text
    assert "↩️ Отменить последнее сохранение" not in undone.message.button_texts


async def test_undo_last_save_of_removed_grades(anya):
    """Удалила пятёрку по ошибке и отменила это: пятёрка вернулась."""
    await put_grades(anya, "Алгебра", 5, 3)
    counter = await open_counter(anya, "Алгебра")
    await press_grade(anya, 5, "−", on=counter)
    await anya.click("✅ Сохранить", on=counter)

    undone = await anya.click("↩️ Отменить последнее сохранение")

    assert "Алгебра — 4.00 (2)" in undone.text


async def test_old_counter_after_bot_restart(anya, restart_bot):
    """Счётчик открыт, бот перезапустился: кнопка честно говорит, что сессия истекла."""
    counter = await open_counter(anya, "Алгебра")
    restart_bot()

    pressed = await press_grade(anya, 5, on=counter)

    assert "Сессия истекла" in pressed.answer["text"]


async def test_two_open_grade_screens_save_to_the_subject_on_screen(anya):
    """Два сообщения /grades: в одном открыта Алгебра, в другом Физика. Вернулась к первому,
    нажала +5 и «Сохранить» — пятёрка должна попасть в Алгебру, которая на экране."""
    first = (await anya.send("/grades")).message
    second = (await anya.send("/grades")).message
    await anya.click("Алгебра", on=first)
    await anya.click("Физика", on=second)

    await press_grade(anya, 5, on=first)
    assert "Алгебра" in first.text and "Физика" not in first.text, f"экран превратился в: {first.text!r}"
    await anya.click("✅ Сохранить", on=first)

    grades = (await anya.send("/grades")).text
    assert "Алгебра — 5.00 (1)" in grades
    assert "Физика —\n" in grades


async def test_overall_average_color_is_the_same_everywhere(anya):
    """Общий средний 4.00: цвет в /grades и в списке после сохранения должен совпадать."""
    saved = await put_grades(anya, "Алгебра", 4, 4)

    fresh = await anya.send("/grades")

    assert overall_line(fresh.text) == overall_line(saved.text)


async def test_subject_colors_follow_school_rounding(anya):
    """Цвет предмета — по школьному округлению: 4.50 → 5 🟢, 4.25 → 4 🟡, 2.50 → 3 🟠."""
    await put_grades(anya, "Алгебра", 5, 4)
    await put_grades(anya, "Физика", 5, 4, 4, 4)
    await put_grades(anya, "Химия", 3, 2)

    text = (await anya.send("/grades")).text

    assert re.search(r"🟢 Алгебра — 4\.50", text)
    assert re.search(r"🟡 Физика — 4\.25", text)
    assert re.search(r"🟠 Химия — 2\.50", text)
