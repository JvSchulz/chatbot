"""
Testes de ponta a ponta de que o webhook não segura o bloqueio de escrita do SQLite enquanto
espera a resposta da Meta: outra escrita durante o envio precisa passar.
"""

import sqlite3
from contextlib import closing
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pywa.client import WhatsApp
from sqlmodel import Session, SQLModel

from main import app
from src.core.db import build_engine
from src.models.menu_model import Menu
from tests.conftest import sign_webhook

BSUID = "BR.1000000000008"
WA_ID = "554798765432"


@pytest.fixture(name="database_file")
def database_file_fixture(tmp_path: Path, monkeypatch) -> Iterator[Path]:
    """Banco em arquivo (com WAL, como em produção) com uma raiz e um filho, no lugar do banco em memória."""
    path = tmp_path / "webhook.db"
    engine = build_engine(f"sqlite:///{path}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as seed:
        root = Menu(name="menu_inicio", selection_name="Início", message="Bem-vindo")
        seed.add(root)
        seed.commit()
        seed.add(Menu(name="Cursos", selection_name="Cursos", message="Nossos cursos", parent_id=root.id))
        seed.commit()
    monkeypatch.setattr("src.core.db.engine", engine)
    yield path
    engine.dispose()


@pytest.fixture(name="concurrent_writes")
def concurrent_writes_fixture(monkeypatch, database_file: Path) -> list[str]:
    """Faz cada envio à Meta tentar uma escrita de outra conexão e registra se ela passou."""
    outcomes: list[str] = []

    def fake_send_message(self, to, text, **kwargs):
        try:
            with closing(sqlite3.connect(database_file, timeout=0.2)) as other:
                other.execute(
                    "INSERT INTO menus (name, selection_name, message, created_at, updated_at) "
                    "VALUES ('outra', 'outra', 'outra', datetime('now'), datetime('now'))"
                )
                other.commit()
            outcomes.append("escrita permitida")
        except sqlite3.OperationalError as error:
            outcomes.append(str(error))
        return "wamid.SAIDA_LOCAL"

    monkeypatch.setattr(WhatsApp, "send_message", fake_send_message)
    return outcomes


def post_webhook(body: bytes) -> None:
    response = TestClient(app).post(
        "/webhook",
        content=body,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": sign_webhook(body)},
    )
    assert response.status_code == 200


def test_text_event_does_not_hold_the_write_lock_while_sending(concurrent_writes: list[str], webhook_body):
    post_webhook(webhook_body("text", "Oi", WA_ID, BSUID))

    assert concurrent_writes == ["escrita permitida"]


def test_click_event_does_not_hold_the_write_lock_while_sending(concurrent_writes: list[str], webhook_body):
    post_webhook(webhook_body("button", "menu:2", WA_ID, BSUID, "Cursos"))

    assert concurrent_writes == ["escrita permitida"]


def test_event_rows_are_saved_once_the_event_ends(database_file: Path, concurrent_writes: list[str], webhook_body):
    post_webhook(webhook_body("text", "Oi", WA_ID, BSUID))

    with closing(sqlite3.connect(database_file)) as check:
        roles = [row[0] for row in check.execute("SELECT role FROM chat_histories ORDER BY id")]
        sessions = check.execute("SELECT COUNT(*) FROM user_sessions").fetchone()[0]
    assert roles == ["user", "bot"]
    assert sessions == 1
