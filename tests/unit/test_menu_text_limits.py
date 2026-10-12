"""
Testes unitários dos limites de tamanho dos textos de menu impostos pela API do WhatsApp.
"""

import pytest
from sqlmodel import Session, select

from src.models.menu_model import Menu
from src.services.menu_service import (
    LEAF_SUFFIX,
    MAX_MESSAGE_LEN,
    MAX_SELECTION_NAME_LEN,
    MENU_FIELDS_REQUIRED_MESSAGE,
    MenuData,
    create_menu,
    update_menu,
)


def valid_data(**overrides) -> MenuData:
    fields = {"name": "Cursos", "selection_name": "Cursos", "message": "Escolha um curso", "is_root": True}
    return MenuData(**{**fields, **overrides})


def test_the_limits_come_from_meta():
    assert (MAX_SELECTION_NAME_LEN, MAX_MESSAGE_LEN) == (20, 991)


def test_the_leaf_suffix_fills_the_gap_to_the_body_limit():
    assert LEAF_SUFFIX == "\n\nDeseja realizar outra consulta?"
    assert MAX_MESSAGE_LEN + len(LEAF_SUFFIX) == 1024


def test_a_selection_name_at_the_limit_is_saved(session: Session):
    menu = create_menu(session, valid_data(selection_name="x" * 20))

    assert menu.selection_name == "x" * 20


def test_a_selection_name_over_the_limit_is_rejected_and_nothing_is_saved(session: Session):
    with pytest.raises(ValueError) as error:
        create_menu(session, valid_data(selection_name="x" * 21))

    assert str(error.value) == "Texto de seleção pode ter no máximo 20 caracteres."
    assert session.exec(select(Menu)).all() == []


def test_a_message_at_the_limit_is_saved(session: Session):
    menu = create_menu(session, valid_data(message="m" * 991))

    assert len(menu.message) == 991


def test_a_message_over_the_limit_is_rejected_and_nothing_is_saved(session: Session):
    with pytest.raises(ValueError) as error:
        create_menu(session, valid_data(message="m" * 992))

    assert str(error.value) == "Mensagem pode ter no máximo 991 caracteres."
    assert session.exec(select(Menu)).all() == []


def test_the_length_is_counted_after_trimming(session: Session):
    menu = create_menu(session, valid_data(selection_name="  " + "x" * 20 + "  ", message=" " + "m" * 991 + "\n"))

    assert (len(menu.selection_name), len(menu.message)) == (20, 991)


def test_trimming_does_not_hide_an_excess_character(session: Session):
    with pytest.raises(ValueError):
        create_menu(session, valid_data(selection_name=" " + "x" * 21 + " "))


def test_the_internal_name_has_no_limit(session: Session):
    menu = create_menu(session, valid_data(name="n" * 500))

    assert len(menu.name) == 500


def test_the_selection_name_is_reported_before_the_message(session: Session):
    with pytest.raises(ValueError) as error:
        create_menu(session, valid_data(selection_name="x" * 21, message="m" * 992))

    assert str(error.value).startswith("Texto de seleção")


def test_a_blank_field_is_reported_before_a_length(session: Session):
    with pytest.raises(ValueError) as error:
        create_menu(session, valid_data(name=" ", selection_name="x" * 21))

    assert str(error.value) == MENU_FIELDS_REQUIRED_MESSAGE


def test_update_rejects_an_over_long_selection_name_and_keeps_the_menu(session: Session):
    menu = create_menu(session, valid_data())

    with pytest.raises(ValueError) as error:
        update_menu(session, menu.id, valid_data(selection_name="x" * 21))  # type: ignore

    assert str(error.value) == "Texto de seleção pode ter no máximo 20 caracteres."
    session.refresh(menu)
    assert menu.selection_name == "Cursos"


def test_update_rejects_an_over_long_message_and_accepts_the_limit(session: Session):
    menu = create_menu(session, valid_data())

    with pytest.raises(ValueError):
        update_menu(session, menu.id, valid_data(message="m" * 992))  # type: ignore
    updated = update_menu(session, menu.id, valid_data(message="m" * 991))  # type: ignore

    assert len(updated.message) == 991
