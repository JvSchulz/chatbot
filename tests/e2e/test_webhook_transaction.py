"""
Testes de ponta a ponta de que cada evento do webhook grava tudo ou nada, em uma única transação.
"""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select
from pywa.client import WhatsApp

from main import app
from src.models.chat_history_model import ChatHistory
from src.models.menu_model import Menu
from src.models.user_session_model import UserSession
from tests.conftest import sign_webhook

BSUID = "BR.1000000000007"
WA_ID = "554798765432"


@pytest.fixture(name="outbound")
def outbound_fixture(monkeypatch) -> list[dict]:
    sent: list[dict] = []

    def fake_send_message(self, to, text, **kwargs):
        sent.append({"to": to, "text": text, **kwargs})
        return "wamid.SAIDA_LOCAL"

    monkeypatch.setattr(WhatsApp, "send_message", fake_send_message)
    return sent


@pytest.fixture(name="failing_bot_log")
def failing_bot_log_fixture(monkeypatch) -> None:
    """Faz a gravação da resposta do bot no histórico falhar, como um erro de banco no meio do evento."""

    def explode(*args, **kwargs):
        raise RuntimeError("falha simulada ao gravar o histórico")

    monkeypatch.setattr("src.services.webhook.message_handler.save_bot_reply_log", explode)


@pytest.fixture(name="tree")
def tree_fixture(session: Session) -> dict[str, Menu]:
    root = Menu(name="menu_inicio", selection_name="Início", message="Bem-vindo")
    session.add(root)
    session.commit()
    child = Menu(name="Cursos", selection_name="Cursos", message="Nossos cursos", parent_id=root.id)
    session.add(child)
    session.commit()
    leaf = Menu(name="Engenharia", selection_name="Eng", message="Info", parent_id=child.id)
    session.add(leaf)
    session.commit()
    return {"root": root, "child": child, "leaf": leaf}


def post_webhook(body: bytes) -> int:
    response = TestClient(app).post(
        "/webhook",
        content=body,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": sign_webhook(body)},
    )
    return response.status_code


def stored_session(session: Session) -> UserSession | None:
    session.expire_all()
    return session.exec(select(UserSession).where(UserSession.user_id == BSUID)).first()


def history_count(session: Session) -> int:
    session.expire_all()
    return len(session.exec(select(ChatHistory)).all())


def test_failed_history_write_on_a_text_leaves_nothing_behind(
    session: Session, outbound, failing_bot_log, webhook_body, tree
):
    assert post_webhook(webhook_body("text", "Oi", WA_ID, BSUID)) == 200

    assert len(outbound) == 1
    assert history_count(session) == 0
    assert stored_session(session) is None


def test_failed_history_write_on_a_click_keeps_the_previous_session_state(
    session: Session, outbound, failing_bot_log, webhook_body, tree
):
    long_ago = datetime.now(timezone.utc) - timedelta(minutes=5)
    session.add(UserSession(user_id=BSUID, current_menu_id=tree["child"].id, last_interaction_at=long_ago))
    session.commit()

    body = webhook_body("button", f"menu:{tree['leaf'].id}", WA_ID, BSUID, "Eng")
    assert post_webhook(body) == 200

    kept = stored_session(session)
    assert kept is not None
    assert kept.current_menu_id == tree["child"].id
    assert kept.last_interaction_at == long_ago
    assert history_count(session) == 0


def test_successful_click_commits_the_click_the_reply_and_the_session_together(
    session: Session, outbound, webhook_body, tree
):
    body = webhook_body("button", f"menu:{tree['leaf'].id}", WA_ID, BSUID, "Eng")

    assert post_webhook(body) == 200

    saved = stored_session(session)
    assert saved is not None and saved.current_menu_id == tree["leaf"].id
    assert history_count(session) == 2
