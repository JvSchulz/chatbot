from typing import Literal
from sqlmodel import Field

from src.models.timestamp_model import TimestampModel


class ChatHistoryBase(TimestampModel):
    """
    Estrutura base para o histórico de conversas do chatbot.

    Attributes:
        user_id: Identificador BSUID do usuário (chave estável, presente mesmo sem telefone).
        wa_id: Telefone do usuário quando disponível (ausente para usuários com nome de usuário).
        role: Papel da mensagem ('user' para mensagens recebidas, 'bot' para respostas enviadas).
        content: Conteúdo textual da mensagem ou título da opção selecionada.
        menu_id: Identificador do menu associado à mensagem, se houver (nulo se o menu for excluído).
    """

    user_id: str = Field(index=True)
    wa_id: str | None = Field(default=None)
    role: str = Field(default="user")
    content: str
    menu_id: int | None = Field(default=None, foreign_key="menus.id", ondelete="SET NULL")


class ChatHistory(ChatHistoryBase, table=True):
    """Tabela de histórico de conversas e mensagens."""

    __tablename__: Literal["chat_histories"] = "chat_histories"  # pyright: ignore[reportIncompatibleVariableOverride]

    id: int | None = Field(default=None, primary_key=True)
