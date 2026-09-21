import logging
from pywa import filters
from pywa.client import WhatsApp
from pywa.types.message import Message
from pywa.types.message_status import MessageStatus
from pywa.types.callback import CallbackButton, CallbackSelection
from src.services.webhook.message_handler import (
    handle_message,
    handle_status,
    handle_callback_selection,
    handle_callback_button,
)

logger = logging.getLogger("Chatbot")


def setup_webhook_handlers(wa: WhatsApp):
    @wa.on_message()
    def on_message(client: WhatsApp, msg: Message):
        handle_message(client, msg)

    @wa.on_message_status()
    def on_message_status(_: WhatsApp, status: MessageStatus):
        handle_status(_, status)

    @wa.on_callback_selection()
    def on_callback_selection(client: WhatsApp, sel: CallbackSelection):
        handle_callback_selection(client, sel)

    @wa.on_callback_button()
    def on_callback_button(client: WhatsApp, btn: CallbackButton):
        handle_callback_button(client, btn)
