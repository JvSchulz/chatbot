"""
Testes de integração para o serviço de menus hierárquicos com banco SQLite em memória.
"""

from sqlmodel import Session
from src.models.menu_model import Menu
from src.services.menu_service import get_root_menus, get_submenus, get_menu_by_id


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

    roots = get_root_menus()

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

    submenus_a = get_submenus(parent_id=root_1.id)  # type: ignore
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

    found = get_menu_by_id(menu.id)  # type: ignore
    assert found is not None
    assert found.name == "Secretaria"

    not_found = get_menu_by_id(99999)
    assert not_found is None
