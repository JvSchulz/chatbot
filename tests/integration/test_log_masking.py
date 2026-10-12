"""
Testes de que os logs da aplicação não expõem telefone, BSUID nem conteúdo de mensagens.
"""

import logging
import pytest
from unittest.mock import MagicMock
from sqlmodel import Session
from pywa.types import MessageStatus
from pywa.types.base_update import User
from src.models.menu_model import Menu
from src.services.webhook.message_handler import (
    dispatch_reply,
    handle_callback,
    handle_message,
    handle_status,
)

PHONE = "554799998888"
BSUID = "BR.9999999999876"
SECRET_TEXT = "meu CPF é 123"
SECRET_TITLE = "Título Sigiloso"


@pytest.fixture(name="root")
def root_fixture(session: Session) -> Menu:
    root = Menu(name="menu_inicio", selection_name="Início", message="Bem-vindo")
    session.add(root)
    session.commit()
    return root


def _assert_no_personal_data(caplog) -> None:
    assert caplog.text != ""
    for secret in (PHONE, "5547999998888", BSUID, SECRET_TEXT, "CPF", SECRET_TITLE):
        assert secret not in caplog.text


def test_inbound_text_and_reply_logs_carry_no_personal_data(
    session: Session, mock_wa_client: MagicMock, message_factory, root, caplog
):
    with caplog.at_level(logging.DEBUG):
        handle_message(mock_wa_client, message_factory(wa_id=PHONE, bsuid=BSUID, text=SECRET_TEXT), session)

    _assert_no_personal_data(caplog)
    assert "***9876" in caplog.text or "***8888" in caplog.text


def test_click_logs_carry_no_personal_data(
    session: Session, mock_wa_client: MagicMock, button_factory, root, caplog
):
    with caplog.at_level(logging.DEBUG):
        handle_callback(
            mock_wa_client,
            button_factory(wa_id=PHONE, bsuid=BSUID, data=f"menu:{root.id}", title=SECRET_TITLE), session
        )

    _assert_no_personal_data(caplog)
    assert f"Menu: {root.id}" in caplog.text


def test_click_from_a_user_without_phone_logs_the_bsuid_masked(
    session: Session, mock_wa_client: MagicMock, selection_factory, root, caplog
):
    with caplog.at_level(logging.DEBUG):
        handle_callback(
            mock_wa_client, selection_factory(wa_id=None, bsuid=BSUID, data="action:root", title=SECRET_TITLE), session
        )

    _assert_no_personal_data(caplog)


def test_successful_outbound_log_carries_no_recipient_or_text(caplog):
    client = MagicMock()
    client.send_message.return_value = "wamid.HBgLNTU0Nzk5OTk4ODg4"

    with caplog.at_level(logging.DEBUG):
        dispatch_reply(client, PHONE, {"text": SECRET_TEXT})

    _assert_no_personal_data(caplog)
    assert "[OUTBOUND SUCESSO] Para: ***8888" in caplog.text
    assert "wamid" not in caplog.text


def test_failed_outbound_log_carries_no_recipient_or_text(caplog):
    client = MagicMock()
    client.send_message.side_effect = RuntimeError("timeout")

    with caplog.at_level(logging.DEBUG):
        dispatch_reply(client, PHONE, {"text": SECRET_TEXT})

    _assert_no_personal_data(caplog)
    assert "[OUTBOUND FALHA] Para: ***8888 | Erro ao despachar requisição para a Meta: timeout" in caplog.text


def test_status_logs_carry_no_personal_data(caplog):
    status = MagicMock(spec=MessageStatus)
    status.id = "wamid.HBgLNTU0Nzk5OTk4ODg4"
    status.status.value = "delivered"
    user = MagicMock(spec=User)
    user.bsuid = BSUID
    user.wa_id = PHONE
    status.from_user = user
    status.error = None

    with caplog.at_level(logging.DEBUG):
        handle_status(MagicMock(), status)

    _assert_no_personal_data(caplog)
    assert "wamid" not in caplog.text


def test_status_error_text_is_redacted(caplog):
    status = MagicMock(spec=MessageStatus)
    status.status.value = "failed"
    user = MagicMock(spec=User)
    user.bsuid = BSUID
    user.wa_id = PHONE
    status.from_user = user
    err = MagicMock()
    err.code = 131026
    err.message = f"Message undeliverable to {PHONE}"
    err.details = f"user {BSUID} unreachable"
    status.error = err

    with caplog.at_level(logging.DEBUG):
        handle_status(MagicMock(), status)

    _assert_no_personal_data(caplog)
    assert "Erro 131026: Message undeliverable to *** (user *** unreachable)" in caplog.text


def test_failed_outbound_error_text_is_redacted(caplog):
    client = MagicMock()
    client.send_message.side_effect = RuntimeError(f"Recipient {PHONE} / {BSUID} not allowed")

    with caplog.at_level(logging.DEBUG):
        dispatch_reply(client, PHONE, {"text": SECRET_TEXT})

    _assert_no_personal_data(caplog)
    assert "Erro ao despachar requisição para a Meta: Recipient *** / *** not allowed" in caplog.text
