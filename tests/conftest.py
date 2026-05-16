import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from httpx import AsyncClient, ASGITransport

from admin.deps import get_db_session
from database.base import Base
from database.models import User, Subject, Grade, DEFAULT_SUBJECTS
from admin.app import app as admin_app


@pytest.fixture(scope="session")
def engine():
    return create_async_engine("sqlite+aiosqlite://", echo=False)


@pytest.fixture(scope="session")
def _session_factory(engine):
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture(autouse=True)
async def _init_db(engine):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture(autouse=True)
def _clear_grades_handler_state():
    from bot.handlers import grades as grades_handler

    grades_handler._add_state.clear()
    grades_handler._last_saved_action.clear()
    grades_handler._pending_renames.clear()
    yield
    grades_handler._add_state.clear()
    grades_handler._last_saved_action.clear()
    grades_handler._pending_renames.clear()


@pytest.fixture
async def session(_session_factory):
    async with _session_factory() as sess:
        yield sess


@pytest.fixture
async def registered_user(session):
    user = User(telegram_id=123456, username="testuser", first_name="Test")
    session.add(user)
    await session.flush()
    for i, name in enumerate(DEFAULT_SUBJECTS):
        session.add(Subject(user_id=user.id, name=name, is_default=True))
    await session.commit()
    return user


@pytest.fixture
def telegram_id():
    return 123456


@pytest.fixture
def tg_message(telegram_id):
    msg = AsyncMock()
    msg.from_user.id = telegram_id
    msg.from_user.first_name = "Test"
    msg.from_user.username = "testuser"
    msg.from_user.last_name = None
    msg.from_user.language_code = "ru"
    msg.answer = AsyncMock()
    msg.edit_text = AsyncMock()
    msg.delete = AsyncMock()
    return msg


@pytest.fixture
def tg_callback(telegram_id, tg_message):
    cb = AsyncMock()
    cb.from_user.id = telegram_id
    cb.from_user.first_name = "Test"
    cb.from_user.username = "testuser"
    cb.message = tg_message
    cb.answer = AsyncMock()
    cb.chat_instance = "test-chat"
    cb.id = "test-cb-id"
    return cb


@pytest.fixture
async def admin_client(session):
    async def override_get_db_session():
        yield session

    admin_app.dependency_overrides[get_db_session] = override_get_db_session
    transport = ASGITransport(app=admin_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client
    admin_app.dependency_overrides.clear()
