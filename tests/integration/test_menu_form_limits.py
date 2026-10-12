"""
Testes de integração do formulário de menu: limites de texto, contador e ordem das listas.
"""

import re

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from src.models.menu_model import Menu
from src.services.menu_service import MenuData, create_menu

FORM = {"name": "novo", "selection_name": "Novo", "message": "Texto", "is_root": "true"}


def tag_of(html: str, element_id: str) -> str:
    """Devolve a tag de abertura do input ou textarea com o id informado."""
    found = re.search(rf'<(?:input|textarea)[^>]*\sid="{element_id}"[^>]*>', html, re.DOTALL)
    assert found is not None, element_id
    return found.group(0)


def add(session: Session, name: str, selection_name: str | None = None, parent_id: int | None = None) -> Menu:
    menu = Menu(name=name, selection_name=selection_name or name, message="M", parent_id=parent_id)
    session.add(menu)
    session.commit()
    session.refresh(menu)
    return menu


def test_the_form_limits_come_from_the_service(auth_client: TestClient):
    html = auth_client.get("/menus/novo/card").text

    assert 'maxlength="20"' in tag_of(html, "selection_name")
    assert 'maxlength="991"' in tag_of(html, "message")


def test_both_limited_fields_ask_for_a_live_counter(auth_client: TestClient):
    html = auth_client.get("/menus/novo/card").text

    assert "data-counter" in tag_of(html, "selection_name")
    assert "data-counter" in tag_of(html, "message")


def test_the_internal_name_has_neither_limit_nor_counter(auth_client: TestClient):
    tag = tag_of(auth_client.get("/menus/novo/card").text, "name")

    assert "maxlength" not in tag and "data-counter" not in tag


def test_the_limits_are_present_on_the_full_page_and_on_an_existing_card(auth_client: TestClient, session: Session):
    menu = create_menu(session, MenuData(name="raiz", selection_name="Raiz", message="Olá", is_root=True))

    for path in ("/menus", f"/menus/{menu.id}/card"):
        html = auth_client.get(path).text

        assert 'maxlength="20"' in tag_of(html, "selection_name")
        assert 'maxlength="991"' in tag_of(html, "message")


def test_the_limits_are_kept_on_the_rejected_form(auth_client: TestClient):
    html = auth_client.post("/menus", data={**FORM, "selection_name": "x" * 21}).text

    assert 'maxlength="20"' in tag_of(html, "selection_name")
    assert 'maxlength="991"' in tag_of(html, "message")


def test_a_title_over_the_limit_returns_422_and_refills_the_form(auth_client: TestClient, session: Session):
    response = auth_client.post("/menus", data={**FORM, "selection_name": "x" * 21, "message": "Corpo digitado"})

    assert response.status_code == 422
    assert "Texto de seleção pode ter no máximo 20 caracteres." in response.text
    assert f'value="{"x" * 21}"' in tag_of(response.text, "selection_name")
    assert "Corpo digitado" in response.text
    assert session.exec(select(Menu)).all() == []


def test_a_message_over_the_limit_returns_422(auth_client: TestClient, session: Session):
    response = auth_client.post("/menus", data={**FORM, "message": "m" * 992})

    assert response.status_code == 422
    assert "Mensagem pode ter no máximo 991 caracteres." in response.text
    assert session.exec(select(Menu)).all() == []


def test_a_title_at_the_limit_is_saved(auth_client: TestClient, session: Session):
    response = auth_client.post("/menus", data={**FORM, "selection_name": "x" * 20})

    assert response.status_code == 200
    assert [m.selection_name for m in session.exec(select(Menu)).all()] == ["x" * 20]


def test_a_message_typed_with_browser_line_breaks_counts_each_break_once(auth_client: TestClient, session: Session):
    typed = "\r\n".join(["a" * 98] * 10)

    response = auth_client.post("/menus", data={**FORM, "message": typed})

    assert response.status_code == 200
    saved = session.exec(select(Menu)).one()
    assert saved.message == "\n".join(["a" * 98] * 10)


def test_the_menu_list_is_ordered_by_internal_name(auth_client: TestClient, session: Session):
    for name in ("menu b", "Dúvidas", "Duvidas 2", "Menu A"):
        add(session, name)

    html = auth_client.get("/menus/lista").text

    names = re.findall(r"<strong>([^<]*)</strong>", html)
    assert names == ["Dúvidas", "Duvidas 2", "Menu A", "menu b"]


def test_the_menu_page_lists_menus_in_the_same_order(auth_client: TestClient, session: Session):
    for name in ("menu 10", "menu 2"):
        add(session, name)

    html = auth_client.get("/menus").text

    assert html.index("<strong>menu 2</strong>") < html.index("<strong>menu 10</strong>")


def test_the_parent_selector_is_ordered_by_internal_name(auth_client: TestClient, session: Session):
    for name in ("menu 10", "Ácido", "menu 2"):
        add(session, name)

    html = auth_client.get("/menus/novo/card").text

    options = re.findall(r'<option value="\d+"[^>]*>\s*([^<(]*?)\s*\(', html)
    assert options == ["Ácido", "menu 2", "menu 10"]
