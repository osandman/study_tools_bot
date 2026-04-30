from collections.abc import AsyncGenerator

from fastapi import Request
from fastapi.responses import RedirectResponse

from database.base import async_session


async def get_db_session() -> AsyncGenerator:
    async with async_session() as session:
        yield session


def require_admin(request: Request) -> None:
    if not request.session.get("admin_logged_in"):
        raise PermissionError


def redirect_login() -> RedirectResponse:
    return RedirectResponse(url="/admin/login", status_code=303)
