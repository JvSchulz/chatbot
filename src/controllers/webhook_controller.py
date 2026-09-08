import logging
from pywa import filters
from pywa.client import WhatsApp
from pywa.types.message import Message
from pywa.types.message_status import MessageStatus

logger = logging.getLogger("Chatbot")


def setup_webhook_handlers(wa: WhatsApp):
    @wa.on_message()
    def handle_message(client: WhatsApp, msg: Message):
        sender_phone = str(msg.from_user.wa_id or "")
        user_name = msg.from_user.name or "Usuário"
        message_text = msg.text or ""

        if not sender_phone:
            return

        logger.info(
            f"[INBOUND] De: {user_name} ({sender_phone}) | Texto: '{message_text}'"
        )

        if sender_phone.startswith("55") and len(sender_phone) == 12:
            target_phone = f"{sender_phone[:4]}9{sender_phone[4:]}"
        else:
            target_phone = sender_phone

        reply_payload = f"Olá {user_name}, recebi sua dúvida: '{message_text}'"

        try:
            response_msg_id = client.send_message(
                to=target_phone,
                text=reply_payload,
            )
            logger.info(
                f"[OUTBOUND SUCESSO] Para: {target_phone} | Resposta: '{reply_payload}' | ID: {response_msg_id}"
            )
        except Exception as e:
            logger.error(
                f"[OUTBOUND FALHA] Erro ao despachar requisição para a Meta: {e}"
            )

    @wa.on_message_status()
    def handle_status(_: WhatsApp, status: MessageStatus):
        status_name = (
            status.status.value
            if hasattr(status.status, "value")
            else str(status.status)
        )
        recipient = status.from_user.wa_id if status.from_user else "Desconhecido"
        msg_id = status.id

        if status.error:
            err = status.error
            logger.warning(
                f"[STATUS UPDATE] ID: {msg_id} | Destino: {recipient} | Status: {status_name} | "
                f"Erro {err.code}: {err.message} ({err.details})"
            )
        else:
            logger.info(
                f"[STATUS UPDATE] ID: {msg_id} | Destino: {recipient} | Status: {status_name}"
            )
