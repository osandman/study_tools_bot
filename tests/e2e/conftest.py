"""Фикстуры e2e-сценариев. Запуск: ``scripts/e2e.sh`` (поднимает одноразовый Postgres).

Без ``E2E=1`` сценарии не собираются, чтобы обычный ``pytest tests/`` не требовал Postgres.
"""

import os
from datetime import datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

if os.environ.get("E2E") != "1":
    collect_ignore_glob = ["test_*.py"]

import database.models.grade as grade_module  # noqa: E402
from admin.app import app as admin_app  # noqa: E402
from bot.handlers import grades as grades_handler  # noqa: E402
from bot.main import build_bot, build_dispatcher  # noqa: E402
from config import settings  # noqa: E402
from database.base import engine  # noqa: E402
from database.schema import upgrade_to_head  # noqa: E402
from harness import E2E, E2E_TOKEN, TelegramEmulator  # noqa: E402


@pytest.fixture(scope="session")
def dispatcher():
    # Роутеры обработчиков — модульные синглтоны: aiogram не даёт подключить их дважды.
    return build_dispatcher()


@pytest.fixture(scope="session")
def migrated_schema():
    """Схема — как в проде: миграциями Alembic, а не create_all()."""
    upgrade_to_head()


@pytest.fixture(autouse=True)
async def clean_database(migrated_schema):
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE grades, subjects, users RESTART IDENTITY CASCADE"))
    yield
    # У каждого теста свой event loop, а пул asyncpg привязан к loop'у.
    await engine.dispose()


@pytest.fixture(autouse=True)
def school_month(monkeypatch):
    """«Сегодня» для автовыбора периода; по умолчанию середина октября 2026."""

    def set_month(month: int) -> None:
        year = 2026 if month >= 9 else 2027

        class FrozenDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(year, month, 15, 12, 0, tzinfo=tz)

        monkeypatch.setattr(grade_module, "datetime", FrozenDatetime)

    set_month(10)
    return set_month


@pytest.fixture
async def e2e(dispatcher):
    tg = TelegramEmulator()
    bot = build_bot(E2E_TOKEN, session=tg)
    yield E2E(dispatcher, bot, tg)


@pytest.fixture
def restart_bot():
    """Перезапуск процесса бота: всё, что обработчики держат в памяти, пропадает."""

    def restart() -> None:
        grades_handler._add_state.clear()
        grades_handler._last_saved_action.clear()
        grades_handler._pending_renames.clear()

    return restart


@pytest.fixture
async def admin():
    transport = ASGITransport(app=admin_app)
    async with AsyncClient(transport=transport, base_url="http://admin.test") as client:
        response = await client.post(
            "/admin/login",
            data={"username": settings.admin_username, "password": settings.admin_password},
        )
        assert response.status_code == 303, response.text
        yield client

