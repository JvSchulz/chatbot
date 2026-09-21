from typing import Sequence

from sqlmodel import Session, select
from src.core.db import engine
from src.models.menu_model import Menu


def get_root_menus() -> Sequence[Menu]:
    """
    Retorna todos os menus de nível raiz (onde parent_id é nulo).

    Returns:
        Sequência de instâncias de Menu raiz.
    """
    with Session(engine) as session:
        return session.exec(select(Menu).where(Menu.parent_id == None)).all()


def get_submenus(parent_id: int) -> Sequence[Menu]:
    """
    Retorna todos os submenus vinculados a um determinado menu pai.

    Args:
        parent_id: Identificador do menu pai.

    Returns:
        Sequência de submenus vinculados.
    """
    with Session(engine) as session:
        return session.exec(select(Menu).where(Menu.parent_id == parent_id)).all()


def get_menu_by_id(menu_id: int) -> Menu | None:
    """
    Busca um registro de menu pelo seu identificador primário.

    Args:
        menu_id: Identificador numérico do menu no banco de dados.

    Returns:
        Instância de Menu encontrada ou None caso não exista.
    """
    with Session(engine) as session:
        return session.get(Menu, menu_id)
