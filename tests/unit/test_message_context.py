"""
Testes unitários para extração e normalização de contexto de eventos WhatsApp.
"""

from unittest.mock import MagicMock
from sqlmodel import Session
from pywa.types import Message
from pywa.types.base_update import User
from src.services.webhook.message_handler import (
    MessageContext,
    extract_callback_context,
    extract_message_context,
    normalize_phone_number,
)


def _message(wa_id: str | None, bsuid: str = "BR.1234567890123", name: str | None = "Carlos Silva", text: str | None = "Olá"):
    msg = MagicMock(spec=Message)
    user = MagicMock(spec=User)
    user.bsuid = bsuid
    user.wa_id = wa_id
    user.name = name
    msg.from_user = user
    msg.text = text
    return msg


def test_extract_message_context_carries_user_id_wa_id_and_text(session: Session):
    context = extract_message_context(_message("554788884444", text="Preciso de ajuda"), session)

    assert isinstance(context, MessageContext)
    assert context is not None
    assert context.session is session
    assert context.user_id == "BR.1234567890123"
    assert context.wa_id == "554788884444"
    assert context.user_name == "Carlos Silva"
    assert context.message_text == "Preciso de ajuda"


def test_extract_message_context_reply_target_inserts_ninth_digit_of_12_digit_phone(session: Session):
    context = extract_message_context(_message("554788884444"), session)

    assert context is not None
    assert context.reply_to == "5547988884444"


def test_extract_message_context_reply_target_keeps_13_digit_phone(session: Session):
    context = extract_message_context(_message("5547988884444"), session)

    assert context is not None
    assert context.reply_to == "5547988884444"


def test_extract_message_context_reply_target_keeps_international_phone(session: Session):
    context = extract_message_context(_message("12025550199"), session)

    assert context is not None
    assert context.reply_to == "12025550199"


def test_extract_message_context_without_wa_id_replies_to_the_bsuid(session: Session):
    context = extract_message_context(_message(None, bsuid="BR.1000000000004"), session)

    assert context is not None
    assert (context.user_id, context.wa_id, context.reply_to) == (
        "BR.1000000000004", None, "BR.1000000000004",
    )


def test_extract_message_context_treats_empty_wa_id_as_absent(session: Session):
    context = extract_message_context(_message(""), session)

    assert context is not None
    assert context.wa_id is None


def test_extract_message_context_without_bsuid_returns_none(session: Session):
    assert extract_message_context(_message("554788884444", bsuid=""), session) is None


def test_extract_message_context_without_user_returns_none(session: Session):
    msg = MagicMock(spec=Message)
    msg.from_user = None

    assert extract_message_context(msg, session) is None


def test_extract_message_context_defaults_when_name_and_text_are_none(session: Session):
    context = extract_message_context(_message("5547988884444", name=None, text=None), session)

    assert context is not None
    assert context.user_name == "Usuário"
    assert context.message_text == ""


def test_extract_callback_context_uses_the_option_title_as_text(button_factory, session: Session):
    context = extract_callback_context(button_factory(wa_id="554788884444", title="Cursos", bsuid="BR.1000000000003"), session)

    assert context is not None
    assert context.user_id == "BR.1000000000003"
    assert context.reply_to == "5547988884444"
    assert context.message_text == "Cursos"


def test_extract_callback_context_without_user_returns_none(button_factory, session: Session):
    btn = button_factory()
    btn.from_user = None

    assert extract_callback_context(btn, session) is None


def test_normalize_phone_number_empty_or_none():
    assert normalize_phone_number(None) == ""
    assert normalize_phone_number("") == ""
    assert normalize_phone_number("   ") == ""
