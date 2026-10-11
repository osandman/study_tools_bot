"""Двойные нажатия. aiogram по умолчанию обрабатывает каждый апдейт отдельной задачей
(``handle_as_tasks=True``), поэтому два быстрых нажатия выполняются параллельно —
здесь это воспроизведено с настоящим Postgres."""

import asyncio

import pytest
from sqlalchemy import text

from database.base import engine
from database.models import DEFAULT_SUBJECTS
from dbtools import db_subject_names
from harness import open_counter, press_grade, put_grades


@pytest.fixture(autouse=True)
async def warm_pool():
    """В проде пул соединений уже прогрет. Без этого второй задаче приходится открывать новое
    соединение, первая успевает закончить — и гонка маскируется."""

    async def ping():
        async with engine.connect() as conn:
            await conn.execute(text("SELECT pg_sleep(0.05)"))

    await asyncio.gather(*(ping() for _ in range(3)))


@pytest.fixture
async def anya(e2e):
    user = e2e.user("Аня")
    await user.send("/start")
    return user


async def double_tap(e2e, user, label, *, on):
    first, _ = user.click_update(label, on=on)
    second, _ = user.click_update(label, on=on)
    return await asyncio.gather(e2e.feed(first), e2e.feed(second), return_exceptions=True)


async def test_double_tap_start(e2e):
    """Нетерпеливый двойной /start: один пользователь, один набор предметов, бот не падает."""
    anya = e2e.user("Аня")

    results = await asyncio.gather(
        e2e.feed(anya.message_update("/start")),
        e2e.feed(anya.message_update("/start")),
        return_exceptions=True,
    )

    assert len(await db_subject_names(anya.id)) == len(DEFAULT_SUBJECTS)
    crashes = [r for r in results if isinstance(r, Exception)]
    assert not crashes, f"второй /start уронил обработчик: {type(crashes[0]).__name__}"


async def test_double_tap_save_does_not_duplicate_grades(e2e, anya):
    """Двойной тап по «✅ Сохранить» после +5: в базе одна пятёрка, а не две."""
    counter = await open_counter(anya, "Алгебра")
    await press_grade(anya, 5, on=counter)

    await double_tap(e2e, anya, "✅ Сохранить", on=counter)

    assert "Алгебра — 5.00 (1)" in (await anya.send("/grades")).text


async def test_double_tap_undo_does_not_restore_twice(e2e, anya):
    """Удалила двойку, затем двойной тап по «↩️ Отменить»: двойка вернулась одна."""
    await put_grades(anya, "Алгебра", 5, 2)
    counter = await open_counter(anya, "Алгебра")
    await press_grade(anya, 2, "−", on=counter)
    saved = await anya.click("✅ Сохранить", on=counter)

    await double_tap(e2e, anya, "↩️ Отменить последнее сохранение", on=saved.message)

    assert "Алгебра — 3.50 (2)" in (await anya.send("/grades")).text
