"""
Testes de integração das mensagens de falha do login: credenciais inválidas e limite de tentativas.
"""

import pytest
from fastapi.testclient import TestClient

from main import app

INVALID_CREDENTIALS_MESSAGE = "Usuário ou senha inválidos."
RATE_LIMIT_MESSAGE = "Muitas tentativas de login. Aguarde um minuto e tente novamente."
HTMX = {"HX-Request": "true"}
WRONG_CREDENTIALS = {"username": "ninguem", "password": "errada"}
LOGIN_ATTEMPTS_PER_MINUTE = 5


def exhaust_login_attempts(client: TestClient) -> None:
    """Consome o limite de tentativas de login do minuto."""
    for _ in range(LOGIN_ATTEMPTS_PER_MINUTE):
        assert client.post("/login", data=WRONG_CREDENTIALS).status_code == 401


def test_htmx_wrong_password_returns_a_swappable_401_fragment():
    response = TestClient(app).post("/login", data=WRONG_CREDENTIALS, headers=HTMX)

    assert response.status_code == 401
    assert response.headers["content-type"].startswith("text/html")
    assert response.text == f'<div class="alert alert-danger">{INVALID_CREDENTIALS_MESSAGE}</div>'


def test_browser_wrong_password_returns_the_login_page_with_the_message():
    response = TestClient(app).post("/login", data=WRONG_CREDENTIALS)

    assert response.status_code == 401
    assert "Login Administrativo" in response.text
    assert INVALID_CREDENTIALS_MESSAGE in response.text


def test_htmx_rate_limited_login_returns_a_swappable_429_fragment():
    client = TestClient(app)
    exhaust_login_attempts(client)

    response = client.post("/login", data=WRONG_CREDENTIALS, headers=HTMX)

    assert response.status_code == 429
    assert response.headers["content-type"].startswith("text/html")
    assert response.text == f'<div class="alert alert-danger">{RATE_LIMIT_MESSAGE}</div>'


def test_browser_rate_limited_login_returns_the_login_page_with_the_message():
    client = TestClient(app)
    exhaust_login_attempts(client)

    response = client.post("/login", data=WRONG_CREDENTIALS)

    assert response.status_code == 429
    assert "Login Administrativo" in response.text
    assert RATE_LIMIT_MESSAGE in response.text


@pytest.mark.parametrize("headers", [HTMX, {}])
def test_rate_limited_login_does_not_check_the_credentials(headers: dict[str, str]):
    client = TestClient(app)
    exhaust_login_attempts(client)

    response = client.post("/login", data=WRONG_CREDENTIALS, headers=headers)

    assert INVALID_CREDENTIALS_MESSAGE not in response.text
