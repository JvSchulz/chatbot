"""
Testes de integração da inicialização da aplicação: criação do primeiro administrador no lifespan.
"""

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlmodel import Session
from src.core.config import settings
from src.models.user_model import User
from src.services.user_service import get_all_users
from main import app


@pytest.fixture(autouse=True)
def isolated_startup(engine, monkeypatch):
    """Aponta o lifespan para o banco de testes e evita criar tabelas no banco real."""
    monkeypatch.setattr("main.engine", engine)
    monkeypatch.setattr("main.create_db_and_tables", lambda: None)


def test_startup_creates_first_admin_from_initial_password(session: Session, monkeypatch):
    """
    O lifespan deve criar o administrador 'admin' quando o banco está vazio e a senha inicial é válida.
    """
    monkeypatch.setattr(settings, "admin_initial_password", SecretStr("SenhaInicial123"))

    with TestClient(app):
        pass

    session.expire_all()
    assert [user.login for user in get_all_users(session)] == ["admin"]


def test_startup_fails_on_empty_database_without_initial_password(monkeypatch):
    """
    O lifespan deve falhar nomeando ADMIN_INITIAL_PASSWORD quando o banco está vazio e não há senha inicial.
    """
    monkeypatch.setattr(settings, "admin_initial_password", None)

    with pytest.raises(RuntimeError, match="ADMIN_INITIAL_PASSWORD"):
        with TestClient(app):
            pass


def test_startup_does_not_touch_existing_users(session: Session, monkeypatch):
    """
    O lifespan não deve criar nem alterar usuários quando já existe um administrador.
    """
    monkeypatch.setattr(settings, "admin_initial_password", SecretStr("SenhaInicial123"))
    session.add(User(login="coord", password="hash", is_admin=True))
    session.commit()

    with TestClient(app):
        pass

    session.expire_all()
    assert [user.login for user in get_all_users(session)] == ["coord"]


@pytest.mark.parametrize("table", ["chat_histories", "user_sessions"])
def test_startup_fails_when_a_table_still_has_the_old_schema(engine, monkeypatch, table: str):
    """
    O lifespan deve falhar indicando a migração quando o banco tem o esquema anterior à identidade por BSUID.
    """
    monkeypatch.setattr(settings, "admin_initial_password", SecretStr("SenhaInicial123"))
    with engine.begin() as connection:
        connection.exec_driver_sql(f"DROP TABLE {table}")
        connection.exec_driver_sql(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY, wa_id VARCHAR)")

    with pytest.raises(RuntimeError, match=r"scripts\.migrate_bot_identity"):
        with TestClient(app):
            pass
