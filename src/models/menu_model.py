from typing import Literal, Optional
from sqlmodel import SQLModel, Field, Relationship

from src.models.timestamp_model import TimestampModel


# 1. Base: Shared fields between forms, APIs, and DB
class MenuBase(TimestampModel):
    name: str
    selection_name: str
    message: str
    parent_id: int | None = Field(default=None, foreign_key="menus.id")


class Menu(MenuBase, table=True):
    __tablename__: Literal["menus"] = "menus"  # pyright: ignore[reportIncompatibleVariableOverride]

    id: int | None = Field(default=None, primary_key=True)
    parent_menu: Optional["Menu"] = Relationship(
        back_populates="submenus", sa_relationship_kwargs={"remote_side": "Menu.id"}
    )
    submenus: list["Menu"] = Relationship(back_populates="parent_menu")
