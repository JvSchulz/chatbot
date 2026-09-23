"""
Testes unitários para despacho de respostas via PyWa/WhatsApp Cloud API.
"""

from unittest.mock import MagicMock
from pywa.client import WhatsApp
from pywa.types import Button
from src.services.webhook.message_handler import dispatch_reply


def test_dispatch_reply_success_returns_message_id():
    """
    Despacho bem-sucedido deve retornar o identificador da mensagem enviada pela Meta.
    """
    client = MagicMock(spec=WhatsApp)
    client.send_message.return_value = "wamid.HBgLMTIzNDU2"

    payload = {
        "text": "Olá! Escolha uma opção:",
        "buttons": [Button(title="Opção 1", callback_data="menu:1")],
    }

    result = dispatch_reply(client=client, to="5547998765432", response_payload=payload)

    assert result == "wamid.HBgLMTIzNDU2"
    client.send_message.assert_called_once_with(
        to="5547998765432",
        text="Olá! Escolha uma opção:",
        buttons=payload["buttons"],
    )


def test_dispatch_reply_without_buttons_sends_text_only():
    """
    Despacho de mensagem de texto simples sem botões.
    """
    client = MagicMock(spec=WhatsApp)
    client.send_message.return_value = "wamid.PLAIN_TEXT_123"

    payload = {
        "text": "Mensagem informativa",
    }

    result = dispatch_reply(client=client, to="5547998765432", response_payload=payload)

    assert result == "wamid.PLAIN_TEXT_123"
    client.send_message.assert_called_once_with(
        to="5547998765432",
        text="Mensagem informativa",
        buttons=None,
    )


def test_dispatch_reply_exception_returns_none_without_raising(caplog):
    """
    Exceção durante transmissão para a API da Meta deve ser tratada e retornar None.
    """
    client = MagicMock(spec=WhatsApp)
    client.send_message.side_effect = RuntimeError("Meta API timeout error")

    payload = {
        "text": "Mensagem de teste",
    }

    with caplog.at_level("ERROR"):
        result = dispatch_reply(client=client, to="5547998765432", response_payload=payload)

    assert result is None
    assert "[OUTBOUND FALHA] Erro ao despachar requisição para a Meta: Meta API timeout error" in caplog.text
    client.send_message.assert_called_once()

