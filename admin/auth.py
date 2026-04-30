from fastapi import Request

from config import settings


def check_admin_credentials(username: str, password: str) -> bool:
    return username == settings.admin_username and password == settings.admin_password


def login_admin(request: Request) -> None:
    request.session["admin_logged_in"] = True


def logout_admin(request: Request) -> None:
    request.session.clear()
