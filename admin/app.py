from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from admin.routes.users import router as users_router
from config import settings


app = FastAPI(title="Study Tools Admin")
app.add_middleware(SessionMiddleware, secret_key=settings.admin_secret_key)
app.include_router(users_router)
