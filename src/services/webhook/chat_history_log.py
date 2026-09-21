from datetime import datetime, timezone
from pywa.types.message import Message
from sqlmodel import Session, select
from src.core.db import engine
from src.models.chat_history_model import ChatHistory


def is_first_interaction(sender_id: str) -> bool:
    """
    Verifica se o remetente possui interações anteriores no histórico de conversas.

    Args:
        sender_id: Identificador único do remetente (wa_id).

    Returns:
        True se não houver registros prévios do remetente, False caso contrário.
    """
    with Session(engine) as session:
        statement = select(ChatHistory).where(ChatHistory.sender_id == sender_id)
        first_record = session.exec(statement).first()
        return first_record is None


def save_message_log(msg: Message, accessed_menu_id: int | None = None) -> None:
    """
    Registra uma interação de mensagem no histórico do banco de dados.

    Args:
        msg: Mensagem recebida do usuário via WhatsApp.
        accessed_menu_id: Identificador opcional do menu acessado nessa interação.
    """
    sender_id: str = str(msg.from_user.wa_id or "")
    content: str = msg.text or ""

    record = ChatHistory(
        sender_id=sender_id,
        content=content,
        acessed_menu=accessed_menu_id,
        datetime=datetime.now(timezone.utc),
    )
    with Session(engine) as session:
        session.add(record)
        session.commit()
        session.refresh(record)
