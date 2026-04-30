import pytest

from bot.middlewares.database import DatabaseMiddleware
from config import settings


@pytest.mark.asyncio
async def test_admin_login_page(admin_client):
    response = await admin_client.get("/admin/login")
    assert response.status_code == 200
    assert "Вход в админку" in response.text


@pytest.mark.asyncio
async def test_admin_login_success(admin_client):
    response = await admin_client.post(
        "/admin/login",
        data={"username": settings.admin_username, "password": settings.admin_password},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/users"


@pytest.mark.asyncio
async def test_admin_users_requires_login(admin_client):
    response = await admin_client.get("/admin/users", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"


@pytest.mark.asyncio
async def test_admin_block_and_unblock(admin_client, session, registered_user):
    await admin_client.post(
        "/admin/login",
        data={"username": settings.admin_username, "password": settings.admin_password},
    )

    response = await admin_client.post(f"/admin/users/{registered_user.id}/block", follow_redirects=False)
    assert response.status_code == 303

    await session.refresh(registered_user)
    assert registered_user.is_blocked is True

    response = await admin_client.post(f"/admin/users/{registered_user.id}/unblock", follow_redirects=False)
    assert response.status_code == 303

    await session.refresh(registered_user)
    assert registered_user.is_blocked is False


@pytest.mark.asyncio
async def test_blocked_user_denied_in_middleware(session, tg_message, registered_user):
    registered_user.is_blocked = True
    await session.commit()

    class TestMiddleware(DatabaseMiddleware):
        @staticmethod
        def _extract_telegram_id(event):
            return registered_user.telegram_id

        @staticmethod
        async def _deny_blocked(event):
            await event.answer("Ваш доступ к боту ограничен.")

        async def __call__(self, handler, event, data):
            data["session"] = session
            return await super().__call__(handler, event, data)

    middleware = TestMiddleware(lambda: session)

    async def handler(event, data):
        raise AssertionError("Blocked user should not reach handler")

    await middleware(handler, tg_message, {})
    tg_message.answer.assert_called_once()
    assert "ограничен" in tg_message.answer.call_args[0][0]
