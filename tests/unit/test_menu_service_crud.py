"""
Testes unitários para as operações de CRUD e regras hierárquicas de MenuService.
"""

import pytest
from sqlmodel import Session
from src.models.menu_model import Menu
from src.services.menu_service import (
    get_all_menus,
    get_root_menu,
    get_valid_parent_menus,
    can_delete_menu,
    create_menu,
    update_menu,
    delete_menu,
)


def test_get_all_menus_returns_ordered_list(session: Session):
    """
    get_all_menus deve retornar todos os menus cadastrados.
    """
    m1 = Menu(name="B Menu", selection_name="B", message="Msg B", parent_id=None)
    m2 = Menu(name="A Menu", selection_name="A", message="Msg A", parent_id=1)
    session.add(m1)
    session.add(m2)
    session.commit()

    menus = get_all_menus(session)
    assert len(menus) == 2
    assert menus[0].name == "A Menu"
    assert menus[1].name == "B Menu"


def test_get_root_menu_returns_single_root(session: Session):
    """
    get_root_menu deve retornar a instância raiz ou None.
    """
    assert get_root_menu(session) is None

    root = Menu(name="Raiz", selection_name="R", message="R", parent_id=None)
    session.add(root)
    session.commit()

    assert get_root_menu(session) is not None
    assert get_root_menu(session).name == "Raiz"  # type: ignore


def test_get_valid_parent_menus_without_exclusion_returns_all(session: Session):
    """
    get_valid_parent_menus sem exclusão deve retornar todos os menus existentes.
    """
    m1 = Menu(name="Menu 1", selection_name="1", message="Msg 1", parent_id=None)
    session.add(m1)
    session.commit()

    parents = get_valid_parent_menus(session, exclude_id=None)
    assert len(parents) == 1
    assert parents[0].id == m1.id


def test_get_valid_parent_menus_excludes_self_and_all_descendants(session: Session):
    """
    get_valid_parent_menus deve excluir o próprio menu e seus descendentes diretos e indiretos.
    Árvore: Root (1) -> Child (2) -> Grandchild (3); Unrelated (4)
    Ao editar Root (1), pais válidos só podem ser Unrelated (4) ou None.
    """
    root = Menu(name="Root", selection_name="R", message="R", parent_id=None)
    session.add(root)
    session.commit()
    session.refresh(root)

    child = Menu(name="Child", selection_name="C", message="C", parent_id=root.id)
    session.add(child)
    session.commit()
    session.refresh(child)

    grandchild = Menu(name="Grandchild", selection_name="GC", message="GC", parent_id=child.id)
    session.add(grandchild)
    session.commit()
    session.refresh(grandchild)

    unrelated = Menu(name="Unrelated", selection_name="U", message="U", parent_id=child.id)
    session.add(unrelated)
    session.commit()
    session.refresh(unrelated)

    valid_parents_for_child = get_valid_parent_menus(session, exclude_id=child.id)
    parent_ids = [m.id for m in valid_parents_for_child]

    assert child.id not in parent_ids
    assert grandchild.id not in parent_ids
    assert root.id in parent_ids


def test_can_delete_menu_checks_submenus_presence(session: Session):
    """
    can_delete_menu deve retornar True se o menu não tem submenus e False se tiver submenus.
    """
    parent = Menu(name="Pai", selection_name="P", message="P", parent_id=None)
    session.add(parent)
    session.commit()
    session.refresh(parent)

    assert can_delete_menu(session, parent.id) is True  # type: ignore

    child = Menu(name="Filho", selection_name="F", message="F", parent_id=parent.id)
    session.add(child)
    session.commit()

    assert can_delete_menu(session, parent.id) is False  # type: ignore
    assert can_delete_menu(session, child.id) is True  # type: ignore


def test_create_menu_as_root(session: Session):
    """
    create_menu com is_root=True deve persistir menu com parent_id nulo.
    """
    created = create_menu(
        session=session,
        name="Novo Menu",
        selection_name="Opção 1",
        message="Mensagem de teste",
        is_root=True,
    )
    assert created.id is not None
    assert created.parent_id is None
    assert created.name == "Novo Menu"


def test_create_second_root_menu_raises_value_error(session: Session):
    """
    create_menu com is_root=True quando já existe raiz deve falhar.
    """
    create_menu(session=session, name="Raiz 1", selection_name="R1", message="M1", is_root=True)

    with pytest.raises(ValueError, match="Já existe um menu raiz definido"):
        create_menu(session=session, name="Raiz 2", selection_name="R2", message="M2", is_root=True)


def test_create_child_menu_without_root_raises_value_error(session: Session):
    """
    create_menu com is_root=False em banco vazio deve falhar.
    """
    with pytest.raises(ValueError, match="Nenhum menu raiz está configurado"):
        create_menu(session=session, name="Sub", selection_name="S", message="M", is_root=False, parent_id=1)


def test_update_menu_modifies_fields(session: Session):
    """
    update_menu deve alterar os campos permitidos e persistir alterações.
    """
    root = create_menu(session=session, name="Antigo", selection_name="Old", message="Old msg", is_root=True)

    updated = update_menu(
        session=session,
        menu_id=root.id,  # type: ignore
        name="Atualizado",
        selection_name="New",
        message="New msg",
        is_root=True,
    )
    assert updated.name == "Atualizado"
    assert updated.message == "New msg"


def test_update_menu_raises_value_error_on_cycle(session: Session):
    """
    update_menu deve lançar ValueError se o parent_id for o próprio menu ou um descendente.
    """
    root = create_menu(session=session, name="Raiz", selection_name="R", message="R", is_root=True)
    child = create_menu(session=session, name="Filho", selection_name="F", message="F", is_root=False, parent_id=root.id)

    with pytest.raises(ValueError, match="Ciclo hierárquico detectado"):
        update_menu(
            session=session,
            menu_id=root.id,  # type: ignore
            name="Raiz",
            selection_name="R",
            message="R",
            parent_id=child.id,
            is_root=False,
        )


def test_delete_menu_deletes_when_safe(session: Session):
    """
    delete_menu deve excluir com sucesso caso não tenha submenus.
    """
    menu = create_menu(session=session, name="Folha", selection_name="F", message="F", is_root=True)

    assert delete_menu(session, menu.id) is True  # type: ignore
    assert session.get(Menu, menu.id) is None


def test_delete_menu_raises_value_error_when_has_submenus(session: Session):
    """
    delete_menu deve lançar ValueError ao tentar remover menu com filhos.
    """
    root = create_menu(session=session, name="Pai", selection_name="P", message="P", is_root=True)
    create_menu(session=session, name="Filho", selection_name="F", message="F", is_root=False, parent_id=root.id)

    with pytest.raises(ValueError, match="possui submenus vinculados"):
        delete_menu(session, root.id)  # type: ignore
