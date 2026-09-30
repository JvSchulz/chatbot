"""
Testes do script de migração de identidade do bot, sempre contra bancos temporários.
"""

import sqlite3
from pathlib import Path
from sqlalchemy import create_engine
from sqlmodel import SQLModel
from src.models import menu_model, session_model, user_model  # noqa: F401
from scripts.migrate_bot_identity import BACKUP_SUFFIX, main, migrate

OLD_CHAT_HISTORIES = """
CREATE TABLE chat_histories (
    created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL, deleted_at DATETIME,
    sender_id VARCHAR NOT NULL, role VARCHAR NOT NULL, content VARCHAR NOT NULL,
    acessed_menu INTEGER, datetime DATETIME NOT NULL, id INTEGER PRIMARY KEY,
    FOREIGN KEY (acessed_menu) REFERENCES menus (id)
)
"""
OLD_USER_SESSIONS = """
CREATE TABLE user_sessions (
    created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL, deleted_at DATETIME,
    id INTEGER PRIMARY KEY, wa_id VARCHAR NOT NULL, mode VARCHAR NOT NULL,
    current_menu_id INTEGER, last_interaction_at DATETIME NOT NULL,
    FOREIGN KEY (current_menu_id) REFERENCES menus (id)
)
"""


def _old_database(path: Path) -> None:
    """Cria um banco com o esquema anterior à mudança: menus e usuários novos, históricos antigos."""
    engine = create_engine(f"sqlite:///{path}")
    SQLModel.metadata.create_all(
        engine,
        tables=[
            SQLModel.metadata.tables["menus"],
            SQLModel.metadata.tables["users"],
            SQLModel.metadata.tables["admin_sessions"],
        ],
    )
    engine.dispose()
    with sqlite3.connect(path) as connection:
        connection.execute("INSERT INTO menus (id, name, selection_name, message, created_at, updated_at) "
                           "VALUES (1, 'menu_inicio', 'Início', 'Bem-vindo', '2026-09-01 10:00:00', '2026-09-01 10:00:00')")
        connection.execute("INSERT INTO users (id, login, password, is_admin, created_at, updated_at) "
                           "VALUES (1, 'admin', 'hash', 1, '2026-09-01 10:00:00', '2026-09-01 10:00:00')")
        connection.execute(OLD_CHAT_HISTORIES)
        connection.execute(OLD_USER_SESSIONS)
        connection.execute("INSERT INTO chat_histories VALUES ('2026-09-01 10:00:00', '2026-09-01 10:00:00', NULL, "
                           "'554798765432', 'user', 'Olá', 1, '2026-09-01 10:00:00', 1)")
        connection.execute("INSERT INTO user_sessions VALUES ('2026-09-01 10:00:00', '2026-09-01 10:00:00', NULL, "
                           "1, '554798765432', 'menu', 1, '2026-09-01 10:00:00')")


def _columns(path: Path, table: str) -> set[str]:
    with sqlite3.connect(path) as connection:
        return {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}


def _count(path: Path, table: str) -> int:
    with sqlite3.connect(path) as connection:
        return connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]


def _backups(path: Path) -> list[Path]:
    return sorted(path.parent.glob(f"{path.name}{BACKUP_SUFFIX}*"))


def test_migration_backs_up_and_rebuilds_the_two_tables(tmp_path: Path):
    database = tmp_path / "database.db"
    _old_database(database)

    backup = migrate(database)

    assert backup is not None and backup.exists()
    assert _backups(database) == [backup]
    assert {"user_id", "wa_id", "menu_id"} <= _columns(database, "chat_histories")
    assert "sender_id" not in _columns(database, "chat_histories")
    assert {"user_id", "wa_id", "current_menu_id"} <= _columns(database, "user_sessions")
    assert _count(database, "chat_histories") == 0
    assert _count(database, "user_sessions") == 0


def test_backup_keeps_the_old_schema_and_data(tmp_path: Path):
    database = tmp_path / "database.db"
    _old_database(database)

    backup = migrate(database)

    assert backup is not None
    assert "sender_id" in _columns(backup, "chat_histories")
    assert _count(backup, "chat_histories") == 1
    assert _count(backup, "user_sessions") == 1


def test_menus_users_and_admin_sessions_are_left_intact(tmp_path: Path):
    database = tmp_path / "database.db"
    _old_database(database)

    migrate(database)

    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT id, name, message FROM menus").fetchall() == [(1, "menu_inicio", "Bem-vindo")]
        assert connection.execute("SELECT login, is_admin FROM users").fetchall() == [("admin", 1)]


def test_second_run_is_a_no_op(tmp_path: Path):
    database = tmp_path / "database.db"
    _old_database(database)
    first_backup = migrate(database)

    second_backup = migrate(database)

    assert second_backup is None
    assert _backups(database) == [first_backup]


def test_new_tables_accept_rows_with_the_menu_foreign_key(tmp_path: Path):
    database = tmp_path / "database.db"
    _old_database(database)
    migrate(database)

    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO chat_histories (user_id, role, content, menu_id, created_at, updated_at) "
            "VALUES ('BR.1000000000001', 'user', 'Cursos', 1, '2026-09-29 10:00:00', '2026-09-29 10:00:00')"
        )

    assert _count(database, "chat_histories") == 1


def test_missing_database_is_created_without_backup(tmp_path: Path):
    database = tmp_path / "novo.db"

    backup = migrate(database)

    assert backup is None
    assert not _backups(database)
    assert {"user_id"} <= _columns(database, "chat_histories")
    assert {"user_id"} <= _columns(database, "user_sessions")


def test_partially_migrated_database_only_rebuilds_the_stale_table(tmp_path: Path):
    database = tmp_path / "database.db"
    _old_database(database)
    migrate(database)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO chat_histories (user_id, role, content, created_at, updated_at) "
            "VALUES ('BR.1000000000001', 'user', 'Oi', '2026-09-29 10:00:00', '2026-09-29 10:00:00')"
        )
        connection.execute("DROP TABLE user_sessions")
        connection.execute(OLD_USER_SESSIONS)

    backup = migrate(database)

    assert backup is not None
    assert _count(database, "chat_histories") == 1
    assert "user_id" in _columns(database, "user_sessions")


def test_main_prints_the_backup_path(tmp_path: Path, capsys):
    database = tmp_path / "database.db"
    _old_database(database)

    main(["--db", str(database)])

    output = capsys.readouterr().out
    assert str(_backups(database)[0]) in output


def test_main_reports_when_there_is_nothing_to_migrate(tmp_path: Path, capsys):
    database = tmp_path / "database.db"
    _old_database(database)
    migrate(database)

    main(["--db", str(database)])

    assert "Nada a migrar" in capsys.readouterr().out


def test_main_prints_the_restore_steps_after_the_backup(tmp_path: Path, capsys):
    database = tmp_path / "database.db"
    _old_database(database)

    main(["--db", str(database)])

    output = capsys.readouterr().out
    backup = _backups(database)[0]
    assert "Para restaurar" in output
    assert "Pare o servidor" in output
    assert f"{database}-wal" in output and f"{database}-shm" in output
    assert f"cp {backup} {database}" in output


def test_main_does_not_print_restore_steps_when_nothing_was_migrated(tmp_path: Path, capsys):
    database = tmp_path / "database.db"
    _old_database(database)
    migrate(database)
    capsys.readouterr()

    main(["--db", str(database)])

    assert "Para restaurar" not in capsys.readouterr().out
