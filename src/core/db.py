from pathlib import Path
from sqlmodel import SQLModel, create_engine, Session
from sqlalchemy import Engine, event
from typing import Annotated
from fastapi import Depends

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DB_PATH = BASE_DIR / "database.db"
sqlite_url = f"sqlite:///{DB_PATH}"

# Tempo que uma escrita espera o bloqueio do SQLite antes de falhar com "database is locked"
SQLITE_BUSY_TIMEOUT_SECONDS = 30


def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL;")
    cursor.execute("PRAGMA synchronous=NORMAL;")
    cursor.execute("PRAGMA foreign_keys=ON;")
    cursor.close()


def build_engine(url: str) -> Engine:
    """
    Cria um motor SQLite com os PRAGMAs da aplicação e sem valores de parâmetros nos erros.

    Escritas concorrentes esperam até SQLITE_BUSY_TIMEOUT_SECONDS pelo bloqueio em vez de falhar na hora.

    Os parâmetros SQL carregam telefone, BSUID e texto de mensagens; com hide_parameters
    eles não aparecem nas mensagens de exceção nem nos tracebacks registrados em log.

    Args:
        url: URL de conexão SQLAlchemy.

    Returns:
        Motor configurado.
    """
    new_engine = create_engine(
        url,
        connect_args={"check_same_thread": False, "timeout": SQLITE_BUSY_TIMEOUT_SECONDS},
        hide_parameters=True,
    )
    event.listen(new_engine, "connect", set_sqlite_pragma)
    return new_engine


engine = build_engine(sqlite_url)


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session


def open_event_session() -> Session:
    """
    Abre a sessão que abrange um único evento do webhook, do início ao commit final.

    O autoflush fica desligado de propósito: as gravações do evento só chegam ao SQLite no commit,
    então o bloqueio de escrita não é mantido enquanto o servidor espera a resposta da Meta.

    Returns:
        Sessão sem autoflush, para uso em um bloco with; sair do bloco sem commit descarta tudo.
    """
    return Session(engine, autoflush=False)


SessionDep = Annotated[Session, Depends(get_session)]
