"""Сценарий администратора: развернуть бота с нуля на пустой базе."""

import asyncio
import os
import sys

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from config import settings

BOT_START = "import asyncio; from database.schema import apply_migrations; asyncio.run(apply_migrations())"


def url_for(database: str) -> str:
    return settings.database_url.rsplit("/", 1)[0] + f"/{database}"


@pytest.fixture
async def fresh_database():
    name = "study_tools_fresh"
    admin_engine = create_async_engine(url_for("postgres"), isolation_level="AUTOCOMMIT")
    async with admin_engine.connect() as conn:
        await conn.execute(text(f"DROP DATABASE IF EXISTS {name}"))
        await conn.execute(text(f"CREATE DATABASE {name}"))
    yield name
    async with admin_engine.connect() as conn:
        await conn.execute(text(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)"))
    await admin_engine.dispose()


async def run_python(database: str, *args: str) -> str:
    """Отдельный процесс, как при старте контейнера; возвращает строку с ошибкой, если упал."""
    proc = await asyncio.create_subprocess_exec(
        sys.executable, *args,
        env={**os.environ, "POSTGRES_DB": database},
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
    )
    output, _ = await proc.communicate()
    if proc.returncode == 0:
        return ""
    errors = [line for line in output.decode().splitlines() if "Error" in line and ":" in line]
    return errors[-1] if errors else output.decode()[-500:]


async def bot_start(database: str) -> str:
    """То, что делает со схемой bot.main.on_startup."""
    return await run_python(database, "-c", BOT_START)


async def alembic(database: str, *args: str) -> str:
    return await run_python(database, "-m", "alembic", *args)


async def test_readme_install_order(fresh_database):
    """README: «docker compose up» (бот сам применяет миграции), затем по желанию «alembic upgrade head»."""
    assert not await bot_start(fresh_database)
    assert not await alembic(fresh_database, "upgrade", "head")
    assert not await alembic(fresh_database, "check"), "схема после миграций расходится с моделями"


async def test_migrations_before_first_start(fresh_database):
    """Обычный порядок: сначала миграции на пустую базу, потом старт бота."""
    assert not await alembic(fresh_database, "upgrade", "head")
    assert not await bot_start(fresh_database)
    assert not await alembic(fresh_database, "check"), "схема после миграций расходится с моделями"


async def test_production_legacy_schema_is_cleaned_up(fresh_database):
    """Рабочая база создавалась ранней версией моделей: лишние колонки в grades и период по умолчанию
    'trimester_1', которого бот не знает. Старт бота приводит её к схеме моделей."""
    assert not await alembic(fresh_database, "upgrade", "20260430_000001")
    engine = create_async_engine(url_for(fresh_database))
    async with engine.begin() as conn:
        await conn.execute(text(
            "ALTER TABLE grades ADD COLUMN grade_type varchar(50) DEFAULT 'other' NOT NULL, "
            "ADD COLUMN description text, ALTER COLUMN period SET DEFAULT 'trimester_1'"
        ))
    await engine.dispose()

    assert not await bot_start(fresh_database)

    assert not await alembic(fresh_database, "check"), "схема после миграций расходится с моделями"
    engine = create_async_engine(url_for(fresh_database))
    async with engine.connect() as conn:
        period_default = await conn.scalar(text(
            "SELECT column_default FROM information_schema.columns "
            "WHERE table_name = 'grades' AND column_name = 'period'"
        ))
    await engine.dispose()
    assert period_default is None


async def test_existing_grades_get_school_year_by_their_date(fresh_database):
    """Оценки, поставленные до учебных лет, получают год по своей дате (год начинается 1 сентября),
    а закрепление периода без года перестаёт действовать."""
    assert not await alembic(fresh_database, "upgrade", "20261011_000002")
    engine = create_async_engine(url_for(fresh_database))
    async with engine.begin() as conn:
        await conn.execute(text(
            "INSERT INTO users (id, telegram_id, period_system, active_period, is_active, is_blocked) "
            "VALUES (1, 100, 'trimesters', 't3', true, false)"
        ))
        await conn.execute(text("INSERT INTO subjects (id, user_id, name, is_default, sort_order) VALUES (1, 1, 'Алгебра', true, 0)"))
        await conn.execute(text(
            "INSERT INTO grades (user_id, subject_id, value, period, date) VALUES "
            "(1, 1, 5, 't3', '2026-05-20'), (1, 1, 4, 't3', '2026-08-31'), (1, 1, 3, 't1', '2026-09-01')"
        ))
    await engine.dispose()

    assert not await bot_start(fresh_database)

    engine = create_async_engine(url_for(fresh_database))
    async with engine.connect() as conn:
        years = dict((await conn.execute(text("SELECT date::text, school_year FROM grades"))).all())
        pinned_year = await conn.scalar(text("SELECT active_school_year FROM users"))
    await engine.dispose()
    assert years == {"2026-05-20": 2025, "2026-08-31": 2025, "2026-09-01": 2026}
    assert pinned_year is None
    assert not await alembic(fresh_database, "check"), "схема после миграций расходится с моделями"
