"""
Testes unitários para utilitários de infraestrutura de banco de dados e sessão.
"""

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



