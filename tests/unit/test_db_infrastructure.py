"""
Testes unitários para utilitários de infraestrutura de banco de dados e sessão.
"""

import pytest
from sqlmodel import Session
from src.core.db import create_db_and_tables, get_session


def test_create_db_and_tables():
    """
    create_db_and_tables deve executar sem exceções.
    """
    create_db_and_tables()


def test_get_session_yields_valid_session():
    """
    get_session deve produzir uma instância válida de Session e fechá-la.
    """
    gen = get_session()
    sess = next(gen)
    assert isinstance(sess, Session)
    try:
        next(gen)
    except StopIteration:
        pass


def test_set_sqlite_pragma_configures_wal_and_foreign_keys():
    """
    set_sqlite_pragma deve executar os comandos PRAGMA no cursor do SQLite.
    """
    from unittest.mock import MagicMock
    from src.core.db import set_sqlite_pragma

    mock_connection = MagicMock()
    mock_cursor = MagicMock()
    mock_connection.cursor.return_value = mock_cursor

    set_sqlite_pragma(mock_connection, None)

    assert mock_cursor.execute.call_count == 3
    mock_cursor.close.assert_called_once()





def _engine_with_old_table(table: str):
    """Motor em memória com o esquema atual, exceto a tabela informada, recriada no formato antigo."""
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool
    from sqlmodel import SQLModel

    engine = create_engine("sqlite://", poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.exec_driver_sql(f"DROP TABLE {table}")
        connection.exec_driver_sql(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY, wa_id VARCHAR)")
    return engine


def test_ensure_bot_identity_schema_accepts_the_current_schema(engine):
    from src.core.db import ensure_bot_identity_schema

    ensure_bot_identity_schema(engine)


def test_ensure_bot_identity_schema_accepts_an_empty_database():
    from sqlalchemy import create_engine
    from src.core.db import ensure_bot_identity_schema

    ensure_bot_identity_schema(create_engine("sqlite://"))


@pytest.mark.parametrize("table", ["chat_histories", "user_sessions"])
def test_ensure_bot_identity_schema_rejects_old_tables_and_names_the_migration(table: str):
    from src.core.db import ensure_bot_identity_schema

    with pytest.raises(RuntimeError, match=r"python -m scripts\.migrate_bot_identity") as error:
        ensure_bot_identity_schema(_engine_with_old_table(table))

    assert table in str(error.value)


def test_build_engine_hides_sql_parameters_in_errors():
    from sqlalchemy.exc import IntegrityError
    from src.core.db import build_engine

    engine = build_engine("sqlite://")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE secrets (id INTEGER PRIMARY KEY, phone VARCHAR NOT NULL)")

    with pytest.raises(IntegrityError) as error:
        with engine.begin() as connection:
            connection.exec_driver_sql("INSERT INTO secrets (id, phone) VALUES (?, ?)", (1, None))
            connection.exec_driver_sql("INSERT INTO secrets (id, phone) VALUES (?, ?)", (1, "554799998888"))

    assert "554799998888" not in str(error.value)
    assert "[parameters:" not in str(error.value)


def test_build_engine_keeps_the_sqlite_pragmas():
    from src.core.db import build_engine

    with build_engine("sqlite://").connect() as connection:
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1


def test_production_engine_hides_sql_parameters():
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-c", "import src.core.db as db; print(db.engine.hide_parameters)"],
        capture_output=True,
        text=True,
        check=True,
    )

    assert result.stdout.strip() == "True"


def test_open_event_session_does_not_autoflush_and_uses_the_configured_engine(engine):
    from src.core.db import open_event_session

    with open_event_session() as event_session:
        assert event_session.autoflush is False
        assert event_session.get_bind() is engine


def test_build_engine_waits_up_to_thirty_seconds_for_the_write_lock():
    from src.core.db import build_engine

    with build_engine("sqlite://").connect() as connection:
        assert connection.exec_driver_sql("PRAGMA busy_timeout").scalar() == 30000
