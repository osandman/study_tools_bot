"""Админка вместе с ботом: блокировка, разблокировка, список пользователей."""

import re

from dbtools import db_user
from harness import open_counter, press_grade


async def admin_row(admin, telegram_id: int) -> list[str]:
    page = (await admin.get("/admin/users")).text
    row = next(r for r in page.split("<tr>") if f"<td>{telegram_id}</td>" in r)
    return [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", cell)).strip() for cell in re.findall(r"<td>(.*?)</td>", row, re.S)]


async def test_blocked_student_loses_access_until_unblocked(e2e, admin):
    """Админ блокирует ученика: команды и даже уже открытые кнопки отвечают «доступ ограничен».
    После разблокировки всё снова работает."""
    anya = e2e.user("Аня")
    await anya.send("/start")
    counter = await open_counter(anya, "Алгебра")
    user_id = (await db_user(anya.id)).id

    await admin.post(f"/admin/users/{user_id}/block")
    assert "Заблокирован" in await admin_row(admin, anya.id)

    assert (await anya.send("/grades")).text == "Ваш доступ к боту ограничен."
    assert (await anya.send("/start")).text == "Ваш доступ к боту ограничен."
    pressed = await press_grade(anya, 5, on=counter)
    assert pressed.answer["text"] == "Ваш доступ к боту ограничен."
    assert "Средний балл: —" in counter.text

    await admin.post(f"/admin/users/{user_id}/unblock")
    assert "Алгебра" in (await anya.send("/grades")).text


async def test_admin_list_shows_students_and_escapes_names(e2e, admin):
    """Имя ученика с HTML не исполняется в админке, а показывается как текст."""
    evil = e2e.user("<img src=x onerror=alert(1)>", username="evil")
    try:
        await evil.send("/start")
    except AssertionError:
        pass  # приветствие с таким именем ломается отдельно — см. test_name_with_angle_brackets_gets_greeting

    page = (await admin.get("/admin/users")).text

    assert "<img src=x" not in page
    assert "&lt;img src=x onerror=alert(1)&gt;" in page


async def test_admin_requires_login(e2e):
    """Без входа список пользователей и блокировка недоступны."""
    from httpx import ASGITransport, AsyncClient

    from admin.app import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://admin.test") as anonymous:
        assert (await anonymous.get("/admin/users")).headers["location"] == "/admin/login"
        assert (await anonymous.post("/admin/users/1/block")).headers["location"] == "/admin/login"
