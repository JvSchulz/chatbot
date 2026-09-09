from sqlite3.dbapi2 import Timestamp

from sqlalchemy import ForeignKey
from sqlmodel import SQLModel, Field, Relationship
from typing import Literal, Optional

from src.models.timestamp_model import TimestampModel


# 1. Base: Shared fields between forms, APIs, and DB
class ChatHistoryBase(TimestampModel):
    sender_id: str
    content: str
    accessed_menu: int | None = Field(foreign_key="menus.id")
    datetime: Timestamp


class ChatHistory(ChatHistoryBase, table=True):
    __tablename__: Literal["chat_histories"] = "chat_histories"

    id: int | None = Field(default=None, primary_key=True)
