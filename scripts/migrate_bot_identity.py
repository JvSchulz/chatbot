"""
Migra o banco para a identidade do bot por BSUID.

As tabelas chat_histories e user_sessions passam a usar user_id (BSUID) e wa_id opcional.
Como só guardam dados de teste, são recriadas do zero depois de um backup do arquivo do banco.
As tabelas menus, users e admin_sessions não são alteradas.

Uso (a partir da raiz do projeto, com o servidor parado):
    python -m scripts.migrate_bot_identity
    python -m scripts.migrate_bot_identity --db caminho/outro.db

O script é idempotente: com as tabelas já migradas, não faz nada e não cria backup.
"""

import argparse
import sqlite3
import sys
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from collections.abc import Sequence
from sqlalchemy import create_engine, event, text
from sqlmodel import SQLModel
from src.core.db import BOT_IDENTITY_COLUMN, BOT_IDENTITY_TABLES, DB_PATH, set_sqlite_pragma
from src.models import chat_history_model, menu_model, session_model, user_model, user_session_model  # noqa: F401

BACKUP_SUFFIX = ".bak-"


def _stale_tables(db_path: Path) -> list[str]:
    """
    Lista as tabelas reconstruídas que existem no banco sem a coluna user_id.

    Args:
        db_path: Caminho do arquivo SQLite.

    Returns:
        Nomes das tabelas com o esquema anterior à mudança; vazio se não há o que migrar.
    """
    stale: list[str] = []
    with closing(sqlite3.connect(db_path)) as connection:
        for table in BOT_IDENTITY_TABLES:
            columns = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
            if columns and BOT_IDENTITY_COLUMN not in columns:
                stale.append(table)
    return stale


def _backup(db_path: Path) -> Path:
    """
    Copia o banco, com consistência, para um arquivo ao lado com o carimbo UTC no nome.

    Args:
        db_path: Caminho do arquivo SQLite.

    Returns:
        Caminho do arquivo de backup criado.
    """
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = db_path.with_name(f"{db_path.name}{BACKUP_SUFFIX}{stamp}")
    with closing(sqlite3.connect(db_path)) as source, closing(sqlite3.connect(backup_path)) as target:
        source.backup(target)
    return backup_path


def migrate(db_path: Path) -> Path | None:
    """
    Recria as tabelas de histórico e de sessões no esquema por BSUID.

    Args:
        db_path: Caminho do arquivo SQLite a migrar; é criado se não existir.

    Returns:
        Caminho do backup criado, ou None se não havia tabela a migrar.
    """
    backup_path = None
    stale_tables = _stale_tables(db_path) if db_path.exists() else []
    if stale_tables:
        backup_path = _backup(db_path)

    engine = create_engine(f"sqlite:///{db_path}")
    event.listen(engine, "connect", set_sqlite_pragma)
    with engine.begin() as connection:
        for table in stale_tables:
            connection.execute(text(f"DROP TABLE {table}"))
    SQLModel.metadata.create_all(engine)
    engine.dispose()
    return backup_path


def main(argv: Sequence[str] | None = None) -> None:
    """
    Ponto de entrada da linha de comando.

    Args:
        argv: Argumentos da linha de comando; usa sys.argv quando omitido.
    """
    parser = argparse.ArgumentParser(description="Migra o banco para a identidade do bot por BSUID")
    parser.add_argument(
        "--db",
        type=Path,
        default=DB_PATH,
        help=f"Caminho do banco SQLite (padrão: {DB_PATH})",
    )
    args = parser.parse_args(argv)

    backup_path = migrate(args.db)
    if backup_path is None:
        print("Nada a migrar: as tabelas já usam user_id.")
        return
    print(f"Backup criado em: {backup_path}")
    print("Tabelas chat_histories e user_sessions recriadas.")
    print("Para restaurar o banco anterior:")
    print("  1. Pare o servidor.")
    print(f"  2. Apague {args.db}-wal e {args.db}-shm, se existirem.")
    print(f"  3. Copie o backup sobre o banco: cp {backup_path} {args.db}")


if __name__ == "__main__":
    sys.exit(main())
