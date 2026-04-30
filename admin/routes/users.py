from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from admin.auth import check_admin_credentials, login_admin, logout_admin
from admin.deps import get_db_session, require_admin, redirect_login
from database.models.user import User

router = APIRouter()
templates = Jinja2Templates(directory="admin/templates")


@router.get("/admin/login", response_class=HTMLResponse)
async def admin_login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {"error": None})


@router.post("/admin/login", response_class=HTMLResponse)
async def admin_login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    if not check_admin_credentials(username, password):
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "Неверный логин или пароль"},
            status_code=401,
        )

    login_admin(request)
    return RedirectResponse(url="/admin/users", status_code=303)


@router.post("/admin/logout")
async def admin_logout(request: Request):
    logout_admin(request)
    return RedirectResponse(url="/admin/login", status_code=303)


@router.get("/admin/users", response_class=HTMLResponse)
async def admin_users(request: Request, session: AsyncSession = Depends(get_db_session)):
    try:
        require_admin(request)
    except PermissionError:
        return redirect_login()

    result = await session.execute(select(User).order_by(User.created_at.desc()))
    users = result.scalars().all()
    return templates.TemplateResponse(request, "users.html", {"users": users})


@router.post("/admin/users/{user_id}/block")
async def block_user(user_id: int, request: Request, session: AsyncSession = Depends(get_db_session)):
    try:
        require_admin(request)
    except PermissionError:
        return redirect_login()

    user = await session.get(User, user_id)
    if user is not None:
        user.is_blocked = True
        await session.commit()
    return RedirectResponse(url="/admin/users", status_code=303)


@router.post("/admin/users/{user_id}/unblock")
async def unblock_user(user_id: int, request: Request, session: AsyncSession = Depends(get_db_session)):
    try:
        require_admin(request)
    except PermissionError:
        return redirect_login()

    user = await session.get(User, user_id)
    if user is not None:
        user.is_blocked = False
        await session.commit()
    return RedirectResponse(url="/admin/users", status_code=303)
