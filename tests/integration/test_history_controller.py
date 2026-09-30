"""
Testes de integração da página /historico: linhas reais, estado vazio, paginação e controle de acesso.
"""

import re
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from main import app
from src.models.chat_history_model import ChatHistory
from src.models.menu_model import Menu
from src.services.user_service import UserData, create_user
from tests.conftest import make_user_client

BASE_TIME = datetime(2026, 9, 1, 10, 0, 0, tzinfo=timezone.utc)
COLUMNS = ["ID", "ID Usuário", "Remetente", "Conteúdo", "Menu Acessado", "Data/Hora"]


def add_rows(session: Session, count: int) -> None:
    session.add_all(
        ChatHistory(
            user_id="BR.1000000000001",
            wa_id="554798765432",
            role="user",
            content=f"mensagem {index}",
            created_at=BASE_TIME + timedelta(seconds=index),
        )
        for index in range(1, count + 1)
    )
    session.commit()


def rendered_contents(html: str) -> list[str]:
    """Extrai o texto da coluna Conteúdo (quarta célula) de cada linha da tabela."""
    return [cells[3] for cells in (re.findall(r"<td[^>]*>(.*?)</td>", row, re.S) for row in re.findall(r"<tr>(.*?)</tr>", html, re.S)) if cells]


def test_history_page_lists_the_rows_newest_first(session: Session, auth_client: TestClient):
    menu = Menu(name="Cursos", selection_name="C", message="M")
    session.add(menu)
    session.commit()
    session.add(ChatHistory(user_id="BR.1", content="primeira", created_at=BASE_TIME))
    session.add(ChatHistory(user_id="BR.1", role="bot", content="segunda", menu_id=menu.id, created_at=BASE_TIME + timedelta(seconds=5)))
    session.add(ChatHistory(user_id="BR.2", wa_id="5511999998888", content="terceira", created_at=BASE_TIME + timedelta(seconds=9)))
    session.commit()

    response = auth_client.get("/historico")

    assert response.status_code == 200
    assert rendered_contents(response.text) == ["terceira", "segunda", "primeira"]
    assert "Cursos" in response.text
    assert "2026-09-01 10:00:09" in response.text


def test_history_page_shows_the_labels_of_a_row(session: Session, auth_client: TestClient):
    session.add(ChatHistory(user_id="BR.1000000000001", wa_id=None, role="bot", content="Olá", created_at=BASE_TIME))
    session.commit()

    response = auth_client.get("/historico")

    cells = re.findall(r"<td[^>]*>(.*?)</td>", response.text, re.S)
    assert [cell.strip() for cell in cells] == ["1", "BR.1000000000001", "Bot", "Olá", "-", "2026-09-01 10:00:00"]


def test_history_page_has_the_expected_columns_and_no_channel(auth_client: TestClient, session: Session):
    add_rows(session, 1)

    response = auth_client.get("/historico")

    assert [text.strip() for text in re.findall(r"<th[^>]*>(.*?)</th>", response.text)] == COLUMNS
    assert "Canal" not in response.text
    assert "Telegram" not in response.text


def test_history_page_shows_the_empty_state(auth_client: TestClient):
    response = auth_client.get("/historico")

    assert response.status_code == 200
    assert "Nenhuma mensagem registrada." in response.text
    assert "<table" not in response.text
    assert "Anterior" not in response.text and "Próxima" not in response.text


def test_history_page_escapes_message_content(session: Session, auth_client: TestClient):
    session.add(ChatHistory(user_id="BR.1", content="<script>alert(1)</script>", created_at=BASE_TIME))
    session.commit()

    response = auth_client.get("/historico")

    assert "<script>alert(1)</script>" not in response.text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in response.text


def test_second_page_shows_rows_51_to_100_with_both_links(session: Session, auth_client: TestClient):
    add_rows(session, 120)

    response = auth_client.get("/historico?page=2")

    contents = rendered_contents(response.text)
    assert contents[0] == "mensagem 70" and contents[-1] == "mensagem 21" and len(contents) == 50
    assert 'href="/historico?page=1"' in response.text
    assert 'href="/historico?page=3"' in response.text
    assert "Anterior" in response.text and "Próxima" in response.text


def test_first_page_has_only_the_next_link(session: Session, auth_client: TestClient):
    add_rows(session, 120)

    response = auth_client.get("/historico")

    assert 'href="/historico?page=2"' in response.text
    assert "Anterior" not in response.text
    assert "Página 1" in response.text


def test_last_page_has_only_the_previous_link(session: Session, auth_client: TestClient):
    add_rows(session, 120)

    response = auth_client.get("/historico?page=3")

    assert 'href="/historico?page=2"' in response.text
    assert "Próxima" not in response.text
    assert len(rendered_contents(response.text)) == 20


def test_single_page_has_no_navigation_links(session: Session, auth_client: TestClient):
    add_rows(session, 10)

    response = auth_client.get("/historico")

    assert "Anterior" not in response.text and "Próxima" not in response.text
    assert "pagination" not in response.text


@pytest.mark.parametrize("query", ["?page=abc", "?page=99", "?page=0", "?page=-4", "?page=", "?page=1.5"])
def test_invalid_or_out_of_range_pages_fall_back_to_a_valid_page(session: Session, auth_client: TestClient, query: str):
    add_rows(session, 10)

    response = auth_client.get(f"/historico{query}")

    assert response.status_code == 200
    assert len(rendered_contents(response.text)) == 10


def test_out_of_range_page_on_many_rows_shows_the_last_page(session: Session, auth_client: TestClient):
    add_rows(session, 120)

    response = auth_client.get("/historico?page=99")

    assert len(rendered_contents(response.text)) == 20


def test_anonymous_browser_is_redirected_to_login():
    response = TestClient(app, follow_redirects=False).get("/historico")

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_non_admin_user_can_open_the_history(session: Session):
    editor = create_user(session, UserData(login="editor", password="SenhaOriginal123", is_admin=False))

    response = make_user_client(session, editor).get("/historico")

    assert response.status_code == 200
