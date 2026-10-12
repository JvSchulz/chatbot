"""
Testes unitários das mensagens de erro exatas e do contexto da tela de menus.
"""

import pytest
from sqlmodel import Session, select

from src.models.menu_model import Menu
from src.services.menu_service import (
    MenuData,
    build_menu_split_view_context,
    can_delete_menu,
    create_menu,
    delete_menu,
    get_valid_parent_menus,
    update_menu,
)


def add(session: Session, name: str, parent_id: int | None = None) -> Menu:
    menu = Menu(name=name, selection_name=name, message="M", parent_id=parent_id)
    session.add(menu)
    session.commit()
    session.refresh(menu)
    return menu


def data(**overrides) -> MenuData:
    fields = {"name": "n", "selection_name": "s", "message": "m"}
    return MenuData(**{**fields, **overrides})


def test_create_without_a_root_says_the_menu_must_be_the_root(session: Session):
    with pytest.raises(ValueError) as error:
        create_menu(session, data(parent_id=1))

    assert str(error.value) == "Nenhum menu raiz está configurado. O menu deve ser definido como raiz."


def test_create_a_submenu_without_a_parent_asks_for_one(session: Session):
    add(session, "raiz")

    with pytest.raises(ValueError) as error:
        create_menu(session, data(parent_id=None))

    assert str(error.value) == "Um submenu deve ter um menu pai selecionado."


def test_update_a_missing_menu_names_the_id(session: Session):
    with pytest.raises(ValueError) as error:
        update_menu(session, 42, data())

    assert str(error.value) == "Menu com ID 42 não encontrado."


def test_update_a_child_without_a_parent_asks_for_one(session: Session):
    root = add(session, "raiz")
    child = add(session, "filho", root.id)

    with pytest.raises(ValueError) as error:
        update_menu(session, child.id, data(parent_id=None))  # type: ignore

    assert str(error.value) == "Selecione um menu pai para este submenu."


def test_update_the_root_without_a_parent_and_without_root_flag_keeps_it_parentless(session: Session):
    root = add(session, "raiz")

    updated = update_menu(session, root.id, data(parent_id=None, is_root=False))  # type: ignore

    assert updated.parent_id is None


def test_update_into_a_cycle_names_the_rule(session: Session):
    root = add(session, "raiz")
    child = add(session, "filho", root.id)

    with pytest.raises(ValueError) as error:
        update_menu(session, root.id, data(parent_id=child.id))  # type: ignore

    assert str(error.value) == "Ciclo hierárquico detectado: um menu não pode ser filho de si mesmo ou de seus descendentes."


def test_delete_a_missing_menu_names_the_id(session: Session):
    with pytest.raises(ValueError) as error:
        delete_menu(session, 7)

    assert str(error.value) == "Menu com ID 7 não encontrado."


def test_delete_a_menu_with_children_is_blocked_with_the_exact_message(session: Session):
    root = add(session, "raiz")
    add(session, "filho", root.id)

    with pytest.raises(ValueError) as error:
        delete_menu(session, root.id)  # type: ignore

    assert str(error.value) == "Não é possível excluir um menu que possui submenus vinculados."


def test_can_delete_menu_is_false_only_when_the_menu_has_children(session: Session):
    root = add(session, "raiz")
    leaf = add(session, "folha", root.id)

    assert (can_delete_menu(session, root.id), can_delete_menu(session, leaf.id)) == (False, True)  # type: ignore


def test_valid_parents_are_ordered_by_name(session: Session):
    add(session, "c")
    add(session, "a")
    add(session, "b")

    assert [menu.name for menu in get_valid_parent_menus(session)] == ["a", "b", "c"]


def test_valid_parents_of_a_lone_menu_are_empty_of_itself(session: Session):
    lone = add(session, "sozinho")

    assert get_valid_parent_menus(session, lone.id) == []


def test_valid_parents_fall_back_to_menus_other_than_the_excluded_one(session: Session):
    root = add(session, "raiz")
    add(session, "filho", root.id)

    child = session.exec(select(Menu).where(Menu.parent_id == root.id)).one()

    valid = get_valid_parent_menus(session, root.id)

    assert [menu.id for menu in valid] == [child.id]


def test_split_view_context_without_a_selection_shows_the_root(session: Session):
    root = add(session, "raiz")
    add(session, "a-filho", root.id)

    context = build_menu_split_view_context(session)

    assert context["selected_menu"].id == root.id
    assert context["root_menu"].id == root.id
    assert context["has_root"] is True
    assert context["is_current_root"] is True
    assert context["can_toggle_root"] is True


def test_split_view_context_without_a_root_shows_the_first_menu_by_name(session: Session):
    first = add(session, "b")
    second = add(session, "a", first.id)
    first.parent_id = second.id
    session.add(first)
    session.commit()

    context = build_menu_split_view_context(session)

    assert context["has_root"] is False
    assert context["root_menu"] is None
    assert context["selected_menu"].id == second.id
    assert (context["is_current_root"], context["can_toggle_root"]) == (False, True)


def test_split_view_context_with_no_menus_drafts_the_first_root(session: Session):
    context = build_menu_split_view_context(session)

    assert context == {
        "menus": [],
        "selected_menu": None,
        "root_menu": None,
        "has_root": False,
        "is_current_root": True,
        "can_toggle_root": True,
        "valid_parents": [],
        "limits": {"selection_name": 20, "message": 991},
    }


def test_split_view_context_valid_parents_exclude_the_selection_and_its_descendants(session: Session):
    root = add(session, "raiz")
    child = add(session, "filho", root.id)
    other = add(session, "outro", root.id)

    context = build_menu_split_view_context(session, selected_id=child.id)  # type: ignore

    assert [menu.id for menu in context["valid_parents"]] == [other.id, root.id]
    assert context["selected_menu"].id == child.id
    assert (context["is_current_root"], context["can_toggle_root"]) == (False, False)
