"""
Testes unitários para extração e normalização de contexto de mensagens WhatsApp.
"""

from unittest.mock import MagicMock
from pywa.types import Message
from pywa.types.base_update import User
from src.services.webhook.message_handler import extract_message_context, MessageContext


def test_extract_message_context_with_valid_12_digit_brazilian_phone():
    """
    Deve inserir o nono dígito em números brasileiros de 12 dígitos.
    """
    msg = MagicMock(spec=Message)
    user = MagicMock(spec=User)
    user.wa_id = "554788884444"
    user.name = "Carlos Silva"
    msg.from_user = user
    msg.text = "Olá, preciso de ajuda"

    context = extract_message_context(msg)

    assert context is not None
    assert isinstance(context, MessageContext)
    assert context.sender_phone == "554788884444"
    assert context.target_phone == "5547988884444"
    assert context.user_name == "Carlos Silva"
    assert context.message_text == "Olá, preciso de ajuda"


def test_extract_message_context_with_already_formatted_13_digit_phone():
    """
    Deve preservar inalterado o número brasileiro que já possui 13 dígitos.
    """
    msg = MagicMock(spec=Message)
    user = MagicMock(spec=User)
    user.wa_id = "5547988884444"
    user.name = "Maria Souza"
    msg.from_user = user
    msg.text = "Cardápio do dia"

    context = extract_message_context(msg)

    assert context is not None
    assert context.sender_phone == "5547988884444"
    assert context.target_phone == "5547988884444"


def test_extract_message_context_with_international_phone():
    """
    Deve manter números internacionais sem modificação.
    """
    msg = MagicMock(spec=Message)
    user = MagicMock(spec=User)
    user.wa_id = "12025550199"
    user.name = "John Doe"
    msg.from_user = user
    msg.text = "Hello"

    context = extract_message_context(msg)

    assert context is not None
    assert context.sender_phone == "12025550199"
    assert context.target_phone == "12025550199"
    assert context.user_name == "John Doe"


def test_extract_message_context_missing_wa_id_returns_none():
    """
    Deve retornar None quando o identificador wa_id for nulo ou vazio.
    """
    msg = MagicMock(spec=Message)
    user = MagicMock(spec=User)
    user.wa_id = None
    user.name = "Sem ID"
    msg.from_user = user
    msg.text = "Mensagem órfã"

    context = extract_message_context(msg)

    assert context is None


def test_extract_message_context_empty_wa_id_returns_none():
    """
    Deve retornar None quando o identificador wa_id for string vazia.
    """
    msg = MagicMock(spec=Message)
    user = MagicMock(spec=User)
    user.wa_id = ""
    user.name = "Sem ID"
    msg.from_user = user
    msg.text = "Mensagem órfã"

    context = extract_message_context(msg)

    assert context is None


def test_extract_message_context_defaults_when_name_and_text_are_none():
    """
    Deve atribuir valores padrão para nome ('Usuário') e texto ('') quando forem nulos.
    """
    msg = MagicMock(spec=Message)
    user = MagicMock(spec=User)
    user.wa_id = "5547988884444"
    user.name = None
    msg.from_user = user
    msg.text = None

    context = extract_message_context(msg)

    assert context is not None
    assert context.user_name == "Usuário"
    assert context.message_text == ""


def test_normalize_phone_number_empty_or_none():
    """
    normalize_phone_number deve retornar string vazia para valores nulos ou vazios.
    """
    from src.services.webhook.message_handler import normalize_phone_number

    assert normalize_phone_number(None) == ""
    assert normalize_phone_number("") == ""
    assert normalize_phone_number("   ") == ""

