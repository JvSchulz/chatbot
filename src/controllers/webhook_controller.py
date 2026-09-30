import logging
from pywa.client import WhatsApp
from pywa.types.message import Message
from pywa.types.message_status import MessageStatus
from pywa.types.callback import CallbackButton, CallbackSelection
from src.core.db import open_event_session
from src.services.webhook.message_handler import (
    handle_message,
    handle_status,
    handle_callback,
    mask_user_id,
)

logger = logging.getLogger("Chatbot")


def log_handler_failure(event: str, update: Message | MessageStatus | CallbackButton | CallbackSelection, error: Exception) -> None:
    """
    Registra uma falha de tratador em uma única linha, sem dados pessoais nem parâmetros SQL.

    O traceback e a mensagem da exceção são omitidos de propósito: podem conter telefone,
    BSUID ou texto da mensagem.

    Args:
        event: Tipo do evento que falhou.
        update: Evento recebido, usado apenas para mascarar o identificador do usuário.
        error: Exceção capturada; só o nome da classe é registrado.
    """
    user_id = update.from_user.bsuid if update.from_user else None
    logger.error(
        f"[WEBHOOK] Falha ao processar {event} | Usuário: {mask_user_id(user_id)} | {type(error).__name__}"
    )


def setup_webhook_handlers(wa: WhatsApp):
    @wa.on_message()
    def on_message(client: WhatsApp, msg: Message):
        try:
            with open_event_session() as session:
                handle_message(client, msg, session)
        except Exception as error:
            log_handler_failure("mensagem", msg, error)

    @wa.on_message_status()
    def on_message_status(_: WhatsApp, status: MessageStatus):
        try:
            handle_status(_, status)
        except Exception as error:
            log_handler_failure("status", status, error)

    @wa.on_callback_selection()
    def on_callback_selection(client: WhatsApp, sel: CallbackSelection):
        try:
            with open_event_session() as session:
                handle_callback(client, sel, session)
        except Exception as error:
            log_handler_failure("seleção", sel, error)

    @wa.on_callback_button()
    def on_callback_button(client: WhatsApp, btn: CallbackButton):
        try:
            with open_event_session() as session:
                handle_callback(client, btn, session)
        except Exception as error:
            log_handler_failure("botão", btn, error)
