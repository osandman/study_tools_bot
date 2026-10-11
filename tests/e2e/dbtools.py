"""Прямой доступ к базе для e2e: проверки и подготовка данных, которую нельзя сделать через UI."""

from sqlalchemy import select

from database.base import async_session
from database.models import Subject, User


async def db_user(telegram_id: int) -> User | None:
    async with async_session() as session:
        return await session.scalar(select(User).where(User.telegram_id == telegram_id))


async def db_add_subject(telegram_id: int, name: str) -> None:
    async with async_session() as session:
        user = await session.scalar(select(User).where(User.telegram_id == telegram_id))
        session.add(Subject(user_id=user.id, name=name, is_default=False))
        await session.commit()


async def db_subject_names(telegram_id: int) -> list[str]:
    async with async_session() as session:
        rows = await session.scalars(
            select(Subject.name).join(User, Subject.user_id == User.id).where(User.telegram_id == telegram_id)
        )
        return sorted(rows.all())
