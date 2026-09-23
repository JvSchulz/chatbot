"""
Testes de integração para histórico de mensagens e detecção de primeira interação.
"""

from unittest.mock import MagicMock
from sqlmodel import Session, select
from pywa.types import Message
from pywa.types.base_update import User
from src.models.chat_history_model import ChatHistory
from src.services.webhook.chat_history_log import (
    is_first_interaction,
    save_message_log,
    save_bot_reply_log,
)


def test_is_first_interaction_on_empty_and_populated_database(session: Session):
    """
    is_first_interaction deve retornar True em banco vazio e False após haver registros do remetente.
    """
    wa_id = "5547998765432"

    # 1. Banco vazio para este remetente
    assert is_first_interaction(wa_id) is True

    # 2. Insere registro de mensagem
    msg = MagicMock(spec=Message)
    user = MagicMock(spec=User)
    user.wa_id = wa_id
    user.name = "Teste"
    msg.from_user = user
    msg.text = "Primeiro contato"

    save_message_log(msg=msg)

    # 3. Agora não é mais primeira interação
    assert is_first_interaction(wa_id) is False


def test_save_message_log_persists_inbound_user_role(session: Session):
    """
    save_message_log deve persistir mensagem do usuário com role='user'.
    """
    msg = MagicMock(spec=Message)
    user = MagicMock(spec=User)
    user.wa_id = "554711112222"
    user.name = "Roberto"
    msg.from_user = user
    msg.text = "Quero saber sobre pós"

    save_message_log(msg=msg, accessed_menu_id=2)

    statement = select(ChatHistory).where(ChatHistory.sender_id == "554711112222")
    record = session.exec(statement).first()

    assert record is not None
    assert record.sender_id == "554711112222"
    assert record.content == "Quero saber sobre pós"
    assert record.acessed_menu == 2
    assert record.role == "user"
    assert record.datetime is not None


def test_save_bot_reply_log_persists_bot_role(session: Session):
    """
    save_bot_reply_log deve persistir resposta do sistema com role='bot'.
    """
    save_bot_reply_log(
        recipient_id="554711112222",
        content="Aqui estão as opções de pós-graduação:",
        accessed_menu_id=2,
    )

    statement = select(ChatHistory).where(
        ChatHistory.sender_id == "554711112222",
        ChatHistory.role == "bot",
    )
    record = session.exec(statement).first()

    assert record is not None
    assert record.sender_id == "554711112222"
    assert record.content == "Aqui estão as opções de pós-graduação:"
    assert record.role == "bot"
    assert record.acessed_menu == 2
