"""
Teste E2E de ponta a ponta para validação do fluxo de segurança e autenticação administrativa.
"""

from fastapi.testclient import TestClient
from sqlmodel import Session, select
from src.core.security import SESSION_COOKIE_NAME, hash_password, generate_csrf_token
from src.models.user_model import User
from src.models.session_model import AdminSession
from main import app


def test_auth_security_e2e_full_lifecycle(session: Session):
    """
    Fluxo E2E de segurança:
    1. Tentativa de acesso sem autenticação a / e /menus é bloqueada com status 401.
    2. Submissão de credenciais incorretas é rejeitada com status 401 e mensagem genérica.
    3. Submissão de credenciais válidas autentica com sucesso, emite cookie __Host-session.
    4. Com o cookie e token CSRF, navega em /menus e obtém status 200.
    5. Submete logout via POST /logout, invalidando a sessão no SQLite e no cliente.
    6. Nova tentativa de acesso a /menus é imediatamente bloqueada com status 401.
    """
    # Cria administrador no banco
    admin = User(
        login="diretoria",
        password=hash_password("SenhaForte2026!"),
        is_admin=True,
    )
    session.add(admin)
    session.commit()
    session.refresh(admin)

    client = TestClient(app, base_url="https://testserver")

    # 1. Bloqueio de acesso não autenticado
    res_unauth_menus = client.get("/menus")
    assert res_unauth_menus.status_code == 401

    res_unauth_root = client.get("/")
    assert res_unauth_root.status_code == 401

    # 2. Login com senha errada
    res_bad_login = client.post(
        "/login",
        data={"username": "diretoria", "password": "SenhaCompletamenteIncorreta"},
        headers={"HX-Request": "true"},
    )
    assert res_bad_login.status_code == 401
    assert "Usuário ou senha inválidos." in res_bad_login.text
    assert SESSION_COOKIE_NAME not in client.cookies

    # 3. Login com sucesso
    res_login = client.post(
        "/login",
        data={"username": "diretoria", "password": "SenhaForte2026!"},
        headers={"HX-Request": "true"},
    )
    assert res_login.status_code == 200
    assert res_login.headers.get("HX-Redirect") == "/"
    assert SESSION_COOKIE_NAME in client.cookies

    session_token = client.cookies.get(SESSION_COOKIE_NAME)
    assert session_token is not None

    # Verifica persistência no banco
    db_session = session.get(AdminSession, session_token)
    assert db_session is not None
    assert db_session.user_id == admin.id

    # 4. Acesso autenticado a /menus com token CSRF
    csrf_token = generate_csrf_token(session_token)
    client.headers.update({"X-CSRF-Token": csrf_token})

    res_auth_menus = client.get("/menus")
    assert res_auth_menus.status_code == 200
    assert "Gerenciador de Menus" in res_auth_menus.text

    # 5. Logout
    res_logout = client.post("/logout", headers={"HX-Request": "true"})
    assert res_logout.status_code == 200
    assert res_logout.headers.get("HX-Redirect") == "/login"

    # Confirma exclusão da sessão no SQLite
    session.expire_all()
    assert session.get(AdminSession, session_token) is None

    # 6. Nova tentativa pós-logout é bloqueada
    res_post_logout = client.get("/menus")
    assert res_post_logout.status_code == 401


def test_auth_rate_limiting_on_login():
    """
    Verifica se múltiplas requisições repetidas de login disparam bloqueio 429 Too Many Requests.
    """
    client = TestClient(app)

    # O rate limit configurado é de 5 requisições por minuto
    responses = []
    for _ in range(7):
        resp = client.post(
            "/login",
            data={"username": "brute_force_bot", "password": "any"},
        )
        responses.append(resp.status_code)

    assert 429 in responses
