from typing import Sequence, Any
from dataclasses import dataclass
from sqlmodel import Session, select
from src.core.db import engine
from src.models.menu_model import Menu


@dataclass
class MenuData:
    """Objeto de parâmetros para criação e atualização de nós de menu."""
    name: str
    selection_name: str
    message: str
    parent_id: int | None = None
    is_root: bool = False


def get_all_menus(session: Session | None = None) -> Sequence[Menu]:
    """
    Retorna todos os menus ordenados alfabeticamente pelo nome.

    Args:
        session: Sessão do banco de dados (opcional).

    Returns:
        Sequência de todos os menus cadastrados.
    """
    if session is not None:
        return session.exec(select(Menu).order_by(Menu.name)).all()  # type: ignore
    with Session(engine) as s:
        return s.exec(select(Menu).order_by(Menu.name)).all()  # type: ignore


def get_root_menus(session: Session | None = None) -> Sequence[Menu]:
    """
    Retorna todos os menus de nível raiz (onde parent_id é nulo).

    Args:
        session: Sessão do banco de dados (opcional).

    Returns:
        Sequência de instâncias de Menu raiz.
    """
    if session is not None:
        return session.exec(select(Menu).where(Menu.parent_id == None)).all()
    with Session(engine) as s:
        return s.exec(select(Menu).where(Menu.parent_id == None)).all()


def get_root_menu(session: Session | None = None) -> Menu | None:
    """
    Retorna o único menu raiz ativo do sistema.

    Args:
        session: Sessão do banco de dados (opcional).

    Returns:
        Instância de Menu raiz ou None se nenhum estiver configurado.
    """
    roots = get_root_menus(session)
    return roots[0] if roots else None


def get_submenus(parent_id: int, session: Session | None = None) -> Sequence[Menu]:
    """
    Retorna todos os submenus vinculados a um determinado menu pai.

    Args:
        parent_id: Identificador do menu pai.
        session: Sessão do banco de dados (opcional).

    Returns:
        Sequência de submenus vinculados.
    """
    if session is not None:
        return session.exec(select(Menu).where(Menu.parent_id == parent_id)).all()
    with Session(engine) as s:
        return s.exec(select(Menu).where(Menu.parent_id == parent_id)).all()


def get_menu_by_id(menu_id: int, session: Session | None = None) -> Menu | None:
    """
    Busca um registro de menu pelo seu identificador primário.

    Args:
        menu_id: Identificador numérico do menu no banco de dados.
        session: Sessão do banco de dados (opcional).

    Returns:
        Instância de Menu encontrada ou None caso não exista.
    """
    if session is not None:
        return session.get(Menu, menu_id)
    with Session(engine) as s:
        return s.get(Menu, menu_id)


def get_valid_parent_menus(
    session: Session,
    exclude_id: int | None = None,
) -> Sequence[Menu]:
    """
    Retorna lista de menus elegíveis a serem pais, prevenindo ciclos hierárquicos.

    Args:
        session: Sessão ativa do banco de dados.
        exclude_id: Identificador do menu sendo editado (exclui ele e seus descendentes).

    Returns:
        Sequência de menus que podem atuar como pai sem gerar ciclos.
    """
    all_menus = session.exec(select(Menu).order_by(Menu.name)).all()  # type: ignore
    if exclude_id is None:
        return all_menus

    excluded_ids = _collect_descendant_ids(all_menus, exclude_id)
    valid = [m for m in all_menus if m.id not in excluded_ids]
    if not valid:
        return [m for m in all_menus if m.id != exclude_id]
    return valid


def build_menu_split_view_context(
    session: Session,
    selected_id: int | None = None,
) -> dict[str, Any]:
    """
    Constrói o dicionário de contexto para a visualização split-view de menus.

    Args:
        session: Sessão ativa do banco de dados.
        selected_id: Identificador opcional do menu a ser exibido selecionado.

    Returns:
        Dicionário com menus, menu selecionado, menu raiz e flags de validação de raiz.
    """
    all_menus = get_all_menus(session)
    root_menu = get_root_menu(session)
    has_root = root_menu is not None

    if selected_id is not None:
        selected_menu = get_menu_by_id(selected_id, session)
    else:
        selected_menu = root_menu or (all_menus[0] if all_menus else None)

    is_current_root = selected_menu is not None and selected_menu.parent_id is None
    can_toggle_root = (not has_root) or is_current_root
    valid_parents = get_valid_parent_menus(session, selected_menu.id if selected_menu else None)

    return {
        "menus": all_menus,
        "selected_menu": selected_menu,
        "root_menu": root_menu,
        "has_root": has_root,
        "is_current_root": is_current_root,
        "can_toggle_root": can_toggle_root,
        "valid_parents": valid_parents,
    }



def can_delete_menu(session: Session, menu_id: int) -> bool:
    """
    Verifica se um menu pode ser excluído com segurança (sem submenus vinculados).

    Args:
        session: Sessão ativa do banco de dados.
        menu_id: Identificador do menu a verificar.

    Returns:
        True se o menu não possuir submenus; False caso possua filhos.
    """
    submenus = session.exec(select(Menu).where(Menu.parent_id == menu_id)).all()
    return len(submenus) == 0


def create_menu(
    session: Session,
    data: MenuData | None = None,
    **kwargs,
) -> Menu:
    """
    Persiste um novo nó de menu no banco de dados com validação de raiz única.

    Args:
        session: Sessão ativa do banco de dados.
        data: Dados estruturados do menu a criar.

    Returns:
        Instância do menu persistido com ID gerado.

    Raises:
        ValueError: Caso se tente criar um segundo menu raiz ou um submenu sem pai ou sem raiz.
    """
    menu_data = data or MenuData(
        name=kwargs.get("name", "Novo Menu"),
        selection_name=kwargs.get("selection_name", "Opção"),
        message=kwargs.get("message", ""),
        parent_id=kwargs.get("parent_id"),
        is_root=kwargs.get("is_root", kwargs.get("parent_id") is None),
    )

    existing_root = get_root_menu(session)

    if menu_data.is_root:
        if existing_root is not None:
            raise ValueError(f"Já existe um menu raiz definido ('{existing_root.name}'). Não é permitido ter mais de um menu raiz.")
        target_parent_id = None
    else:
        if existing_root is None:
            raise ValueError("Nenhum menu raiz está configurado. O menu deve ser definido como raiz.")
        if menu_data.parent_id is None:
            raise ValueError("Um submenu deve ter um menu pai selecionado.")
        target_parent_id = menu_data.parent_id

    new_menu = Menu(
        name=menu_data.name,
        selection_name=menu_data.selection_name,
        message=menu_data.message,
        parent_id=target_parent_id,
    )
    session.add(new_menu)
    session.commit()
    session.refresh(new_menu)
    return new_menu


def update_menu(
    session: Session,
    menu_id: int,
    data: MenuData | None = None,
    **kwargs,
) -> Menu:
    """
    Atualiza as propriedades de um menu existente com proteção contra ciclos e raiz única.

    Args:
        session: Sessão ativa do banco de dados.
        menu_id: Identificador do menu a ser atualizado.
        data: Novos dados estruturados para o menu.

    Returns:
        Instância do menu atualizado.

    Raises:
        ValueError: Caso o menu não exista, tente violar raiz única ou gere ciclo hierárquico.
    """
    menu = session.get(Menu, menu_id)
    if not menu:
        raise ValueError(f"Menu com ID {menu_id} não encontrado.")

    is_root_inferred = kwargs.get("is_root", kwargs.get("parent_id") is None if "parent_id" in kwargs else menu.parent_id is None)
    menu_data = data or MenuData(
        name=kwargs.get("name", menu.name),
        selection_name=kwargs.get("selection_name", menu.selection_name),
        message=kwargs.get("message", menu.message),
        parent_id=kwargs.get("parent_id", menu.parent_id),
        is_root=is_root_inferred,
    )

    existing_root = get_root_menu(session)

    if menu_data.is_root:
        if existing_root is not None and existing_root.id != menu_id:
            raise ValueError(f"Já existe outro menu definido como raiz ('{existing_root.name}'). Desmarque o atual antes de definir este como raiz.")
        target_parent_id = None
    else:
        if menu_data.parent_id is None and existing_root is not None and existing_root.id != menu_id:
            raise ValueError("Selecione um menu pai para este submenu.")
        target_parent_id = menu_data.parent_id

    if target_parent_id is not None:
        all_menus = session.exec(select(Menu)).all()
        invalid_parent_ids = _collect_descendant_ids(all_menus, menu_id)
        if target_parent_id in invalid_parent_ids:
            raise ValueError("Ciclo hierárquico detectado: um menu não pode ser filho de si mesmo ou de seus descendentes.")

    menu.name = menu_data.name
    menu.selection_name = menu_data.selection_name
    menu.message = menu_data.message
    menu.parent_id = target_parent_id

    session.add(menu)
    session.commit()
    session.refresh(menu)
    return menu


def delete_menu(session: Session, menu_id: int) -> bool:
    """
    Remove um menu do banco de dados se não possuir submenus vinculados.

    Args:
        session: Sessão ativa do banco de dados.
        menu_id: Identificador do menu a remover.

    Returns:
        True indicando sucesso da remoção.

    Raises:
        ValueError: Se o menu possuir submenus vinculados ou não for encontrado.
    """
    menu = session.get(Menu, menu_id)
    if not menu:
        raise ValueError(f"Menu com ID {menu_id} não encontrado.")

    if not can_delete_menu(session, menu_id):
        raise ValueError("Não é possível excluir um menu que possui submenus vinculados.")

    session.delete(menu)
    session.commit()
    return True


def _collect_descendant_ids(all_menus: Sequence[Menu], root_id: int) -> set[int]:
    """
    Coleta recursivamente os IDs do nó raiz e de todos os seus descendentes.

    Args:
        all_menus: Sequência completa de menus no banco.
        root_id: Identificador do menu base.

    Returns:
        Conjunto contendo o ID base e todos os IDs descendentes.
    """
    descendants: set[int] = {root_id}
    queue = [root_id]
    while queue:
        current_id = queue.pop(0)
        for m in all_menus:
            if m.parent_id == current_id and m.id is not None and m.id not in descendants:
                descendants.add(m.id)
                queue.append(m.id)
    return descendants
