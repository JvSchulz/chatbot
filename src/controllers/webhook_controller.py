import logging
from pywa import filters
from pywa.client import WhatsApp
from pywa.types.message import Message
from pywa.types.message_status import MessageStatus
from src.services.webhook.message_handler import handle_message, handle_status

logger = logging.getLogger("Chatbot")


def setup_webhook_handlers(wa: WhatsApp):
    @wa.on_message()
    def on_message(client: WhatsApp, msg: Message):
        handle_message(client, msg)

    @wa.on_message_status()
    def on_message_status(_: WhatsApp, status: MessageStatus):
        handle_status(_, status)
