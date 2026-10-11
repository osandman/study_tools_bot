"""/summary: средние, рекомендуемая оценка, прогноз и переключение периодов."""

import pytest

from harness import MAX_TEXT_LENGTH, put_grades


@pytest.fixture
async def anya(e2e):
    user = e2e.user("Аня")
    await user.send("/start")
    return user


async def test_summary_numbers_and_forecast(anya):
    """Алгебра 5,5,4,3 и Физика 3,3,2: средние, рекомендуемые оценки и сколько чего не хватает."""
    await put_grades(anya, "Алгебра", 5, 5, 4, 3)
    await put_grades(anya, "Физика", 3, 3, 2)

    text = (await anya.send("/summary")).text

    assert "Средний по всем: 🟡 3.57" in text
    assert "Рекомендуемая: 4" in text
    assert "До 5: 13 пятёрок" in text  # (25 + 5x) / (7 + x) ≥ 4.5
    algebra, physics = text.split("🧮 Алгебра")[1], text.split("⚛️ Физика")[1]
    assert "Средний: 4.25" in algebra and "До 5: 2 пятёрки" in algebra
    assert "Средний: 2.67" in physics
    assert "До 4: 2 пятёрки или 5 четвёрок" in physics
    assert "До 5: 11 пятёрок" in physics
    assert "Без оценок:" in text and "Химия" in text.split("Без оценок:")[1]


async def test_summary_other_period(anya):
    """Кнопка периода в сводке только показывает статистику: активный период не меняется."""
    await put_grades(anya, "Алгебра", 5)
    await anya.send("/summary")

    other = await anya.click("2 триместр")

    assert "2 триместр" in other.text and "Алгебра" not in other.text.split("Без оценок:")[0]
    assert "Активный период: 1 триместр" in (await anya.send("/settings")).text
    assert "1 триместр" in (await anya.send("/grades")).text


async def test_summary_tap_current_period_is_harmless(anya):
    """Повторное нажатие на текущий период («• 1 триместр») не роняет бота."""
    await anya.send("/summary")

    await anya.click("1 триместр")


async def test_summary_fits_telegram_limit_for_twenty_subjects(anya):
    """Ученик с 20 предметами и оценками везде: сводка влезает в одно сообщение Telegram."""
    for name in ["Технология", "ИЗО", "Музыка", "ОБЖ", "Астрономия", "Черчение", "Немецкий язык"]:
        await anya.send("/subjects")
        await anya.click("➕ Добавить")
        await anya.send(name)
    await anya.send("/grades")
    subjects = [text.split(" ", 1)[1] for text in anya.last_message.button_texts]
    assert len(subjects) == 20
    for name in subjects:
        await put_grades(anya, name, 2, 3, 3, 4)  # 3.00: прогноз и до 4, и до 5 — самый длинный блок

    text = (await anya.send("/summary")).text

    assert len(text) <= MAX_TEXT_LENGTH
    print(f"длина сводки для 20 предметов: {len(text)} из {MAX_TEXT_LENGTH}")
