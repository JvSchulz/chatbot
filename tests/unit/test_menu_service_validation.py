"""
Testes unitários da validação e da normalização dos campos obrigatórios de menu.
"""

import pytest
from sqlmodel import Session, select

from src.models.menu_model import Menu
from src.services.menu_service import (
    MENU_FIELDS_REQUIRED_MESSAGE,
    MenuData,
    create_menu,
    update_menu,
)

BLANK_VALUES = ["", " ", "   ", "\t", "\n", " \t\n "]
REQUIRED_FIELDS = ["name", "selection_name", "message"]


def valid_data(**overrides) -> MenuData:
    """Monta dados válidos de uma raiz, com sobrescrita dos campos informados."""
    fields = {"name": "Cursos", "selection_name": "Cursos", "message": "Escolha um curso", "is_root": True}
    return MenuData(**{**fields, **overrides})


def test_required_message_text():
    assert MENU_FIELDS_REQUIRED_MESSAGE == "Preencha nome, texto de seleção e mensagem."


@pytest.mark.parametrize("field", REQUIRED_FIELDS)
@pytest.mark.parametrize("blank", BLANK_VALUES)
def test_create_menu_rejects_blank_required_fields(session: Session, field: str, blank: str):
    with pytest.raises(ValueError) as error:
        create_menu(session, data=valid_data(**{field: blank}))

    assert str(error.value) == MENU_FIELDS_REQUIRED_MESSAGE
    assert session.exec(select(Menu)).all() == []


@pytest.mark.parametrize("field", REQUIRED_FIELDS)
@pytest.mark.parametrize("blank", ["", "   "])
def test_update_menu_rejects_blank_required_fields(session: Session, field: str, blank: str):
    menu = create_menu(session, data=valid_data())

    with pytest.raises(ValueError) as error:
        update_menu(session, menu.id, data=valid_data(**{field: blank}))  # type: ignore

    assert str(error.value) == MENU_FIELDS_REQUIRED_MESSAGE
    session.refresh(menu)
    assert (menu.name, menu.selection_name, menu.message) == ("Cursos", "Cursos", "Escolha um curso")


def test_blank_fields_are_reported_before_the_root_rule(session: Session):
    create_menu(session, data=valid_data())

    with pytest.raises(ValueError) as error:
        create_menu(session, data=valid_data(selection_name=" "))

    assert str(error.value) == MENU_FIELDS_REQUIRED_MESSAGE


def test_create_menu_trims_surrounding_whitespace(session: Session):
    menu = create_menu(
        session, data=valid_data(name="  Cursos  ", selection_name="\tCursos de\n", message=" Olá \n")
    )

    assert (menu.name, menu.selection_name, menu.message) == ("Cursos", "Cursos de", "Olá")


def test_update_menu_trims_surrounding_whitespace(session: Session):
    menu = create_menu(session, data=valid_data())

    updated = update_menu(
        session, menu.id, data=valid_data(name="  Novo  ", selection_name=" Nova ", message="\nTexto ")  # type: ignore
    )

    assert (updated.name, updated.selection_name, updated.message) == ("Novo", "Nova", "Texto")


def test_inner_whitespace_and_single_characters_are_kept(session: Session):
    menu = create_menu(session, data=valid_data(name="a", selection_name="b  c", message="d\n\ne"))

    assert (menu.name, menu.selection_name, menu.message) == ("a", "b  c", "d\n\ne")
