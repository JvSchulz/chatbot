import math
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING
from sqlalchemy import desc, func
from sqlmodel import Session, col, select
from src.models.chat_history_model import ChatHistory
from src.models.menu_model import Menu

if TYPE_CHECKING:
    from src.services.webhook.message_handler import MessageContext

HISTORY_PAGE_SIZE = 50
NO_MENU_LABEL = "-"
USER_ROLE_LABEL = "Usuário"
BOT_ROLE_LABEL = "Bot"


@dataclass(frozen=True)
class HistoryRow:
    """
    Linha do histórico pronta para exibição no painel.

    Attributes:
        id: Identificador da linha no histórico.
        user_label: Telefone do usuário quando existe; senão, o BSUID.
        role_label: 'Usuário' para mensagens recebidas e 'Bot' para respostas enviadas.
        content: Texto da mensagem ou título da opção selecionada.
        menu_name: Nome do menu associado, ou '-' quando não há menu (ou ele foi excluído).
        created_at: Data e hora UTC do registro.
    """

    id: int
    user_label: str
    role_label: str
    content: str
    menu_name: str
    created_at: datetime


@dataclass(frozen=True)
class HistoryPage:
    """
    Uma página do histórico, da mensagem mais recente para a mais antiga.

    Attributes:
        rows: Linhas da página, no máximo HISTORY_PAGE_SIZE.
        page: Número da página exibida (1 é a mais recente), já ajustado ao intervalo válido.
        has_previous: Se existe uma página mais recente.
        has_next: Se existe uma página mais antiga.
    """

    rows: list[HistoryRow]
    page: int
    has_previous: bool
    has_next: bool


def list_history(session: Session, page: int) -> HistoryPage:
    """
    Lista o histórico de conversas, da mensagem mais recente para a mais antiga, em páginas fixas.

    Páginas fora do intervalo válido são ajustadas para a primeira ou a última página existente.

    Args:
        session: Sessão ativa do banco de dados.
        page: Número da página solicitada (a partir de 1).

    Returns:
        A página pedida (ou a mais próxima que exista) com rótulos prontos para exibição.
    """
    total = session.exec(select(func.count()).select_from(ChatHistory)).one()
    last_page = max(1, math.ceil(total / HISTORY_PAGE_SIZE))
    current = min(max(page, 1), last_page)

    statement = (
        select(ChatHistory, Menu.name)
        .join(Menu, col(ChatHistory.menu_id) == col(Menu.id), isouter=True)
        .order_by(desc(col(ChatHistory.created_at)), desc(col(ChatHistory.id)))
        .offset((current - 1) * HISTORY_PAGE_SIZE)
        .limit(HISTORY_PAGE_SIZE)
    )
    rows = [
        HistoryRow(
            id=record.id,  # type: ignore
            user_label=record.wa_id or record.user_id,
            role_label=USER_ROLE_LABEL if record.role == "user" else BOT_ROLE_LABEL,
            content=record.content,
            menu_name=menu_name or NO_MENU_LABEL,
            created_at=record.created_at,
        )
        for record, menu_name in session.exec(statement).all()
    ]
    return HistoryPage(rows=rows, page=current, has_previous=current > 1, has_next=current < last_page)


def save_user_log(context: "MessageContext", menu_id: int | None = None) -> None:
    """
    Registra no histórico uma interação recebida do usuário (texto, botão ou lista).

    O registro entra na transação do evento (context.session); quem chamou confirma o commit.

    Args:
        context: Contexto do evento; message_text é o texto digitado ou o título da opção.
        menu_id: Identificador opcional do menu selecionado nessa interação.
    """
    context.session.add(
        ChatHistory(
            user_id=context.user_id,
            wa_id=context.wa_id,
            role="user",
            content=context.message_text,
            menu_id=menu_id,
        )
    )


def save_bot_reply_log(context: "MessageContext", content: str, menu_id: int | None = None) -> None:
    """
    Registra no histórico uma resposta do chatbot enviada ao usuário.

    O registro entra na transação do evento (context.session); quem chamou confirma o commit.

    Args:
        context: Contexto do evento, que identifica o destinatário.
        content: Conteúdo textual da resposta entregue.
        menu_id: Identificador opcional do menu apresentado.
    """
    context.session.add(
        ChatHistory(
            user_id=context.user_id,
            role="bot",
            content=content,
            menu_id=menu_id,
        )
    )
