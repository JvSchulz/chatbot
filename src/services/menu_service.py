from typing import Sequence

from sqlmodel import Session, select
from src.core.db import engine
from src.models.menu_model import Menu


def get_root_menus() -> Sequence[Menu]:
    with Session(engine) as session:
        return session.exec(select(Menu).where(Menu.parent_id == None)).all()


def get_submenus(parent_id: int) -> Sequence[Menu]:
    with Session(engine) as session:
        return session.exec(select(Menu).where(Menu.parent_id == parent_id)).all()
