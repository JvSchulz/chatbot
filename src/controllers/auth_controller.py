"""
Controlador de autenticação de administradores, ciclo de sessões e controle de acesso.
"""

from datetime import datetime, timezone, timedelta
from html import escape
from fastapi import APIRouter, Request, Form, HTTPException, status, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import select
from slowapi import Limiter
from slowapi.util import get_remote_address

from src.core import config
from src.core.db import SessionDep
from src.core.security import (
    SESSION_COOKIE_NAME,
    SECURE_SESSION_COOKIE_NAME,
    DUMMY_HASH,
    verify_password,
    generate_session_token,
    get_session_token_from_request,
    session_cookie_name,
)
from src.models.user_model import User
from src.models.session_model import AdminSession

INVALID_CREDENTIALS_MESSAGE = "Usuário ou senha inválidos."
RATE_LIMIT_MESSAGE = "Muitas tentativas de login. Aguarde um minuto e tente novamente."

router = APIRouter(tags=["auth"])
templates = config.templates
limiter = Limiter(key_func=get_remote_address)


def get_current_admin(
    request: Request,
    session: SessionDep,
) -> User:
    """
    Identifica e autentica o administrador a partir da sessão ativa no cookie.

    Args:
        request: Objeto da requisição HTTP recebida.
        session: Sessão do banco de dados SQLite.

    Returns:
        Instância de User autenticada.

    Raises:
        HTTPException: Status 401 caso a sessão seja ausente, inválida ou expirada.
    """
    session_id = get_session_token_from_request(request)
    if not session_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sessão não autenticada.",
        )

    admin_session = session.get(AdminSession, session_id)
    if not admin_session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sessão inválida.",
        )

    if admin_session.expires_at < datetime.now(timezone.utc):
        session.delete(admin_session)
        session.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sessão expirada.",
        )

    user = session.get(User, admin_session.user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário associado à sessão não encontrado.",
        )

    return user


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    """
    Renderiza o formulário de login do painel administrativo.

    Args:
        request: Objeto da requisição HTTP.

    Returns:
        Template HTML com os campos de autenticação.
    """
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"error": None},
    )


@router.post("/login")
@limiter.limit("5/minute")
def login_submit(
    request: Request,
    session: SessionDep,
    username: str = Form(...),
    password: str = Form(...),
):
    """
    Processa a submissão de credenciais com proteção contra temporização e força bruta.

    Args:
        request: Requisição HTTP interceptada.
        session: Sessão do banco de dados.
        username: Nome de usuário informado no formulário.
        password: Senha em texto puro.

    Returns:
        Resposta HTTP configurando cookie __Host-session ou erro 401 genérico.
    """
    user = session.exec(select(User).where(User.login == username)).first()

    if not user:
        verify_password(password, DUMMY_HASH)
        return build_login_error_response(request, INVALID_CREDENTIALS_MESSAGE, status.HTTP_401_UNAUTHORIZED)

    if not verify_password(password, user.password or ""):
        return build_login_error_response(request, INVALID_CREDENTIALS_MESSAGE, status.HTTP_401_UNAUTHORIZED)

    session_token = generate_session_token()
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("User-Agent")

    admin_session = AdminSession(
        id=session_token,
        user_id=user.id,  # type: ignore
        expires_at=datetime.now(timezone.utc) + timedelta(hours=12),
        ip_address=client_ip,
        user_agent=user_agent,
    )
    session.add(admin_session)
    session.commit()

    return _build_auth_success_response(request, session_token)


@router.post("/logout")
def logout_submit(
    request: Request,
    session: SessionDep,
):
    """
    Invalida a sessão ativa no banco de dados e remove o cookie do cliente.

    Args:
        request: Requisição HTTP recebida.
        session: Sessão ativa do banco de dados.

    Returns:
        Redirecionamento para a tela de login com cookie limpo.
    """
    session_id = get_session_token_from_request(request)
    if session_id:
        existing_session = session.get(AdminSession, session_id)
        if existing_session:
            session.delete(existing_session)
            session.commit()

    is_htmx = request.headers.get("HX-Request") == "true"
    if is_htmx:
        response = Response(status_code=200, headers={"HX-Redirect": "/login"})
    else:
        response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    response.delete_cookie(key=SESSION_COOKIE_NAME, path="/")
    response.delete_cookie(key=SECURE_SESSION_COOKIE_NAME, path="/", secure=True)
    return response


def build_login_error_response(request: Request, message: str, status_code: int) -> Response:
    """
    Constrói a resposta de uma falha de login: fragmento HTML para HTMX ou a página de login.

    Args:
        request: Requisição HTTP originária.
        message: Mensagem, em português, exibida ao administrador.
        status_code: Status HTTP da falha (401 ou 429).

    Returns:
        Fragmento com o alerta quando a requisição vem do HTMX; página de login com a mensagem caso contrário.
    """
    if request.headers.get("HX-Request") == "true":
        return HTMLResponse(
            content=f'<div class="alert alert-danger">{escape(message)}</div>',
            status_code=status_code,
        )
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"error": message},
        status_code=status_code,
    )


def login_rate_limit_handler(request: Request, exc: Exception) -> Response:
    """
    Responde ao bloqueio por excesso de tentativas de login com uma mensagem legível.

    Args:
        request: Requisição HTTP bloqueada.
        exc: Exceção RateLimitExceeded levantada pelo limitador.

    Returns:
        Resposta 429 no formato adequado ao cliente (HTMX ou navegador).
    """
    return build_login_error_response(request, RATE_LIMIT_MESSAGE, status.HTTP_429_TOO_MANY_REQUESTS)


def _build_auth_success_response(request: Request, session_token: str) -> Response:
    """
    Constrói resposta de sucesso configurando o cookie de sessão seguro.

    Args:
        request: Requisição HTTP originária.
        session_token: Token criptográfico da sessão recém-criada.

    Returns:
        Resposta HTTP com cabeçalho Set-Cookie e redirecionamento.
    """
    is_htmx = request.headers.get("HX-Request") == "true"
    if is_htmx:
        response = Response(status_code=200, headers={"HX-Redirect": "/"})
    else:
        response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

    is_https = request.url.scheme == "https" or request.headers.get("X-Forwarded-Proto") == "https"
    response.set_cookie(
        key=session_cookie_name(is_https),
        value=session_token,
        httponly=True,
        secure=is_https,
        samesite="lax",
        path="/",
    )
    return response
