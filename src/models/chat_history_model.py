from sqlite3.dbapi2 import Timestamp

from sqlmodel import Field
from typing import Literal

from src.models.timestamp_model import TimestampModel


class ChatHistoryBase(TimestampModel):
    sender_id: str
    content: str
    acessed_menu: int | None = Field(foreign_key="menus.id")
    datetime: Timestamp


class ChatHistory(ChatHistoryBase, table=True):
    __tablename__: Literal["chat_histories"] = "chat_histories"

    id: int | None = Field(default=None, primary_key=True)
