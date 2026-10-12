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


def test_post_login_rejects_plaintext_stored_password(session: Session):
    """
    POST /login não deve autenticar nem migrar senha armazenada em texto puro.
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

    assert response.status_code == 401
    assert SESSION_COOKIE_NAME not in response.cookies
    session.refresh(user)
    assert user.password == "plain_password_123"


def test_get_current_admin_rejects_x_user_id_header(session: Session):
    """
    O cabeçalho X-User-Id não deve conceder acesso: a sessão por cookie é a única credencial.
    """
    user = User(login="header_admin", password=hash_password("123"), is_admin=True)
    session.add(user)
    session.commit()
    session.refresh(user)

    app = create_auth_test_app()
    client = TestClient(app)

    response = client.get("/admin-only", headers={"X-User-Id": str(user.id)})
    assert response.status_code == 401


def test_users_route_redirects_x_user_id_header_to_login(session: Session):
    """
    Requisição a /usuarios apenas com X-User-Id deve ser tratada como não autenticada.
    """
    from main import app

    user = User(login="header_admin", password=hash_password("123"), is_admin=True)
    session.add(user)
    session.commit()
    session.refresh(user)

    client = TestClient(app, follow_redirects=False)

    response = client.get("/usuarios", headers={"X-User-Id": str(user.id)})
    assert response.status_code == 303
    assert response.headers.get("Location") == "/login"


def test_get_current_admin_user_not_found(session: Session):
    """
    Garante que sessão órfã cujo usuário não existe mais resulte em 401.
    """
    ghost = User(login="ghost_admin", password=hash_password("123"), is_admin=True)
    session.add(ghost)
    session.commit()
    token = generate_session_token()
    session.add(
        AdminSession(
            id=token,
            user_id=ghost.id,  # type: ignore
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
    )
    session.commit()
    session.connection().exec_driver_sql("PRAGMA foreign_keys=OFF")
    session.delete(ghost)
    session.commit()
    session.connection().exec_driver_sql("PRAGMA foreign_keys=ON")

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


def test_post_logout_without_csrf_header_succeeds(session: Session):
    """
    POST /logout sem cabeçalho X-CSRF-Token deve ser aceito e realizar logout com sucesso (303).
    """
    user = User(login="logout_nocsrf", password=hash_password("123"), is_admin=True)
    session.add(user)
    session.commit()

    token = generate_session_token()
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

    response = client.post("/logout")
    assert response.status_code == 303
    assert response.headers.get("Location") == "/login"

    session.expire_all()
    assert session.get(AdminSession, token) is None


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


def _create_login_user(session: Session) -> None:
    """Cria o administrador usado nos testes de nome de cookie por esquema."""
    session.add(User(login="cookie_admin", password=hash_password("SegredoForte123"), is_admin=True))
    session.commit()


def _login(client: TestClient, headers: dict[str, str] | None = None):
    """Executa POST /login com as credenciais do administrador de testes."""
    return client.post(
        "/login",
        data={"username": "cookie_admin", "password": "SegredoForte123"},
        headers=headers,
    )


def _set_cookie_headers(response) -> list[str]:
    """Lista os valores dos cabeçalhos Set-Cookie da resposta."""
    return response.headers.get_list("set-cookie")


def test_login_over_https_sets_host_prefixed_secure_cookie(session: Session):
    """
    Login sobre HTTPS deve definir __Host-session com HttpOnly, Secure, SameSite=Lax e Path=/.
    """
    _create_login_user(session)
    client = TestClient(create_auth_test_app(), base_url="https://testserver", follow_redirects=False)

    cookies = _set_cookie_headers(_login(client))

    assert len(cookies) == 1
    assert cookies[0].startswith("__Host-session=")
    assert "HttpOnly" in cookies[0]
    assert "Secure" in cookies[0]
    assert "SameSite=lax" in cookies[0]
    assert "Path=/" in cookies[0]


def test_login_behind_https_proxy_sets_host_prefixed_secure_cookie(session: Session):
    """
    Login com X-Forwarded-Proto: https deve se comportar como HTTPS.
    """
    _create_login_user(session)
    client = TestClient(create_auth_test_app(), follow_redirects=False)

    cookies = _set_cookie_headers(_login(client, {"X-Forwarded-Proto": "https"}))

    assert cookies[0].startswith("__Host-session=")
    assert "Secure" in cookies[0]


def test_login_over_http_sets_plain_session_cookie_without_secure(session: Session):
    """
    Login sobre HTTP deve definir o cookie session com HttpOnly e SameSite=Lax, sem Secure.
    """
    _create_login_user(session)
    client = TestClient(create_auth_test_app(), base_url="http://testserver", follow_redirects=False)

    cookies = _set_cookie_headers(_login(client))

    assert len(cookies) == 1
    assert cookies[0].startswith("session=")
    assert "HttpOnly" in cookies[0]
    assert "SameSite=lax" in cookies[0]
    assert "Secure" not in cookies[0]


def test_logout_clears_both_cookie_names(session: Session):
    """
    Logout deve limpar session e __Host-session, este último com Secure para o navegador aceitar.
    """
    client = TestClient(create_auth_test_app(), follow_redirects=False)

    cookies = _set_cookie_headers(client.post("/logout"))

    plain = [c for c in cookies if c.startswith("session=")]
    host = [c for c in cookies if c.startswith("__Host-session=")]
    assert len(plain) == 1
    assert len(host) == 1
    assert "Max-Age=0" in plain[0]
    assert "Max-Age=0" in host[0]
    assert "Secure" in host[0]
    assert "Path=/" in host[0]


def test_get_current_admin_accepts_host_prefixed_cookie(session: Session):
    """
    A leitura da sessão deve aceitar o cookie __Host-session emitido sobre HTTPS.
    """
    user = User(login="host_admin", password=hash_password("123"), is_admin=True)
    session.add(user)
    session.commit()
    session.refresh(user)
    token = generate_session_token()
    session.add(
        AdminSession(
            id=token,
            user_id=user.id,  # type: ignore
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
    )
    session.commit()

    client = TestClient(create_auth_test_app(), base_url="https://testserver")
    client.cookies.set("__Host-session", token)

    response = client.get("/admin-only")
    assert response.status_code == 200
    assert response.json() == {"admin": "host_admin"}


def test_get_current_admin_prefers_host_prefixed_cookie_over_stale_plain_cookie(session: Session):
    """
    Um cookie session remanescente não deve ofuscar o __Host-session recém-emitido sobre HTTPS.
    """
    user = User(login="stale_admin", password=hash_password("123"), is_admin=True)
    session.add(user)
    session.commit()
    session.refresh(user)
    token = generate_session_token()
    session.add(
        AdminSession(
            id=token,
            user_id=user.id,  # type: ignore
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
    )
    session.commit()

    client = TestClient(create_auth_test_app(), base_url="https://testserver")
    client.cookies.set("session", "token-antigo-invalido")
    client.cookies.set("__Host-session", token)

    response = client.get("/admin-only")
    assert response.status_code == 200
    assert response.json() == {"admin": "stale_admin"}
