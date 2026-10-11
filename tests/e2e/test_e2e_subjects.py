"""Предметы: добавить, переименовать, удалить — и как это переживают /grades и /summary."""

import pytest

from dbtools import db_add_subject, db_subject_names
from harness import put_grades


@pytest.fixture
async def anya(e2e):
    user = e2e.user("Аня")
    await user.send("/start")
    return user


async def open_subject_card(user, name):
    await user.send("/subjects")
    return (await user.click(name)).message


async def test_add_subject_with_button(anya):
    """➕ Добавить → название → предмет есть в списке с подходящей иконкой."""
    await anya.send("/subjects")
    prompt = await anya.click("➕ Добавить")
    assert "Напиши название" in prompt.text

    added = await anya.send("Музыка")

    assert "Предмет «Музыка» добавлен" in added.text
    assert "🎵 Музыка" in (await anya.send("/subjects")).message.button_texts


async def test_duplicate_in_other_case_is_rejected(anya):
    """«алгебра» при существующей «Алгебре» — дубликат (Postgres с той же локалью, что в проде)."""
    await anya.send("/subjects")
    await anya.click("➕ Добавить")

    reply = await anya.send("алгебра")

    assert "уже существует" in reply.text
    assert (await db_subject_names(anya.id)).count("Алгебра") == 1
    assert "алгебра" not in await db_subject_names(anya.id)


@pytest.mark.parametrize("name", ["Я", "Ж" * 101])
async def test_subject_name_length_is_validated_and_input_continues(anya, name):
    """Слишком короткое или длинное название — ошибка, но бот продолжает ждать название."""
    await anya.send("/subjects")
    await anya.click("➕ Добавить")

    assert "от 2 до 100 символов" in (await anya.send(name)).text
    assert "добавлен" in (await anya.send("Музыка")).text


async def test_rename_keeps_grades(anya):
    """Переименование не теряет оценки: они привязаны к предмету, а не к названию."""
    await put_grades(anya, "Алгебра", 5, 4)
    await open_subject_card(anya, "Алгебра")
    await anya.click("✏️ Изменить")

    renamed = await anya.send("Алгебра и начала анализа")

    assert "«Алгебра» → «Алгебра и начала анализа»" in renamed.text
    assert "Алгебра и начала анализа — 4.50 (2)" in (await anya.send("/grades")).text


async def test_cancel_rename_returns_to_card(anya):
    """✏️ Изменить → ❌ Отмена: снова карточка предмета, название прежнее."""
    await open_subject_card(anya, "Физика")
    await anya.click("✏️ Изменить")

    card = await anya.click("❌ Отмена")

    assert "Физика" in card.text and "Оценок: 0" in card.text
    assert "Не понял сообщение" in (await anya.send("Физика 2")).text


@pytest.mark.parametrize("start_input", ["rename", "add"])
async def test_abandoned_input_does_not_hijack_later_text(anya, start_input):
    """Нажала «Изменить»/«Добавить», передумала и ушла в /grades. Любой текст потом не должен
    молча переименовать предмет или создать новый."""
    if start_input == "rename":
        await open_subject_card(anya, "Алгебра")
        await anya.click("✏️ Изменить")
    else:
        await anya.send("/subjects")
        await anya.click("➕ Добавить")
    await anya.send("/grades")

    reply = await anya.send("спасибо")

    assert "Не понял сообщение" in reply.text, f"бот ответил: {reply.text!r}"
    names = await db_subject_names(anya.id)
    assert "Алгебра" in names and "спасибо" not in names


async def test_delete_subject_removes_it_with_grades(anya):
    """🗑 Удалить: предмет и его оценки пропадают из /grades и /summary."""
    await put_grades(anya, "Химия", 2, 3)
    await open_subject_card(anya, "Химия")

    after = await anya.click("🗑 Удалить")

    assert "Удалён: Химия" in after.answer["text"]
    assert not any(text.endswith("Химия") for text in after.message.button_texts)
    assert "Химия" not in (await anya.send("/grades")).text
    assert "Химия" not in (await anya.send("/summary")).text


async def test_hint_on_empty_subject_list_works(anya):
    """Удалила все предметы. Бот советует «просто пришли название» — совет должен работать."""
    for name in await db_subject_names(anya.id):
        await open_subject_card(anya, name)
        last = await anya.click("🗑 Удалить")
    assert "просто пришли название" in last.text

    reply = await anya.send("Музыка")

    assert "добавлен" in reply.text, f"бот ответил: {reply.text!r}"


async def test_subject_named_with_html_chars_can_be_added(anya):
    """Название с «<», например «Робототехника <Lego>»: бот подтверждает добавление."""
    await anya.send("/subjects")
    await anya.click("➕ Добавить")

    reply = await anya.send("Робототехника <Lego>")

    assert "добавлен" in reply.text


async def test_subject_with_html_chars_does_not_break_grades_and_summary(anya):
    """Такой предмет уже есть в базе. /grades, счётчик и /summary должны продолжать работать."""
    await db_add_subject(anya.id, "Робототехника <Lego>")

    assert "Робототехника <Lego> —" in (await anya.send("/grades")).text
    await put_grades(anya, "Робототехника <Lego>", 5)
    assert "Робототехника <Lego>" in (await anya.send("/summary")).text


@pytest.mark.parametrize("name", ["Би_логия", "%%"])
async def test_name_with_like_wildcards_is_compared_literally(anya, name):
    """«_» и «%» в названии — обычные символы, а не шаблон: не ложный дубликат и не падение."""
    await anya.send("/subjects")
    await anya.click("➕ Добавить")

    reply = await anya.send(name)

    assert "добавлен" in reply.text, f"бот ответил: {reply.text!r}"
