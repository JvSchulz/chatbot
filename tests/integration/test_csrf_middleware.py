"""
Testes de integração para os middlewares de segurança e proteção CSRF.
"""

from fastapi import FastAPI, Request
from starlette.testclient import TestClient
from src.core.security import (
    SESSION_COOKIE_NAME,
    generate_session_token,
    generate_csrf_token,
)
from src.core.middleware import (
    SecurityHeadersMiddleware,
    CSRFProtectionMiddleware,
)


def create_test_app() -> FastAPI:
    """
    Cria uma aplicação FastAPI de teste equipada com a pilha de middlewares de segurança.

    Returns:
        Instância configurada do FastAPI para execução de testes.
    """
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(CSRFProtectionMiddleware)

    @app.api_route("/", methods=["GET", "HEAD", "OPTIONS"])
    def root(request: Request):
        return {"status": "ok", "path": request.url.path}

    @app.post("/login")
    def login_endpoint(request: Request):
        return {"status": "logged_in", "path": request.url.path}

    @app.post("/logout")
    def logout_endpoint(request: Request):
        return {"status": "logged_out", "path": request.url.path}

    @app.post("/webhook")
    def webhook_endpoint(request: Request):
        return {"status": "webhook_received", "path": request.url.path}

    @app.post("/menus")
    def create_menu(request: Request):
        return {"status": "menu_created", "path": request.url.path}

    @app.put("/menus/1")
    def update_menu(request: Request):
        return {"status": "menu_updated", "path": request.url.path}

    @app.patch("/menus/1")
    def patch_menu(request: Request):
        return {"status": "menu_patched", "path": request.url.path}

    @app.delete("/menus/1")
    def delete_menu(request: Request):
        return {"status": "menu_deleted", "path": request.url.path}

    return app


def test_security_headers_middleware_adds_expected_headers():
    """
    Verifica se SecurityHeadersMiddleware anexa cabeçalhos de segurança obrigatórios às respostas.
    """
    app = create_test_app()
    client = TestClient(app)

    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert response.headers["Strict-Transport-Security"] == "max-age=31536000; includeSubDomains"
    assert response.headers["Content-Security-Policy"] == (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none';"
    )


def test_csrf_middleware_allows_safe_methods():
    """
    Verifica se requisições GET, HEAD e OPTIONS passam livremente sem necessidade de token CSRF.
    """
    app = create_test_app()
    client = TestClient(app)

    response_get = client.get("/")
    assert response_get.status_code == 200
    assert response_get.json()["path"] == "/"

    response_head = client.head("/")
    assert response_head.status_code == 200

    response_options = client.options("/")
    assert response_options.status_code == 200


def test_csrf_middleware_exempts_webhook():
    """
    Garante que requisições POST para /webhook passem sem cookie e sem token CSRF.
    """
    app = create_test_app()
    client = TestClient(app)

    response = client.post("/webhook", json={"entry": []})
    assert response.status_code == 200
    assert response.json() == {"status": "webhook_received", "path": "/webhook"}


def test_csrf_middleware_exempts_login():
    """
    Garante que requisições POST para /login passem sem token CSRF prévio.
    """
    app = create_test_app()
    client = TestClient(app)

    response = client.post("/login", data={"username": "a", "password": "b"})
    assert response.status_code == 200
    assert response.json() == {"status": "logged_in", "path": "/login"}


def test_csrf_middleware_exempts_logout():
    """
    Garante que requisições POST para /logout passem sem exigir validação CSRF.
    """
    app = create_test_app()
    client = TestClient(app)

    response = client.post("/logout")
    assert response.status_code == 200
    assert response.json() == {"status": "logged_out", "path": "/logout"}


def test_csrf_middleware_blocks_admin_post_without_cookie_or_token():
    """
    Garante que rotas administrativas state-changing rejeitem requisições sem CSRF com 403.
    """
    app = create_test_app()
    client = TestClient(app)

    response = client.post("/menus", json={"name": "Novo Menu"})
    assert response.status_code == 403
    assert response.json() == {
        "detail": "Token CSRF ausente ou inválido: sessão ausente."
    }


def test_csrf_middleware_blocks_admin_put_and_patch_without_csrf():
    """
    Garante que métodos PUT e PATCH exijam token CSRF válido.
    """
    app = create_test_app()
    client = TestClient(app)

    session_id = generate_session_token()
    client.cookies.set(SESSION_COOKIE_NAME, session_id)

    res_put = client.put("/menus/1", json={})
    assert res_put.status_code == 403
    assert res_put.json() == {"detail": "Token CSRF ausente ou inválido."}

    res_patch = client.patch("/menus/1", json={})
    assert res_patch.status_code == 403
    assert res_patch.json() == {"detail": "Token CSRF ausente ou inválido."}


def test_csrf_middleware_blocks_admin_post_with_invalid_token():
    """
    Garante que token CSRF inválido seja rejeitado com 403.
    """
    app = create_test_app()
    client = TestClient(app)

    session_id = generate_session_token()
    client.cookies.set(SESSION_COOKIE_NAME, session_id)

    response = client.post(
        "/menus",
        json={"name": "Novo Menu"},
        headers={"X-CSRF-Token": "invalid_forged_token"},
    )
    assert response.status_code == 403
    assert response.json() == {"detail": "Token CSRF ausente ou inválido."}


def test_csrf_middleware_allows_admin_post_with_valid_token():
    """
    Garante que requisições com token CSRF válido correspondente à sessão passem com 200.
    """
    app = create_test_app()
    client = TestClient(app)

    session_id = generate_session_token()
    valid_csrf_token = generate_csrf_token(session_id)
    client.cookies.set(SESSION_COOKIE_NAME, session_id)

    response = client.post(
        "/menus",
        json={"name": "Novo Menu"},
        headers={"X-CSRF-Token": valid_csrf_token},
    )
    assert response.status_code == 200
    assert response.json() == {"status": "menu_created", "path": "/menus"}


def test_csrf_middleware_allows_admin_put_patch_delete_with_valid_token():
    """
    Garante que métodos PUT, PATCH e DELETE com token CSRF válido sejam autorizados.
    """
    app = create_test_app()
    client = TestClient(app)

    session_id = generate_session_token()
    valid_csrf_token = generate_csrf_token(session_id)
    client.cookies.set(SESSION_COOKIE_NAME, session_id)
    headers = {"X-CSRF-Token": valid_csrf_token}

    res_put = client.put("/menus/1", headers=headers)
    assert res_put.status_code == 200

    res_patch = client.patch("/menus/1", headers=headers)
    assert res_patch.status_code == 200

    res_delete = client.delete("/menus/1", headers=headers)
    assert res_delete.status_code == 200
    assert res_delete.json() == {"status": "menu_deleted", "path": "/menus/1"}
