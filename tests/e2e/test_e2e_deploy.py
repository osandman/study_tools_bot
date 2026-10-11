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

