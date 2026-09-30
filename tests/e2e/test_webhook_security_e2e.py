"""
Testes E2E da segurança do webhook: assinatura HMAC da Meta e verificação do token de desafio.
"""

import hashlib
import hmac
import os
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select
from pywa.client import WhatsApp
from src.models.chat_history_model import ChatHistory
from src.models.menu_model import Menu
from src.models.user_session_model import UserSession
from tests.conftest import sign_webhook
from main import app

SIGNATURE_HEADER = "X-Hub-Signature-256"


@pytest.fixture(name="outbound")
def outbound_fixture(monkeypatch) -> list[dict]:
    """Substitui o envio da PyWa por um registrador local, para nada sair da máquina."""
    sent: list[dict] = []

    def fake_send_message(self, to, text, **kwargs):
        sent.append({"to": to, "text": text, **kwargs})
        return "wamid.SAIDA_LOCAL"

    monkeypatch.setattr(WhatsApp, "send_message", fake_send_message)
    return sent


@pytest.fixture(name="client")
def client_fixture() -> TestClient:
    """Cliente HTTP da aplicação real, sem sessão administrativa nem token CSRF."""
    return TestClient(app)


def _post_webhook(client: TestClient, body: bytes, signature: str | None) -> int:
    """Envia o corpo ao webhook com o cabeçalho de assinatura informado e devolve o status."""
    headers = {"Content-Type": "application/json"}
    if signature is not None:
        headers[SIGNATURE_HEADER] = signature
    return client.post("/webhook", content=body, headers=headers).status_code


def _persisted_rows(session: Session) -> int:
    """Conta as linhas de histórico e de sessões de conversa persistidas."""
    session.expire_all()
    return len(session.exec(select(ChatHistory)).all()) + len(session.exec(select(UserSession)).all())


def test_signed_text_webhook_is_processed_and_logged(
    client: TestClient, session: Session, outbound: list[dict], webhook_body
):
    """
    Webhook de texto assinado com APP_SECRET, sem cookie nem CSRF, deve gerar resposta e histórico.
    """
    body = webhook_body("text", "Olá", "554798765432")

    status = _post_webhook(client, body, sign_webhook(body))

    assert status == 200
    session.expire_all()
    rows = session.exec(select(ChatHistory).order_by(ChatHistory.id)).all()  # type: ignore
    assert [(row.role, row.user_id, row.wa_id) for row in rows] == [
        ("user", "BR.1234567890123", "554798765432"),
        ("bot", "BR.1234567890123", None),
    ]
    assert rows[0].content == "Olá"
    assert len(outbound) == 1


def _forged_signature(body: bytes) -> str:
    """Assinatura bem formada, mas calculada com uma chave que não é a APP_SECRET."""
    return "sha256=" + hmac.new(b"outra-chave", body, hashlib.sha256).hexdigest()


def _signature_of_another_body(body: bytes) -> str:
    """Assinatura válida da APP_SECRET, porém de outro corpo (corpo adulterado em trânsito)."""
    return sign_webhook(body + b" ")


@pytest.mark.parametrize(
    "make_signature",
    [
        lambda body: None,
        lambda body: "sha256=" + "0" * 64,
        _forged_signature,
        _signature_of_another_body,
    ],
    ids=["missing", "garbage", "wrong-key", "tampered-body"],
)
def test_unsigned_or_forged_webhook_is_rejected_without_side_effects(
    client: TestClient, session: Session, outbound: list[dict], webhook_body, make_signature
):
    """
    Webhook sem assinatura, forjado ou adulterado deve receber 4xx, sem linhas no banco nem envio.
    """
    body = webhook_body("text", "Olá", "554798765432")

    status = _post_webhook(client, body, make_signature(body))

    assert 400 <= status < 500
    assert _persisted_rows(session) == 0
    assert outbound == []


def test_challenge_succeeds_only_with_configured_verify_token(client: TestClient):
    """
    GET /webhook deve devolver o desafio somente quando o token é o WA_VERIFY_TOKEN configurado.
    """
    valid = client.get(
        "/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": os.environ["WA_VERIFY_TOKEN"],
            "hub.challenge": "1158201444",
        },
    )

    assert valid.status_code == 200
    assert valid.text == "1158201444"


@pytest.mark.parametrize("token", ["chatbotudesc", "token-errado", ""])
def test_challenge_is_refused_with_any_other_verify_token(client: TestClient, token: str):
    """
    GET /webhook deve recusar (403) qualquer token que não seja o WA_VERIFY_TOKEN, inclusive o antigo fixo.
    """
    response = client.get(
        "/webhook",
        params={"hub.mode": "subscribe", "hub.verify_token": token, "hub.challenge": "1158201444"},
    )

    assert response.status_code == 403
    assert "1158201444" not in response.text


def test_signed_button_webhook_reaches_the_callback_handler(
    client: TestClient, session: Session, outbound: list[dict], webhook_body
):
    """
    Webhook de clique em botão assinado deve chegar ao tratador de callbacks e responder com o menu.
    """
    menu = Menu(name="Graduação", selection_name="Grad", message="Cursos de Graduação", parent_id=None)
    session.add(menu)
    session.commit()
    session.refresh(menu)
    body = webhook_body("button", f"menu:{menu.id}", "554798765432")

    status = _post_webhook(client, body, sign_webhook(body))

    assert status == 200
    assert len(outbound) == 1
    assert outbound[0]["text"].startswith("Cursos de Graduação")
