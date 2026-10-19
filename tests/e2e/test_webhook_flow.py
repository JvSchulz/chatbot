"""
Testes de ponta a ponta do webhook: eventos assinados via HTTP, respostas enviadas e linhas gravadas.
"""

import logging
import re
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select
from pywa.client import WhatsApp
from pywa.types import SectionList
from src.models.chat_history_model import ChatHistory
from src.models.menu_model import Menu
from src.models.user_session_model import UserSession
from src.services.webhook.message_handler import ACTION_ROOT
from tests.conftest import sign_webhook
from main import app

ROOT_MESSAGE = "Bem-vindo à UDESC. Como podemos ajudar?"


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
    return TestClient(app)


@pytest.fixture(name="tree")
def tree_fixture(session: Session) -> dict[str, Menu]:
    """Raiz com dois filhos; 'graduacao' tem o filho 'matricula', que tem a folha 'documentos'."""
    root = Menu(name="menu_inicio", selection_name="Início", message=ROOT_MESSAGE)
    session.add(root)
    session.commit()
    grad = Menu(name="Graduação", selection_name="Grad", message="Cursos de Graduação", parent_id=root.id)
    office = Menu(name="Secretaria", selection_name="Sec", message="Atendimento geral", parent_id=root.id)
    session.add(grad)
    session.add(office)
    session.commit()
    matriculation = Menu(name="Matrícula", selection_name="Matr", message="Opções de matrícula", parent_id=grad.id)
    session.add(matriculation)
    session.commit()
    docs = Menu(
        name="Documentos", selection_name="Docs", message="Apresente RG e CPF.", parent_id=matriculation.id
    )
    session.add(docs)
    session.commit()
    return {"root": root, "grad": grad, "office": office, "matriculation": matriculation, "docs": docs}


def _post(client: TestClient, body: bytes) -> int:
    response = client.post(
        "/webhook",
        content=body,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": sign_webhook(body)},
    )
    return response.status_code


def _rows(session: Session) -> list[ChatHistory]:
    session.expire_all()
    return list(session.exec(select(ChatHistory).order_by(ChatHistory.id)).all())  # type: ignore


def test_text_lists_only_the_root_children(
    client: TestClient, session: Session, outbound: list[dict], webhook_body, tree
):
    status = _post(client, webhook_body("text", "Olá!", "554798765432", "BR.1000000000006"))

    assert status == 200
    assert len(outbound) == 1
    assert outbound[0]["to"] == "5547998765432"
    assert outbound[0]["text"] == ROOT_MESSAGE
    assert [b.callback_data for b in outbound[0]["buttons"]] == [
        f"menu:{tree['grad'].id}", f"menu:{tree['office'].id}",
    ]
    user_row, bot_row = _rows(session)
    assert (user_row.role, user_row.user_id, user_row.wa_id, user_row.content) == (
        "user", "BR.1000000000006", "554798765432", "Olá!",
    )
    assert (bot_row.role, bot_row.content) == ("bot", ROOT_MESSAGE)


def test_button_to_a_submenu_lists_its_children_then_back(
    client: TestClient, session: Session, outbound: list[dict], webhook_body, tree
):
    body = webhook_body("button", f"menu:{tree['grad'].id}", "554798765432", "BR.1000000000006", "Grad")

    assert _post(client, body) == 200

    assert outbound[0]["text"] == "Cursos de Graduação"
    assert [b.callback_data for b in outbound[0]["buttons"]] == [
        f"menu:{tree['matriculation'].id}",
        f"menu:{tree['root'].id}",
    ]
    click, reply = _rows(session)
    assert (click.role, click.content, click.menu_id) == ("user", "Grad", tree["grad"].id)
    assert (reply.role, reply.menu_id) == ("bot", tree["grad"].id)


def test_list_selection_of_a_leaf_offers_back_and_start(
    client: TestClient, session: Session, outbound: list[dict], webhook_body, tree
):
    body = webhook_body("list", f"menu:{tree['docs'].id}", "554798765432", "BR.1000000000006", "Docs")

    assert _post(client, body) == 200

    assert outbound[0]["text"] == "Apresente RG e CPF.\n\nDeseja realizar outra consulta?"
    assert [(b.title, b.callback_data) for b in outbound[0]["buttons"]] == [
        ("Voltar", f"menu:{tree['matriculation'].id}"),
        ("Voltar ao início", ACTION_ROOT),
    ]
    assert _rows(session)[0].menu_id == tree["docs"].id


def test_leaf_directly_under_the_root_offers_back_to_the_root_and_back_to_start(
    client: TestClient, session: Session, outbound: list[dict], webhook_body, tree
):
    body = webhook_body("button", f"menu:{tree['office'].id}", "554798765432", "BR.1000000000006", "Sec")

    assert _post(client, body) == 200

    assert [(b.title, b.callback_data) for b in outbound[0]["buttons"]] == [
        ("Voltar", f"menu:{tree['root'].id}"),
        ("Voltar ao início", ACTION_ROOT),
    ]


def test_submenu_with_three_children_is_answered_with_a_list_and_a_navigation_section(
    client: TestClient, session: Session, outbound: list[dict], webhook_body, tree
):
    for name in ("Rematrícula", "Trancamento"):
        session.add(Menu(name=name, selection_name=name, message=name, parent_id=tree["grad"].id))
    session.commit()
    body = webhook_body("button", f"menu:{tree['grad'].id}", "554798765432", "BR.1000000000006", "Grad")

    assert _post(client, body) == 200

    sent_list = outbound[0]["buttons"]
    assert isinstance(sent_list, SectionList)
    menu_section, navigation_section = list(sent_list.sections)
    assert (menu_section.title, navigation_section.title) == ("Menu", "Navegação")
    assert [row.title for row in menu_section.rows] == ["Matr", "Rematrícula", "Trancamento"]
    assert [(row.title, row.callback_data) for row in navigation_section.rows] == [
        ("Voltar", f"menu:{tree['root'].id}")
    ]


def test_back_from_depth_one_sends_the_root_menu(
    client: TestClient, session: Session, outbound: list[dict], webhook_body, tree
):
    body = webhook_body("button", f"menu:{tree['root'].id}", "554798765432", "BR.1000000000006", "Voltar")

    assert _post(client, body) == 200

    assert outbound[0]["text"] == ROOT_MESSAGE
    assert [b.callback_data for b in outbound[0]["buttons"]] == [
        f"menu:{tree['grad'].id}", f"menu:{tree['office'].id}",
    ]


def test_back_from_depth_two_sends_the_parent_submenu(
    client: TestClient, session: Session, outbound: list[dict], webhook_body, tree
):
    body = webhook_body("button", f"menu:{tree['grad'].id}", "554798765432", "BR.1000000000006", "Voltar")

    assert _post(client, body) == 200

    assert outbound[0]["text"] == "Cursos de Graduação"


def test_malformed_payload_returns_the_root_menu(
    client: TestClient, session: Session, outbound: list[dict], webhook_body, tree
):
    body = webhook_body("button", "menu:abc", "554798765432", "BR.1000000000006", "Quebrado")

    assert _post(client, body) == 200

    assert outbound[0]["text"] == ROOT_MESSAGE
    assert _rows(session)[0].menu_id is None


def test_contact_without_wa_id_is_answered_at_the_bsuid(
    client: TestClient, session: Session, outbound: list[dict], webhook_body, tree
):
    body = webhook_body("text", "Oi", None, "BR.1000000000005")

    assert _post(client, body) == 200

    assert outbound[0]["to"] == "BR.1000000000005"
    assert outbound[0]["text"] == ROOT_MESSAGE
    user_row, bot_row = _rows(session)
    assert (user_row.user_id, user_row.wa_id) == ("BR.1000000000005", None)
    assert (bot_row.role, bot_row.user_id) == ("bot", "BR.1000000000005")
    session.expire_all()
    stored = session.exec(select(UserSession)).one()
    assert (stored.user_id, stored.wa_id) == ("BR.1000000000005", None)


def test_deleted_menu_button_falls_back_to_the_unavailable_notice(
    client: TestClient, session: Session, outbound: list[dict], webhook_body, tree
):
    body = webhook_body("button", "menu:99999", "554798765432", "BR.1000000000006", "Antigo")

    assert _post(client, body) == 200

    assert outbound[0]["text"].startswith("Esse menu não está mais disponível")
    assert _rows(session)[0].menu_id is None


def test_a_stale_ask_question_button_returns_the_root_menu(
    client: TestClient, session: Session, outbound: list[dict], webhook_body, tree
):
    body = webhook_body("button", "action:ask_question", "554798765432", "BR.1000000000006", "Fazer Pergunta")

    assert _post(client, body) == 200

    assert outbound[0]["text"] == ROOT_MESSAGE
    assert [b.callback_data for b in outbound[0]["buttons"]] == [
        f"menu:{tree['grad'].id}", f"menu:{tree['office'].id}",
    ]


def test_three_children_are_sent_as_three_buttons(
    client: TestClient, session: Session, outbound: list[dict], webhook_body, tree
):
    session.add(Menu(name="Extensão", selection_name="Ext", message="Projetos", parent_id=tree["root"].id))
    session.commit()

    assert _post(client, webhook_body("text", "Oi", "554798765432", "BR.1000000000006")) == 200

    assert [b.title for b in outbound[0]["buttons"]] == ["Ext", "Grad", "Sec"]


def test_four_children_are_sent_as_a_four_row_section_list(
    client: TestClient, session: Session, outbound: list[dict], webhook_body, tree
):
    for name in ("Extensão", "Pesquisa"):
        session.add(Menu(name=name, selection_name=name, message="Projetos", parent_id=tree["root"].id))
    session.commit()

    assert _post(client, webhook_body("text", "Oi", "554798765432", "BR.1000000000006")) == 200

    section_list = outbound[0]["buttons"]
    assert isinstance(section_list, SectionList)
    sections = list(section_list.sections)
    assert [section.title for section in sections] == ["Menu"]
    assert len(list(sections[0].rows)) == 4


def test_webhook_flow_logs_carry_no_phone_bsuid_or_text(
    client: TestClient, session: Session, outbound: list[dict], webhook_body, tree, caplog
):
    with caplog.at_level(logging.DEBUG):
        _post(client, webhook_body("text", "meu CPF é 123", "554799998888", "BR.9999999999876"))
        _post(client, webhook_body("button", f"menu:{tree['grad'].id}", "554799998888", "BR.9999999999876", "Grad"))

    assert "[INBOUND]" in caplog.text and "[CALLBACK]" in caplog.text
    for secret in ("554799998888", "5547999998888", "BR.9999999999876", "meu CPF", "123"):
        assert secret not in caplog.text


def test_database_failure_during_a_webhook_leaks_no_personal_data(
    client: TestClient, session: Session, outbound: list[dict], webhook_body, tree, caplog, monkeypatch
):
    from sqlalchemy.exc import OperationalError

    def locked(*args, **kwargs):
        raise OperationalError("INSERT INTO chat_histories", ("BR.1234567890123", "554799998888", "meu CPF"), Exception("locked"))

    monkeypatch.setattr("src.services.webhook.message_handler.save_user_log", locked)

    with caplog.at_level(logging.DEBUG):
        status = _post(client, webhook_body("text", "meu CPF é 123", "554799998888", "BR.1234567890123"))

    assert status == 200
    assert "OperationalError" in caplog.text
    for secret in ("554799998888", "BR.1234567890123", "meu CPF", "INSERT"):
        assert secret not in caplog.text


def test_stored_xss_payload_from_a_user_is_escaped_in_the_history_page(
    client: TestClient, session: Session, outbound: list[dict], webhook_body, tree, auth_client: TestClient
):
    payload = "<img src=x onerror=alert(1)>"

    assert _post(client, webhook_body("text", payload, "554798765432", "BR.1000000000009")) == 200

    page = auth_client.get("/historico")
    assert page.status_code == 200
    assert payload not in page.text
    assert "&lt;img src=x onerror=alert(1)&gt;" in page.text
    assert not re.search(r"<img[^>]*onerror", page.text)
