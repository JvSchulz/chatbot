"""
Teste E2E que liga o painel administrativo ao bot: menus criados em /menus, visitados via webhook e excluídos.
"""

import re

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select
from pywa.client import WhatsApp
from src.models.chat_history_model import ChatHistory
from src.models.menu_model import Menu
from src.models.user_session_model import UserSession
from tests.conftest import sign_webhook
from main import app

HTMX = {"HX-Request": "true"}


@pytest.fixture(name="outbound", autouse=True)
def outbound_fixture(monkeypatch) -> list[dict]:
    """Substitui o envio da PyWa por um registrador local, para nada sair da máquina."""
    sent: list[dict] = []

    def fake_send_message(self, to, text, **kwargs):
        sent.append({"to": to, "text": text, **kwargs})
        return "wamid.SAIDA_LOCAL"

    monkeypatch.setattr(WhatsApp, "send_message", fake_send_message)
    return sent


def _create(admin: TestClient, name: str, parent_id: int | None = None) -> None:
    data = {"name": name, "selection_name": name, "message": f"Mensagem de {name}"}
    if parent_id is None:
        data["is_root"] = "true"
    else:
        data["parent_id"] = str(parent_id)
        data["is_root"] = "false"
    assert admin.post("/menus", data=data, headers=HTMX).status_code == 200


def _menu_id(session: Session, name: str) -> int:
    session.expire_all()
    menu = session.exec(select(Menu).where(Menu.name == name)).one()
    assert menu.id is not None
    return menu.id


def _post_webhook(kind: str, content: str, webhook_body) -> int:
    body = webhook_body(kind, content, "554798765432", "BR.1000000000006", "Cursos")
    return TestClient(app).post(
        "/webhook",
        content=body,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": sign_webhook(body)},
    ).status_code


def test_admin_builds_menus_users_visit_them_and_a_visited_leaf_can_be_deleted(
    session: Session, auth_client: TestClient, outbound: list[dict], webhook_body
):
    _create(auth_client, "menu_inicio")
    root_id = _menu_id(session, "menu_inicio")
    _create(auth_client, "Cursos", parent_id=root_id)
    _create(auth_client, "Secretaria", parent_id=root_id)
    leaf_id = _menu_id(session, "Secretaria")

    assert _post_webhook("text", "Olá", webhook_body) == 200
    assert outbound[-1]["text"] == "Mensagem de menu_inicio"
    assert [b.title for b in outbound[-1]["buttons"]] == ["Cursos", "Secretaria", "Fazer Pergunta"]

    assert _post_webhook("button", f"menu:{leaf_id}", webhook_body) == 200
    assert outbound[-1]["text"].startswith("Mensagem de Secretaria")

    session.expire_all()
    visited = session.exec(select(ChatHistory).where(ChatHistory.menu_id == leaf_id)).all()
    assert len(visited) == 2
    assert session.exec(select(UserSession)).one().current_menu_id == leaf_id

    deletion = auth_client.delete(f"/menus/{leaf_id}", headers=HTMX)

    assert deletion.status_code == 200
    session.expire_all()
    assert session.get(Menu, leaf_id) is None
    history = session.exec(select(ChatHistory).order_by(ChatHistory.id)).all()  # type: ignore
    assert len(history) == 4
    assert [row.content for row in history][1:] == [
        "Mensagem de menu_inicio",
        "Cursos",
        "Mensagem de Secretaria\n\nDeseja realizar outra consulta?",
    ]
    assert all(row.menu_id is None for row in history)
    assert session.exec(select(UserSession)).one().current_menu_id is None


def _create_titled(admin: TestClient, name: str, selection_name: str, parent_id: int | None = None):
    data = {"name": name, "selection_name": selection_name, "message": f"Mensagem de {name}"}
    data.update({"is_root": "true"} if parent_id is None else {"parent_id": str(parent_id), "is_root": "false"})
    return admin.post("/menus", data=data, headers=HTMX)


def test_options_created_out_of_order_are_listed_and_sent_sorted_with_confirmations_and_back(
    session: Session, auth_client: TestClient, outbound: list[dict], webhook_body
):
    assert _create_titled(auth_client, "inicio", "Início").status_code == 200
    root_id = _menu_id(session, "inicio")
    created = _create_titled(auth_client, "2 tutoria", "Tutoria", root_id)
    assert "Menu criado com sucesso." in created.text
    for name, title in (("1 monitoria", "Monitoria"), ("10 estagio", "Estágio"), ("9 extensao", "Extensão")):
        assert _create_titled(auth_client, name, title, root_id).status_code == 200

    names = re.findall(r"<strong>([^<]*)</strong>", auth_client.get("/menus/lista").text)
    assert names == ["inicio", "1 monitoria", "2 tutoria", "9 extensao", "10 estagio"]

    assert _post_webhook("text", "Olá", webhook_body) == 200
    rows = list(list(outbound[-1]["buttons"].sections)[0].rows)
    assert [row.title for row in rows[:-1]] == ["Monitoria", "Tutoria", "Extensão", "Estágio"]

    tutoring_id = _menu_id(session, "2 tutoria")
    assert _post_webhook("button", f"menu:{tutoring_id}", webhook_body) == 200
    assert [(b.title, b.callback_data) for b in outbound[-1]["buttons"]] == [
        ("Voltar", f"menu:{root_id}"),
        ("Voltar ao início", "action:root"),
    ]

    deleted = auth_client.delete(f"/menus/{tutoring_id}", headers=HTMX)
    assert "Menu excluído com sucesso." in deleted.text


def test_a_title_over_twenty_characters_is_rejected_and_nothing_reaches_the_bot(
    session: Session, auth_client: TestClient
):
    assert _create_titled(auth_client, "inicio", "Início").status_code == 200
    root_id = _menu_id(session, "inicio")

    response = _create_titled(auth_client, "longo", "x" * 21, root_id)

    assert response.status_code == 422
    assert "Texto de seleção pode ter no máximo 20 caracteres." in response.text
    assert session.exec(select(Menu).where(Menu.name == "longo")).first() is None
