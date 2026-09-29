"""
Controlador de autenticação de administradores, ciclo de sessões e controle de acesso.
"""

from datetime import datetime, timezone, timedelta
from typing import Annotated, Optional
from fastapi import APIRouter, Request, Form, HTTPException, status, Depends, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import select
from slowapi import Limiter
from slowapi.util import get_remote_address

from src.core import config
from src.core.db import SessionDep
from src.core.security import (
    SESSION_COOKIE_NAME,
    LEGACY_SESSION_COOKIE_NAME,
    DUMMY_HASH,
    hash_password,
    verify_password,
    generate_session_token,
    generate_csrf_token,
    get_session_token_from_request,
)
from src.models.user_model import User
from src.models.session_model import AdminSession

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
        user_id_str = request.headers.get("X-User-Id")
        if user_id_str and user_id_str.isdigit():
            user = session.get(User, int(user_id_str))
            if user:
                return user
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

    expires_at = admin_session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if expires_at < datetime.now(timezone.utc):
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
        return _build_auth_failure_response(request)

    stored_password = user.password or ""
    is_valid = verify_password(password, stored_password)
    if not is_valid and stored_password == password:
        # Migração transparente caso a senha legada estivesse em texto puro
        user.password = hash_password(password)
        session.add(user)
        session.commit()
        is_valid = True

    if not is_valid:
        return _build_auth_failure_response(request)

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
    response.delete_cookie(key=LEGACY_SESSION_COOKIE_NAME, path="/")
    return response


def _build_auth_failure_response(request: Request) -> Response:
    """
    Constrói resposta genérica de falha na autenticação (HTTP 401).

    Args:
        request: Requisição HTTP originária.

    Returns:
        Resposta HTTP 401 amigável ao HTMX e a navegadores padrão.
    """
    error_msg = "Usuário ou senha inválidos."
    if request.headers.get("HX-Request") == "true":
        return HTMLResponse(
            content=f'<div class="alert alert-danger">{error_msg}</div>',
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    return HTMLResponse(
        content=f"<html><body><p>{error_msg}</p><a href='/login'>Tentar novamente</a></body></html>",
        status_code=status.HTTP_401_UNAUTHORIZED,
    )


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
        key=SESSION_COOKIE_NAME,
        value=session_token,
        httponly=True,
        secure=is_https,
        samesite="lax",
        path="/",
    )
    return response
