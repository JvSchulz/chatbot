"""
Testes de que as falhas dos tratadores do webhook viram uma linha de log mascarada, sem propagar.
"""

import logging
import pytest
from unittest.mock import MagicMock
from sqlalchemy.exc import OperationalError
from pywa.types import MessageStatus
from pywa.types.base_update import User
from src.controllers.webhook_controller import setup_webhook_handlers

PHONE = "554799998888"
BSUID = "BR.1349876543210"
SECRET_TEXT = "meu CPF é 123"


class _Recorder:
    """Finge o cliente WhatsApp e guarda os tratadores registrados por decorador."""

    def __init__(self) -> None:
        self.handlers: dict[str, object] = {}

    def __getattr__(self, name: str):
        if not name.startswith("on_"):
            raise AttributeError(name)

        def registration():
            def decorator(function):
                self.handlers[name] = function
                return function

            return decorator

        return registration


@pytest.fixture(name="handlers")
def handlers_fixture(monkeypatch) -> dict[str, object]:
    recorder = _Recorder()
    setup_webhook_handlers(recorder)  # type: ignore[arg-type]

    def explode(*args, **kwargs):
        raise OperationalError(
            f"INSERT INTO chat_histories VALUES (?, ?, ?)",
            (BSUID, PHONE, SECRET_TEXT),
            Exception(f"database is locked for {PHONE}"),
        )

    for name in ("handle_message", "handle_status", "handle_callback"):
        monkeypatch.setattr(f"src.controllers.webhook_controller.{name}", explode)
    return recorder.handlers


def _update(spec) -> MagicMock:
    update = MagicMock(spec=spec)
    user = MagicMock(spec=User)
    user.bsuid = BSUID
    user.wa_id = PHONE
    update.from_user = user
    update.text = SECRET_TEXT
    update.title = SECRET_TEXT
    update.data = "menu:1"
    return update


@pytest.mark.parametrize(
    "registration, event",
    [
        ("on_message", "mensagem"),
        ("on_message_status", "status"),
        ("on_callback_selection", "seleção"),
        ("on_callback_button", "botão"),
    ],
)
def test_handler_failure_logs_one_masked_line_and_does_not_raise(
    handlers, caplog, registration: str, event: str
):
    handler = handlers[registration]

    with caplog.at_level(logging.DEBUG):
        handler(MagicMock(), _update(MessageStatus))  # type: ignore[operator]

    assert caplog.messages == [f"[WEBHOOK] Falha ao processar {event} | Usuário: ***3210 | OperationalError"]
    for secret in (PHONE, BSUID, "CPF", "INSERT", "locked"):
        assert secret not in caplog.text


def test_handler_failure_without_user_is_logged_with_a_masked_placeholder(handlers, caplog):
    update = _update(MessageStatus)
    update.from_user = None

    with caplog.at_level(logging.DEBUG):
        handlers["on_message"](MagicMock(), update)  # type: ignore[operator]

    assert caplog.messages == ["[WEBHOOK] Falha ao processar mensagem | Usuário: *** | OperationalError"]
