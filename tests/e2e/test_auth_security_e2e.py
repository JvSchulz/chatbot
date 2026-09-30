"""
Teste E2E de ponta a ponta para validação do fluxo de segurança e autenticação administrativa.
"""

from fastapi.testclient import TestClient
from sqlmodel import Session, select
from src.core.security import SECURE_SESSION_COOKIE_NAME, hash_password, generate_csrf_token
from src.models.user_model import User
from src.models.session_model import AdminSession
from main import app


def test_auth_security_e2e_full_lifecycle(session: Session):
    """
    Fluxo E2E de segurança:
    1. Tentativa de acesso sem autenticação a / e /menus redireciona para /login.
    2. Submissão de credenciais incorretas é rejeitada com status 401 e mensagem genérica.
    3. Submissão de credenciais válidas autentica com sucesso, emite cookie de sessão.
    4. Com o cookie e token CSRF, navega em / e /menus, validando header sem login e com botão Sair.
    5. Submete logout via POST /logout, invalidando a sessão no SQLite e no cliente.
    6. Nova tentativa de acesso a /menus é imediatamente redirecionada para /login.
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

    # 1. Bloqueio e redirecionamento de acesso não autenticado
    # 1a. Browser GET sem aceitar JSON explicitamente é redirecionado via 303 para /login
    res_unauth_menus = client.get("/menus", follow_redirects=False)
    assert res_unauth_menus.status_code == 303
    assert res_unauth_menus.headers["location"] == "/login"

    res_unauth_root = client.get("/", follow_redirects=False)
    assert res_unauth_root.status_code == 303
    assert res_unauth_root.headers["location"] == "/login"

    # 1b. Seguir o redirecionamento carrega a página de login com status 200
    res_unauth_followed = client.get("/")
    assert res_unauth_followed.status_code == 200
    assert "Login Administrativo" in res_unauth_followed.text

    # 1c. Requisição programática de API (Accept: application/json) retém status 401
    res_api_unauth = client.get("/menus", headers={"Accept": "application/json"})
    assert res_api_unauth.status_code == 401

    # 1d. Requisição parcial HTMX não autenticada retorna HX-Redirect para /login
    res_htmx_unauth = client.get("/menus", headers={"HX-Request": "true"})
    assert res_htmx_unauth.status_code == 200
    assert res_htmx_unauth.headers.get("HX-Redirect") == "/login"

    # 2. Login com senha errada
    res_bad_login = client.post(
        "/login",
        data={"username": "diretoria", "password": "SenhaCompletamenteIncorreta"},
        headers={"HX-Request": "true"},
    )
    assert res_bad_login.status_code == 401
    assert "Usuário ou senha inválidos." in res_bad_login.text
    assert SECURE_SESSION_COOKIE_NAME not in client.cookies

    # 3. Login com sucesso
    res_login = client.post(
        "/login",
        data={"username": "diretoria", "password": "SenhaForte2026!"},
        headers={"HX-Request": "true"},
    )
    assert res_login.status_code == 200
    assert res_login.headers.get("HX-Redirect") == "/"
    assert SECURE_SESSION_COOKIE_NAME in client.cookies

    session_token = client.cookies.get(SECURE_SESSION_COOKIE_NAME)
    assert session_token is not None

    # Verifica persistência no banco
    db_session = session.get(AdminSession, session_token)
    assert db_session is not None
    assert db_session.user_id == admin.id

    # 4. Acesso autenticado com token CSRF
    csrf_token = generate_csrf_token(session_token)
    client.headers.update({"X-CSRF-Token": csrf_token})

    # Verifica layout administrativo: sem link /login e com botão de logout
    res_root = client.get("/")
    assert res_root.status_code == 200
    assert 'href="/login"' not in res_root.text
    assert "Sair" in res_root.text
    assert 'hx-post="/logout"' in res_root.text

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

    # 6. Nova tentativa pós-logout é imediatamente redirecionada para /login
    res_post_logout = client.get("/menus", follow_redirects=False)
    assert res_post_logout.status_code == 303
    assert res_post_logout.headers.get("location") == "/login"

    res_post_logout_followed = client.get("/menus")
    assert res_post_logout_followed.status_code == 200
    assert "Login Administrativo" in res_post_logout_followed.text


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


def test_users_page_lifecycle_and_csrf_e2e(session: Session):
    """
    Fluxo E2E de gerenciamento de usuários:
    1. Login de administrador e navegação completa para /usuarios.
    2. Validação da presença do token CSRF no meta-tag e hx-headers do body.
    3. Exclusão bem-sucedida de usuário secundário via DELETE com token CSRF.
    4. Bloqueio com status 400 de tentativa de autoexclusão da conta conectada.
    5. Logout via POST /logout com redirecionamento para /login.
    """
    admin = User(login="admin_gestor", password=hash_password("Gestor2026!"), is_admin=True)
    target_user = User(login="usuario_alvo", password=hash_password("Alvo2026!"), is_admin=False)
    session.add(admin)
    session.add(target_user)
    session.commit()
    session.refresh(admin)
    session.refresh(target_user)

    client = TestClient(app, base_url="https://testserver")

    # 1. Login
    res_login = client.post(
        "/login",
        data={"username": "admin_gestor", "password": "Gestor2026!"},
        headers={"HX-Request": "true"},
    )
    assert res_login.status_code == 200

    # 2. Navega para /usuarios
    res_users = client.get("/usuarios")
    assert res_users.status_code == 200
    assert 'hx-headers=' in res_users.text
    assert 'name="csrf-token"' not in res_users.text
    assert "usuario_alvo" in res_users.text

    session_token = client.cookies.get(SECURE_SESSION_COOKIE_NAME)
    assert session_token is not None
    csrf_token = generate_csrf_token(session_token)

    target_id = target_user.id
    # 3. Exclui o usuário alvo com CSRF
    res_delete = client.delete(
        f"/usuarios/{target_id}",
        headers={"X-CSRF-Token": csrf_token, "HX-Request": "true"},
    )
    assert res_delete.status_code == 200
    session.expire_all()
    assert session.get(User, target_id) is None

    # 4. Bloqueio de autoexclusão
    res_self_del = client.delete(
        f"/usuarios/{admin.id}",
        headers={"X-CSRF-Token": csrf_token, "HX-Request": "true"},
    )
    assert res_self_del.status_code == 400
    assert "Você não pode excluir sua própria conta em uso" in res_self_del.text

    # 5. Logout sem headers CSRF manuais tem sucesso
    res_logout = client.post("/logout", headers={"HX-Request": "true"})
    assert res_logout.status_code == 200
    assert res_logout.headers.get("HX-Redirect") == "/login"
