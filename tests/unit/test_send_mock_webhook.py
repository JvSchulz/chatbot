"""
Testes unitários do simulador de webhook assinado (scripts/send_mock_webhook.py).
"""

import json
import os
import urllib.error
import pytest
from scripts import send_mock_webhook
from tests.conftest import sign_webhook


def test_sign_body_matches_the_signature_meta_would_send():
    """
    A assinatura do script deve ser idêntica à calculada com APP_SECRET sobre o corpo bruto.
    """
    body = b'{"a": 1}'

    assert send_mock_webhook.sign_body(body) == sign_webhook(body)


def test_build_payload_text_carries_contact_user_id_and_phone_id():
    """
    O evento de texto deve incluir contacts[].user_id e o phone_number_id configurado.
    """
    payload = json.loads(send_mock_webhook.build_payload("text", "Olá", "554798765432"))

    value = payload["entry"][0]["changes"][0]["value"]
    assert value["messages"][0]["text"]["body"] == "Olá"
    assert value["messages"][0]["from"] == "554798765432"
    assert value["contacts"][0]["user_id"]
    assert value["metadata"]["phone_number_id"] == os.environ["WA_PHONE_ID"]


def test_build_payload_button_carries_callback_data():
    """
    O evento de botão deve carregar os dados do botão em interactive.button_reply.id.
    """
    payload = json.loads(send_mock_webhook.build_payload("button", "menu:1", "554798765432"))

    message = payload["entry"][0]["changes"][0]["value"]["messages"][0]
    assert message["type"] == "interactive"
    assert message["interactive"]["button_reply"]["id"] == "menu:1"


def test_build_payload_generates_a_distinct_message_id_each_time():
    """
    Cada evento deve ter um id de mensagem próprio, para não ser descartado como duplicado.
    """
    first = json.loads(send_mock_webhook.build_payload("text", "a", "1"))
    second = json.loads(send_mock_webhook.build_payload("text", "a", "1"))

    first_id = first["entry"][0]["changes"][0]["value"]["messages"][0]["id"]
    second_id = second["entry"][0]["changes"][0]["value"]["messages"][0]["id"]
    assert first_id != second_id


def test_main_posts_signed_text_event_to_the_given_url(monkeypatch, capsys):
    """
    main deve enviar o texto assinado à URL informada e sair com 0 quando o servidor responde 2xx.
    """
    calls: list[tuple[str, bytes]] = []

    def fake_post(url: str, body: bytes) -> tuple[int, str]:
        calls.append((url, body))
        return 200, "ok"

    monkeypatch.setattr(send_mock_webhook, "post_webhook", fake_post)

    exit_code = send_mock_webhook.main(["--text", "Olá", "--url", "http://localhost:9/webhook"])

    assert exit_code == 0
    assert calls[0][0] == "http://localhost:9/webhook"
    assert json.loads(calls[0][1])["entry"][0]["changes"][0]["value"]["messages"][0]["text"]["body"] == "Olá"
    assert capsys.readouterr().out.strip() == "200 ok"


def test_main_posts_button_event_and_fails_on_rejection(monkeypatch):
    """
    main deve enviar o clique de botão e sair com 1 quando o servidor rejeita o evento.
    """
    bodies: list[bytes] = []

    def fake_post(url: str, body: bytes) -> tuple[int, str]:
        bodies.append(body)
        return 403, "Forbidden"

    monkeypatch.setattr(send_mock_webhook, "post_webhook", fake_post)

    exit_code = send_mock_webhook.main(["--button", "menu:2"])

    assert exit_code == 1
    message = json.loads(bodies[0])["entry"][0]["changes"][0]["value"]["messages"][0]
    assert message["interactive"]["button_reply"]["id"] == "menu:2"


def test_main_requires_exactly_one_of_text_or_button():
    """
    main deve recusar chamadas sem --text/--button ou com os dois ao mesmo tempo.
    """
    with pytest.raises(SystemExit):
        send_mock_webhook.main([])
    with pytest.raises(SystemExit):
        send_mock_webhook.main(["--text", "a", "--button", "b"])


def test_main_reports_unreachable_server_without_traceback(monkeypatch, capsys):
    """
    main deve informar que o servidor não respondeu e sair com 1, sem propagar a exceção de rede.
    """
    def fake_post(url: str, body: bytes) -> tuple[int, str]:
        raise urllib.error.URLError("Connection refused")

    monkeypatch.setattr(send_mock_webhook, "post_webhook", fake_post)

    exit_code = send_mock_webhook.main(["--text", "Olá"])

    assert exit_code == 1
    assert "Connection refused" in capsys.readouterr().err
