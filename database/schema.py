"""Database schema: Alembic migrations are the single source of truth."""

import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def alembic_config() -> Config:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    # Otherwise alembic/env.py reconfigures stdlib logging and silences aiogram's loggers.
    config.attributes["configure_logger"] = False
    return config


def upgrade_to_head() -> None:
    command.upgrade(alembic_config(), "head")


async def apply_migrations() -> None:
    # alembic/env.py runs its own event loop via asyncio.run(), so it needs a thread of its own.
    await asyncio.to_thread(upgrade_to_head)
