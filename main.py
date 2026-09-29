from pathlib import Path
from typing import Annotated
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Depends, HTTPException, status, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.exception_handlers import http_exception_handler
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler

from src.core import config
from src.core.db import create_db_and_tables, engine, SessionDep
from src.core.security import SESSION_COOKIE_NAME, generate_csrf_token
from src.core.middleware import SecurityHeadersMiddleware, CSRFProtectionMiddleware
from src.models import menu_model, user_model, chat_history_model, user_session_model, session_model
from src.models.user_model import User
from src.services.user_service import seed_default_admin
from src.services.menu_service import build_menu_split_view_context
from src.controllers.auth_controller import router as auth_router, get_current_admin, limiter
from src.controllers.menus_controller import router as menus_router
from src.controllers.users_controller import router as users_router
from src.controllers.webhook_controller import setup_webhook_handlers
from pywa.client import WhatsApp
from dotenv import load_dotenv
import os
import logging

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(levelname)s:     %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Runs when FastAPI starts up
    create_db_and_tables()
    with Session(engine) as session:
        seed_default_admin(session)
    yield
    # Code here would run on server shutdown (if needed)


app = FastAPI(lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # pyright: ignore[reportArgumentType]


@app.exception_handler(HTTPException)
async def unauthenticated_exception_handler(request: Request, exc: HTTPException):
    """
    Trata erros de autenticação (HTTP 401) redirecionando navegadores e requisições HTMX para /login.
    """
    if exc.status_code == status.HTTP_401_UNAUTHORIZED:
        if request.headers.get("HX-Request") == "true":
            return Response(status_code=status.HTTP_200_OK, headers={"HX-Redirect": "/login"})
        accept = request.headers.get("Accept", "")
        if "text/html" in accept or "application/json" not in accept:
            return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    return await http_exception_handler(request, exc)


app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(CSRFProtectionMiddleware)

BASE_DIR = Path(__file__).resolve().parent

app.mount(
    "/static",
    StaticFiles(directory=BASE_DIR / "src" / "views" / "static"),
    name="static",
)

app.mount(
    "/assets",
    StaticFiles(directory=BASE_DIR / "src" / "assets"),
    name="assets",
)

templates = config.templates
app.include_router(auth_router)
app.include_router(menus_router)
app.include_router(users_router)

wa = WhatsApp(
    phone_id=os.getenv("WA_PHONE_ID"),
    token=os.getenv("WA_TOKEN"),
    server=app,
    verify_token="chatbotudesc",
    webhook_endpoint="/webhook",
    validate_updates=False,
)

setup_webhook_handlers(wa)


@app.get("/", response_class=HTMLResponse)
def index(
    request: Request,
    session: SessionDep,
    current_user: Annotated[User, Depends(get_current_admin)],
):
    """
    Página inicial do painel de administração.
    Carrega o gerenciador de menus em layout split-view como tela padrão.
    """
    context = build_menu_split_view_context(session)
    context["current_user"] = current_user
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    context["csrf_token"] = generate_csrf_token(session_id) if session_id else ""
    return templates.TemplateResponse(request=request, name="index.html", context=context)


@app.get("/historico", response_class=HTMLResponse)
def chat_history(
    request: Request,
    current_user: Annotated[User, Depends(get_current_admin)],
):
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    csrf_token = generate_csrf_token(session_id) if session_id else ""
    return templates.TemplateResponse(
        request=request,
        name="chat_history.html",
        context={"current_user": current_user, "csrf_token": csrf_token},
    )
