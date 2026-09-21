from sqlmodel import SQLModel, Field, Relationship
from typing import Literal, Optional

from src.models.timestamp_model import TimestampModel


class UserBase(TimestampModel):
    login: str
    password: str
    is_admin: bool


class User(UserBase, table=True):
    __tablename__: Literal["users"] = "users"  # pyright: ignore[reportIncompatibleVariableOverride]

    id: int | None = Field(default=None, primary_key=True)
