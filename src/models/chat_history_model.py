from datetime import datetime
from typing import Literal
from sqlmodel import Field

from src.models.timestamp_model import TimestampModel


class ChatHistoryBase(TimestampModel):
    """
    Estrutura base para o histórico de conversas do chatbot.

    Attributes:
        sender_id: Identificador WhatsApp do usuário ou destinatário.
        role: Papel da mensagem ('user' para mensagens recebidas, 'bot' para respostas enviadas).
        content: Conteúdo textual da mensagem.
        acessed_menu: Identificador do menu acessado nessa mensagem, se houver.
        datetime: Carimbo de data/hora em que a mensagem ocorreu.
    """

    sender_id: str
    role: str = Field(default="user")
    content: str
    acessed_menu: int | None = Field(default=None, foreign_key="menus.id")
    datetime: datetime


class ChatHistory(ChatHistoryBase, table=True):
    """Tabela de histórico de conversas e mensagens."""

    __tablename__: Literal["chat_histories"] = "chat_histories"  # pyright: ignore[reportIncompatibleVariableOverride]

    id: int | None = Field(default=None, primary_key=True)
