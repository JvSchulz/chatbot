"""
Testes de integração das confirmações de sucesso e dos alertas de erro nos cards de menu e de usuário.
"""

import re

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from src.models.menu_model import Menu
from src.models.user_model import User
from src.services.menu_service import MenuData, create_menu
from src.services.user_service import UserData, create_user

SUCCESS_ALERT = re.compile(r'<div class="alert alert-success" role="status">([^<]*)</div>')
ERROR_ALERT = re.compile(r'<div class="alert alert-danger" role="alert">([^<]*)</div>')

MENU_FORM = {"name": "novo", "selection_name": "Novo", "message": "Texto", "is_root": "false"}


def success_text(html: str) -> str | None:
    found = SUCCESS_ALERT.search(html)
    return found.group(1) if found else None


def error_text(html: str) -> str | None:
    found = ERROR_ALERT.search(html)
    return found.group(1) if found else None


@pytest.fixture(name="root")
def root_fixture(session: Session) -> Menu:
    return create_menu(session, MenuData(name="raiz", selection_name="Raiz", message="Olá", is_root=True))


@pytest.fixture(name="leaf")
def leaf_fixture(session: Session, root: Menu) -> Menu:
    return create_menu(session, MenuData(name="folha", selection_name="Folha", message="M", parent_id=root.id))


@pytest.fixture(name="other_user")
def other_user_fixture(session: Session, auth_client: TestClient) -> User:
    return create_user(session, UserData(login="colega", password="SenhaColega123", is_admin=False))


def test_creating_a_menu_confirms_it_in_the_card(auth_client: TestClient, root: Menu):
    response = auth_client.post("/menus", data={**MENU_FORM, "parent_id": str(root.id)})

    assert response.status_code == 200
    assert success_text(response.text) == "Menu criado com sucesso."
    assert error_text(response.text) is None


def test_updating_a_menu_confirms_it_in_the_card(auth_client: TestClient, root: Menu, leaf: Menu):
    response = auth_client.post(f"/menus/{leaf.id}", data={**MENU_FORM, "parent_id": str(root.id)})

    assert response.status_code == 200
    assert success_text(response.text) == "Menu atualizado com sucesso."
    assert error_text(response.text) is None


def test_deleting_a_menu_confirms_it_in_the_blank_card(auth_client: TestClient, leaf: Menu):
    response = auth_client.delete(f"/menus/{leaf.id}")

    assert response.status_code == 200
    assert success_text(response.text) == "Menu excluído com sucesso."
    assert "data-entity-id" not in response.text
    assert "Novo Menu" in response.text


def test_the_menu_confirmation_sits_in_the_error_slot(auth_client: TestClient, root: Menu):
    response = auth_client.post("/menus", data={**MENU_FORM, "parent_id": str(root.id)})

    slot = re.search(r'<div id="menu-error">(.*?)</div>\s*</div>\s*<form', response.text, re.DOTALL)
    assert slot is not None and "alert-success" in slot.group(1)


def test_loading_a_menu_card_shows_no_confirmation(auth_client: TestClient, leaf: Menu):
    for path in (f"/menus/{leaf.id}/card", "/menus/novo/card", "/menus"):
        html = auth_client.get(path).text

        assert success_text(html) is None and "alert-success" not in html and 'role="status"' not in html


def test_a_menu_validation_error_is_announced_as_an_alert(auth_client: TestClient):
    response = auth_client.post("/menus", data={**MENU_FORM, "message": "   "})

    assert response.status_code == 422
    assert error_text(response.text) == "Preencha nome, texto de seleção e mensagem."
    assert success_text(response.text) is None


def test_a_blocked_menu_deletion_is_announced_as_an_alert(auth_client: TestClient, root: Menu, leaf: Menu):
    response = auth_client.delete(f"/menus/{root.id}")

    assert response.status_code == 400
    assert error_text(response.text) == "Não é possível excluir um menu que possui submenus vinculados."
    assert success_text(response.text) is None


def test_creating_a_user_confirms_it_in_the_card(auth_client: TestClient):
    response = auth_client.post("/usuarios", data={"login": "novo", "password": "SenhaNova12345"})

    assert response.status_code == 200
    assert success_text(response.text) == "Usuário criado com sucesso."
    assert error_text(response.text) is None


def test_updating_a_user_confirms_it_in_the_card(auth_client: TestClient, other_user: User):
    response = auth_client.post(f"/usuarios/{other_user.id}", data={"login": "colega2"})

    assert response.status_code == 200
    assert success_text(response.text) == "Usuário atualizado com sucesso."
    assert error_text(response.text) is None


def test_deleting_a_user_confirms_it_in_the_blank_card(auth_client: TestClient, other_user: User):
    response = auth_client.delete(f"/usuarios/{other_user.id}")

    assert response.status_code == 200
    assert success_text(response.text) == "Usuário excluído com sucesso."
    assert "data-entity-id" not in response.text
    assert "Novo Usuário" in response.text


def test_loading_a_user_card_shows_no_confirmation(auth_client: TestClient, other_user: User):
    for path in (f"/usuarios/{other_user.id}/card", "/usuarios/novo/card", "/usuarios"):
        html = auth_client.get(path).text

        assert success_text(html) is None and "alert-success" not in html and 'role="status"' not in html


def test_a_user_validation_error_is_announced_as_an_alert(auth_client: TestClient, other_user: User):
    response = auth_client.post("/usuarios", data={"login": "colega", "password": "SenhaNova12345"})

    assert response.status_code == 400
    assert error_text(response.text) is not None
    assert success_text(response.text) is None


def test_a_blocked_user_deletion_is_announced_as_an_alert(auth_client: TestClient, session: Session):
    admin = session.exec(select(User).where(User.login == "admin")).one()

    response = auth_client.delete(f"/usuarios/{admin.id}")

    assert response.status_code == 400
    assert error_text(response.text) is not None
    assert success_text(response.text) is None


def test_the_stylesheet_styles_the_confirmation_and_the_counter(auth_client: TestClient):
    stylesheet = auth_client.get("/static/style.css").text

    assert ".alert-success {" in stylesheet
    assert ".char-counter {" in stylesheet


def test_the_script_keeps_the_counters_in_sync(auth_client: TestClient):
    script = auth_client.get("/static/app.js").text

    assert "[data-counter]" in script
    assert '"input"' in script
    assert '"htmx:afterSwap"' in script
