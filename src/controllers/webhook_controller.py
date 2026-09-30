import logging
from pywa.client import WhatsApp
from pywa.types.message import Message
from pywa.types.message_status import MessageStatus
from pywa.types.callback import CallbackButton, CallbackSelection
from starlette.types import ASGIApp, Receive, Scope, Send
from starlette.types import Message as ASGIMessage
from src.core.db import open_event_session
from src.services.webhook.message_handler import (
    handle_message,
    handle_status,
    handle_callback,
    mask_user_id,
)

logger = logging.getLogger("Chatbot")


WEBHOOK_PATH = "/webhook"


class WebhookLogMiddleware:
    """
    Registra o corpo bruto e a assinatura de cada POST no webhook antes da PyWa, inclusive os que ela rejeita.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] != "POST" or scope["path"] != WEBHOOK_PATH:
            await self.app(scope, receive, send)
            return
        received = [await receive()]
        while received[-1].get("more_body"):
            received.append(await receive())
        body = b"".join(message.get("body", b"") for message in received)
        signature = dict(scope["headers"]).get(b"x-hub-signature-256", b"").decode("latin-1")
        logger.info(f"[WEBHOOK IN] assinatura={signature or 'ausente'} corpo={body.decode(errors='replace')}")

        async def replay() -> ASGIMessage:
            return received.pop(0) if received else await receive()

        await self.app(scope, replay, send)


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
