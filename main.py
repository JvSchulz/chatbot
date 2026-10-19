from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Depends, HTTPException, status, Response
from fastapi.responses import RedirectResponse
from fastapi.exception_handlers import http_exception_handler
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session
from slowapi.errors import RateLimitExceeded

from src.core import config
from src.core.db import create_db_and_tables, engine
from src.core.middleware import SecurityHeadersMiddleware, CSRFProtectionMiddleware
from src.models import menu_model, user_model, chat_history_model, user_session_model, session_model
from src.services.user_service import seed_first_admin
from src.controllers.auth_controller import router as auth_router, get_current_admin, limiter, login_rate_limit_handler
from src.controllers.history_controller import router as history_router
from src.controllers.menus_controller import router as menus_router
from src.controllers.users_controller import router as users_router
from src.controllers.webhook_controller import setup_webhook_handlers
from pywa.client import WhatsApp
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s:     %(message)s")
# A PyWa registra as atualizações brutas (telefone, BSUID e texto) em DEBUG.
logging.getLogger("pywa").setLevel(logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Prepara o banco na inicialização: cria as tabelas e o primeiro administrador.

    Args:
        app: Aplicação FastAPI que está iniciando.
    """
    create_db_and_tables()
    initial_password = config.settings.admin_initial_password
    with Session(engine) as session:
        seed_first_admin(session, initial_password.get_secret_value() if initial_password else None)
    yield


app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, login_rate_limit_handler)


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

app.include_router(auth_router)
app.include_router(menus_router)
app.include_router(users_router)
app.include_router(history_router)

wa = WhatsApp(
    phone_id=config.settings.wa_phone_id,
    token=config.settings.wa_token.get_secret_value(),
    app_secret=config.settings.app_secret.get_secret_value(),
    server=app,
    verify_token=config.settings.wa_verify_token.get_secret_value(),
    webhook_endpoint="/webhook",
    validate_updates=True,
)

setup_webhook_handlers(wa)


@app.get("/", dependencies=[Depends(get_current_admin)])
def index() -> RedirectResponse:
    """
    Redireciona a raiz do painel para o gerenciador de menus, a tela padrão dos administradores.
    """
    return RedirectResponse(url="/menus", status_code=status.HTTP_303_SEE_OTHER)
