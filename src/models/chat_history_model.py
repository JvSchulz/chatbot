from datetime import datetime
from typing import Literal
from sqlmodel import Field

from src.models.timestamp_model import TimestampModel


class ChatHistoryBase(TimestampModel):
    sender_id: str
    content: str
    acessed_menu: int | None = Field(foreign_key="menus.id")
    datetime: datetime


class ChatHistory(ChatHistoryBase, table=True):
    __tablename__: Literal["chat_histories"] = "chat_histories"  # pyright: ignore[reportIncompatibleVariableOverride]

    id: int | None = Field(default=None, primary_key=True)
