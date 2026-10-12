"""
Testes de integração para o serviço de menus hierárquicos com banco SQLite em memória.
"""

from sqlmodel import Session
from src.models.menu_model import Menu
from src.services.menu_service import (
    build_menu_split_view_context,
    get_menu_by_id,
    get_root_menus,
    get_submenus,
)


def test_get_root_menus_returns_only_nodes_with_null_parent(session: Session):
    """
    get_root_menus deve retornar estritamente os nós cujo parent_id é nulo.
    """
    root_1 = Menu(name="Graduação", selection_name="Grad", message="Opções de graduação", parent_id=None)
    root_2 = Menu(name="Pós-Graduação", selection_name="Pós", message="Opções de pós", parent_id=None)
    child = Menu(name="Matrícula", selection_name="Matr", message="Matrícula grad", parent_id=1)

    session.add(root_1)
    session.add(root_2)
    session.add(child)
    session.commit()

    roots = get_root_menus(session)

    assert len(roots) == 2
    root_names = [m.name for m in roots]
    assert "Graduação" in root_names
    assert "Pós-Graduação" in root_names
    assert "Matrícula" not in root_names


def test_get_submenus_returns_only_direct_children(session: Session):
    """
    get_submenus deve retornar apenas os nós com parent_id correspondente ao menu solicitado.
    """
    root_1 = Menu(name="Menu A", selection_name="A", message="A", parent_id=None)
    root_2 = Menu(name="Menu B", selection_name="B", message="B", parent_id=None)
    session.add(root_1)
    session.add(root_2)
    session.commit()
    session.refresh(root_1)
    session.refresh(root_2)

    child_a1 = Menu(name="Sub A1", selection_name="A1", message="A1", parent_id=root_1.id)
    child_a2 = Menu(name="Sub A2", selection_name="A2", message="A2", parent_id=root_1.id)
    child_b1 = Menu(name="Sub B1", selection_name="B1", message="B1", parent_id=root_2.id)
    session.add(child_a1)
    session.add(child_a2)
    session.add(child_b1)
    session.commit()

    submenus_a = get_submenus(session, root_1.id)  # type: ignore
    assert len(submenus_a) == 2
    sub_names = [m.name for m in submenus_a]
    assert "Sub A1" in sub_names
    assert "Sub A2" in sub_names
    assert "Sub B1" not in sub_names


def test_get_menu_by_id_returns_correct_entity_or_none(session: Session):
    """
    get_menu_by_id deve recuperar o menu pelo ID ou None quando inexistente.
    """
    menu = Menu(name="Secretaria", selection_name="Sec", message="Atendimento da secretaria", parent_id=None)
    session.add(menu)
    session.commit()
    session.refresh(menu)

    found = get_menu_by_id(session, menu.id)  # type: ignore
    assert found is not None
    assert found.name == "Secretaria"

    not_found = get_menu_by_id(session, 99999)
    assert not_found is None


def _tree(session: Session) -> tuple[Menu, Menu]:
    root = Menu(name="menu_inicio", selection_name="Início", message="Bem-vindo")
    session.add(root)
    session.commit()
    child = Menu(name="Cursos", selection_name="Cursos", message="C", parent_id=root.id)
    session.add(child)
    session.commit()
    return root, child


def test_split_view_context_allows_toggling_root_only_on_the_root_itself(session: Session):
    root, child = _tree(session)

    on_root = build_menu_split_view_context(session, selected_id=root.id)
    on_child = build_menu_split_view_context(session, selected_id=child.id)

    assert on_root["can_toggle_root"] is True
    assert on_child["can_toggle_root"] is False


def test_split_view_context_allows_toggling_root_when_there_is_none(session: Session):
    assert build_menu_split_view_context(session)["can_toggle_root"] is True


def test_update_menu_rejects_a_second_root_with_the_create_message(session: Session):
    from src.services.menu_service import MenuData, update_menu
    import pytest

    _, child = _tree(session)

    with pytest.raises(ValueError, match="Já existe um menu raiz definido"):
        update_menu(session, child.id, MenuData(name="Cursos", selection_name="Cursos", message="C", is_root=True))  # type: ignore


def test_get_root_children_returns_only_direct_children_of_the_root(session: Session):
    from src.services.menu_service import get_root_children

    root, child = _tree(session)
    grandchild = Menu(name="Eng", selection_name="Eng", message="E", parent_id=child.id)
    session.add(grandchild)
    session.commit()

    assert [m.name for m in get_root_children(session)] == ["Cursos"]


def test_get_root_children_is_empty_without_a_root(session: Session):
    from src.services.menu_service import get_root_children

    assert get_root_children(session) == []


def test_get_root_menu_is_the_parentless_menu_with_the_lowest_id(session: Session):
    from src.services.menu_service import get_root_menu

    for menu_id in (5, 2, 9):
        session.add(Menu(id=menu_id, name=f"raiz {menu_id}", selection_name="R", message="M"))
    session.commit()

    root = get_root_menu(session)

    assert root is not None and root.id == 2


def test_get_root_menu_ignores_menus_with_a_parent(session: Session):
    from src.services.menu_service import get_root_menu

    session.add(Menu(id=1, name="pai", selection_name="P", message="M", parent_id=None))
    session.add(Menu(id=2, name="filho", selection_name="F", message="M", parent_id=1))
    session.commit()

    root = get_root_menu(session)

    assert root is not None and root.id == 1
