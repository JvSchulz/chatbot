"""
Testes de integração para as rotas e dependências de autenticação (AuthController).
"""

from datetime import datetime, timezone, timedelta
from fastapi import FastAPI, Depends, Request
from fastapi.responses import JSONResponse
from starlette.testclient import TestClient
from sqlmodel import Session, select

from src.core.security import (
    SESSION_COOKIE_NAME,
    hash_password,
    generate_session_token,
    generate_csrf_token,
)
from src.core.db import SessionDep
from src.models.user_model import User
from src.models.session_model import AdminSession
from src.controllers.auth_controller import router as auth_router, get_current_admin
from src.core.middleware import SecurityHeadersMiddleware, CSRFProtectionMiddleware


def create_auth_test_app() -> FastAPI:
    """
    Cria uma aplicação FastAPI dedicada para validar rotas de autenticação e proteção.

    Returns:
        Instância do FastAPI configurada com o roteador de autenticação.
    """
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(CSRFProtectionMiddleware)
    app.include_router(auth_router)

    @app.get("/admin-only")
    def admin_protected_route(current_user: User = Depends(get_current_admin)):
        return {"admin": current_user.login}

    return app


def test_get_login_page_renders_form():
    """
    GET /login deve retornar 200 e conter o formulário de login.
    """
    app = create_auth_test_app()
    client = TestClient(app)

    response = client.get("/login")
    assert response.status_code == 200
    assert "login" in response.text.lower()
    assert 'name="username"' in response.text
    assert 'name="password"' in response.text


def test_post_login_success_creates_session_and_cookie(session: Session):
    """
    POST /login com credenciais válidas deve criar AdminSession e configurar cookie seguro.
    """
    user = User(
        login="valid_admin",
        password=hash_password("SegredoForte123"),
        is_admin=True,
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    app = create_auth_test_app()
    client = TestClient(app)

    response = client.post(
        "/login",
        data={"username": "valid_admin", "password": "SegredoForte123"},
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert response.headers.get("HX-Redirect") == "/"
    assert SESSION_COOKIE_NAME in response.cookies

    cookie_val = response.cookies.get(SESSION_COOKIE_NAME)
    assert cookie_val is not None

    db_session = session.get(AdminSession, cookie_val)
    assert db_session is not None
    assert db_session.user_id == user.id


def test_post_login_standard_form_redirects_303(session: Session):
    """
    POST /login via formulário padrão sem HTMX deve redirecionar com status 303 para /.
    """
    user = User(
        login="form_admin",
        password=hash_password("Senha123"),
        is_admin=True,
    )
    session.add(user)
    session.commit()

    app = create_auth_test_app()
    client = TestClient(app, follow_redirects=False)

    response = client.post(
        "/login",
        data={"username": "form_admin", "password": "Senha123"},
    )

    assert response.status_code == 303
    assert response.headers.get("Location") == "/"
    assert SESSION_COOKIE_NAME in response.cookies


def test_post_login_nonexistent_user_rejected_with_401():
    """
    POST /login com usuário inexistente deve retornar 401 e mensagem genérica.
    """
    app = create_auth_test_app()
    client = TestClient(app)

    response = client.post(
        "/login",
        data={"username": "nao_existe", "password": "qualquer_senha"},
    )

    assert response.status_code == 401
    assert "Usuário ou senha inválidos." in response.text
    assert SESSION_COOKIE_NAME not in response.cookies


def test_post_login_wrong_password_rejected_with_401(session: Session):
    """
    POST /login com senha incorreta deve retornar 401 e mensagem genérica.
    """
    user = User(
        login="admin_alvo",
        password=hash_password("SenhaCorreta123"),
        is_admin=True,
    )
    session.add(user)
    session.commit()

    app = create_auth_test_app()
    client = TestClient(app)

    response = client.post(
        "/login",
        data={"username": "admin_alvo", "password": "SenhaErradaTotal"},
    )

    assert response.status_code == 401
    assert "Usuário ou senha inválidos." in response.text
    assert SESSION_COOKIE_NAME not in response.cookies


def test_post_logout_clears_session_and_cookie(session: Session):
    """
    POST /logout deve deletar AdminSession do banco e remover o cookie de sessão.
    """
    user = User(login="logout_user", password=hash_password("123"), is_admin=True)
    session.add(user)
    session.commit()
    session.refresh(user)

    token = generate_session_token()
    csrf = generate_csrf_token(token)
    admin_session = AdminSession(
        id=token,
        user_id=user.id,  # type: ignore
        expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
    )
    session.add(admin_session)
    session.commit()

    app = create_auth_test_app()
    client = TestClient(app)
    client.cookies.set(SESSION_COOKIE_NAME, token)

    response = client.post(
        "/logout",
        headers={"X-CSRF-Token": csrf, "HX-Request": "true"},
    )

    assert response.status_code == 200
    assert response.headers.get("HX-Redirect") == "/login"

    # Verifica exclusão no banco
    db_session = session.get(AdminSession, token)
    assert db_session is None


def test_get_current_admin_rejects_unauthenticated():
    """
    Acesso à rota protegida sem cookie deve retornar 401 Unauthorized.
    """
    app = create_auth_test_app()
    client = TestClient(app)

    response = client.get("/admin-only")
    assert response.status_code == 401
    assert "não autenticada" in response.text.lower()


def test_get_current_admin_rejects_expired_session(session: Session):
    """
    Acesso com sessão expirada deve remover o registro e retornar 401 Unauthorized.
    """
    user = User(login="expired_user", password=hash_password("123"), is_admin=True)
    session.add(user)
    session.commit()
    session.refresh(user)

    token = generate_session_token()
    admin_session = AdminSession(
        id=token,
        user_id=user.id,  # type: ignore
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=5),
    )
    session.add(admin_session)
    session.commit()

    app = create_auth_test_app()
    client = TestClient(app)
    client.cookies.set(SESSION_COOKIE_NAME, token)

    response = client.get("/admin-only")
    assert response.status_code == 401
    assert "expirada" in response.text.lower()

    # Confirma deleção da sessão expirada
    assert session.get(AdminSession, token) is None


def test_get_current_admin_allows_valid_session(session: Session):
    """
    Acesso com sessão válida ativa deve retornar dados do administrador autenticado.
    """
    user = User(login="active_admin", password=hash_password("123"), is_admin=True)
    session.add(user)
    session.commit()
    session.refresh(user)

    token = generate_session_token()
    admin_session = AdminSession(
        id=token,
        user_id=user.id,  # type: ignore
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    session.add(admin_session)
    session.commit()

    app = create_auth_test_app()
    client = TestClient(app)
    client.cookies.set(SESSION_COOKIE_NAME, token)

    response = client.get("/admin-only")
    assert response.status_code == 200
    assert response.json() == {"admin": "active_admin"}


def test_post_login_migrates_legacy_plaintext_password(session: Session):
    """
    POST /login com senha legada em texto puro deve autenticar e atualizar para Argon2id.
    """
    user = User(login="legacy_user", password="plain_password_123", is_admin=True)
    session.add(user)
    session.commit()
    session.refresh(user)

    app = create_auth_test_app()
    client = TestClient(app)

    response = client.post(
        "/login",
        data={"username": "legacy_user", "password": "plain_password_123"},
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200
    assert SESSION_COOKIE_NAME in response.cookies

    # Confirma que a senha no banco foi convertida para Argon2id
    session.refresh(user)
    assert "$argon2id$" in user.password


def test_get_current_admin_via_x_user_id_header(session: Session):
    """
    Garante suporte ao cabeçalho X-User-Id em testes automatizados.
    """
    user = User(login="header_admin", password=hash_password("123"), is_admin=True)
    session.add(user)
    session.commit()
    session.refresh(user)

    app = create_auth_test_app()
    client = TestClient(app)

    response = client.get("/admin-only", headers={"X-User-Id": str(user.id)})
    assert response.status_code == 200
    assert response.json() == {"admin": "header_admin"}


def test_get_current_admin_user_not_found(session: Session):
    """
    Garante que sessão órfã cujo usuário não existe mais resulte em 401.
    """
    token = generate_session_token()
    admin_session = AdminSession(
        id=token,
        user_id=99999,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    session.add(admin_session)
    session.commit()

    app = create_auth_test_app()
    client = TestClient(app)
    client.cookies.set(SESSION_COOKIE_NAME, token)

    response = client.get("/admin-only")
    assert response.status_code == 401


def test_post_logout_standard_request(session: Session):
    """
    POST /logout sem HTMX deve redirecionar com status 303 para /login.
    """
    user = User(login="standard_logout", password=hash_password("123"), is_admin=True)
    session.add(user)
    session.commit()

    token = generate_session_token()
    csrf = generate_csrf_token(token)
    admin_session = AdminSession(
        id=token,
        user_id=user.id,  # type: ignore
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    session.add(admin_session)
    session.commit()

    app = create_auth_test_app()
    client = TestClient(app, follow_redirects=False)
    client.cookies.set(SESSION_COOKIE_NAME, token)

    response = client.post("/logout", headers={"X-CSRF-Token": csrf})
    assert response.status_code == 303
    assert response.headers.get("Location") == "/login"


def test_unauthenticated_browser_get_redirects_to_login():
    """
    Navegação via browser sem sessão ativa para rotas protegidas deve redirecionar para /login (303).
    """
    from main import app
    client = TestClient(app, follow_redirects=False)

    response = client.get("/")
    assert response.status_code == 303
    assert response.headers.get("Location") == "/login"


def test_unauthenticated_htmx_request_returns_hx_redirect():
    """
    Requisição HTMX sem sessão ativa para rotas protegidas deve retornar 200 com HX-Redirect: /login.
    """
    from main import app
    client = TestClient(app)

    response = client.get("/menus/novo/card", headers={"HX-Request": "true"})
    assert response.status_code == 200
    assert response.headers.get("HX-Redirect") == "/login"


def test_unauthenticated_api_request_with_accept_json_returns_401():
    """
    Requisição programática com Accept: application/json sem sessão deve reter status 401 JSON.
    """
    from main import app
    client = TestClient(app)

    response = client.get("/menus", headers={"Accept": "application/json"})
    assert response.status_code == 401
    assert response.headers.get("content-type", "").startswith("application/json")
