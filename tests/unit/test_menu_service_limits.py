"""
Testes unitários do limite de opções por lista do WhatsApp aplicado ao cadastro de menus.
"""

import pytest
from sqlmodel import Session, select

from src.models.menu_model import Menu
from src.services.menu_service import (
    WHATSAPP_LIST_LIMIT_MESSAGE,
    MenuData,
    create_menu,
    update_menu,
)

ROOT_CHILDREN_LIMIT = 9
SUBMENU_CHILDREN_LIMIT = 10


def add_root(session: Session) -> Menu:
    return create_menu(session, MenuData(name="raiz", selection_name="R", message="M", is_root=True))


def add_child(session: Session, parent: Menu, index: int) -> Menu:
    data = MenuData(name=f"filho {index}", selection_name=f"F{index}", message="M", parent_id=parent.id)
    return create_menu(session, data)


def fill(session: Session, parent: Menu, count: int) -> list[Menu]:
    return [add_child(session, parent, index) for index in range(count)]


def test_limit_message_text():
    assert WHATSAPP_LIST_LIMIT_MESSAGE == "O WhatsApp permite no máximo 10 opções por lista."


def test_root_accepts_its_ninth_child(session: Session):
    root = add_root(session)
    fill(session, root, ROOT_CHILDREN_LIMIT - 1)

    ninth = add_child(session, root, 99)

    assert ninth.parent_id == root.id
    assert len(session.exec(select(Menu).where(Menu.parent_id == root.id)).all()) == ROOT_CHILDREN_LIMIT


def test_root_rejects_a_tenth_child_and_saves_nothing(session: Session):
    root = add_root(session)
    fill(session, root, ROOT_CHILDREN_LIMIT)

    with pytest.raises(ValueError) as error:
        add_child(session, root, 99)

    assert str(error.value) == WHATSAPP_LIST_LIMIT_MESSAGE
    assert len(session.exec(select(Menu)).all()) == ROOT_CHILDREN_LIMIT + 1


def test_submenu_accepts_its_tenth_child(session: Session):
    root = add_root(session)
    parent = add_child(session, root, 0)
    fill(session, parent, SUBMENU_CHILDREN_LIMIT - 1)

    tenth = add_child(session, parent, 99)

    assert tenth.parent_id == parent.id


def test_submenu_rejects_an_eleventh_child(session: Session):
    root = add_root(session)
    parent = add_child(session, root, 0)
    fill(session, parent, SUBMENU_CHILDREN_LIMIT)

    with pytest.raises(ValueError) as error:
        add_child(session, parent, 99)

    assert str(error.value) == WHATSAPP_LIST_LIMIT_MESSAGE


def test_children_of_other_parents_do_not_count(session: Session):
    root = add_root(session)
    parent = add_child(session, root, 0)
    fill(session, parent, SUBMENU_CHILDREN_LIMIT)
    sibling = add_child(session, root, 1)

    added = add_child(session, sibling, 99)

    assert added.parent_id == sibling.id


def test_moving_a_menu_under_a_full_root_is_rejected(session: Session):
    root = add_root(session)
    fill(session, root, ROOT_CHILDREN_LIMIT)
    intermediate = session.exec(select(Menu).where(Menu.parent_id == root.id)).first()
    assert intermediate is not None
    leaf = add_child(session, intermediate, 50)

    with pytest.raises(ValueError) as error:
        update_menu(session, leaf.id, MenuData(name="a", selection_name="a", message="a", parent_id=root.id))  # type: ignore

    assert str(error.value) == WHATSAPP_LIST_LIMIT_MESSAGE
    session.refresh(leaf)
    assert leaf.parent_id == intermediate.id


def test_moving_a_menu_under_a_full_submenu_is_rejected(session: Session):
    root = add_root(session)
    full = add_child(session, root, 0)
    fill(session, full, SUBMENU_CHILDREN_LIMIT)
    other = add_child(session, root, 1)

    with pytest.raises(ValueError) as error:
        update_menu(session, other.id, MenuData(name="a", selection_name="a", message="a", parent_id=full.id))  # type: ignore

    assert str(error.value) == WHATSAPP_LIST_LIMIT_MESSAGE


def test_moving_a_menu_to_a_parent_with_room_is_allowed(session: Session):
    root = add_root(session)
    target = add_child(session, root, 0)
    fill(session, target, SUBMENU_CHILDREN_LIMIT - 1)
    mover = add_child(session, root, 1)

    moved = update_menu(session, mover.id, MenuData(name="a", selection_name="a", message="a", parent_id=target.id))  # type: ignore

    assert moved.parent_id == target.id


def test_editing_a_menu_that_stays_under_a_full_parent_is_allowed(session: Session):
    root = add_root(session)
    children = fill(session, root, ROOT_CHILDREN_LIMIT)

    edited = update_menu(
        session, children[0].id, MenuData(name="novo nome", selection_name="N", message="M", parent_id=root.id)  # type: ignore
    )

    assert edited.name == "novo nome"


def test_editing_a_menu_under_a_parent_already_over_the_limit_is_allowed(session: Session):
    root = add_root(session)
    fill(session, root, ROOT_CHILDREN_LIMIT)
    session.add(Menu(name="legado", selection_name="L", message="M", parent_id=root.id))
    session.commit()
    legacy = session.exec(select(Menu).where(Menu.name == "legado")).one()

    edited = update_menu(
        session, legacy.id, MenuData(name="legado 2", selection_name="L", message="M", parent_id=root.id)  # type: ignore
    )

    assert edited.name == "legado 2"


def test_creating_the_root_is_not_limited(session: Session):
    root = add_root(session)

    assert root.parent_id is None
