"""
Testes de integração do layout compartilhado do painel: base.html, navegação e redirecionamento da raiz.
"""

import re

import pytest
from fastapi.testclient import TestClient

from main import app
from src.core.config import BASE_DIR

TEMPLATES = BASE_DIR / "src" / "views" / "templates"


def active_nav_items(html: str) -> list[str]:
    """Extrai os textos dos links de navegação marcados como ativos."""
    return re.findall(r'<a href="[^"]+" class="nav-item active">([^<]+)</a>', html)


def test_root_redirects_authenticated_admin_to_menus(auth_client: TestClient):
    response = auth_client.get("/", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/menus"


def test_root_still_redirects_anonymous_visitor_to_login():
    response = TestClient(app, follow_redirects=False).get("/")

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_index_template_was_replaced_by_base_and_menus():
    assert not (TEMPLATES / "index.html").exists()
    assert (TEMPLATES / "base.html").exists()
    assert (TEMPLATES / "menus.html").exists()


@pytest.mark.parametrize("template", ["menus.html", "users.html", "chat_history.html", "login.html"])
def test_every_page_extends_the_base_layout(template: str):
    source = (TEMPLATES / template).read_text(encoding="utf-8")

    assert '{% extends "base.html" %}' in source


@pytest.mark.parametrize(
    ("path", "label"),
    [("/menus", "Menus"), ("/usuarios", "Usuários"), ("/historico", "Histórico")],
)
def test_navigation_marks_only_the_current_page(auth_client: TestClient, path: str, label: str):
    response = auth_client.get(path)

    assert active_nav_items(response.text) == [label]


def test_navigation_links_to_menus_directly(auth_client: TestClient):
    response = auth_client.get("/menus")

    assert '<a href="/menus" class="nav-item active">Menus</a>' in response.text


@pytest.mark.parametrize("path", ["/menus", "/usuarios", "/historico"])
def test_every_admin_page_has_the_alert_region_and_the_shared_script(auth_client: TestClient, path: str):
    response = auth_client.get(path)

    assert 'id="page-alert"' in response.text
    assert '<script src="/static/app.js"></script>' in response.text


def test_csrf_token_travels_only_in_hx_headers(auth_client: TestClient):
    response = auth_client.get("/menus")

    assert "hx-headers=" in response.text
    assert "X-CSRF-Token" in response.text
    assert 'name="csrf-token"' not in response.text


def test_htmx_config_disables_injected_indicator_styles(auth_client: TestClient):
    response = auth_client.get("/menus")

    assert '"includeIndicatorStyles": false' in response.text
