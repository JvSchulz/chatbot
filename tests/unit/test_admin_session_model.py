"""
Testes unitários para o modelo de dados de sessão de administrador.
"""

from datetime import datetime, timezone, timedelta
from sqlmodel import Session, create_engine, select
from src.models.user_model import User
from src.models.session_model import AdminSession
from src.core.db import SQLModel


def test_admin_session_model_instantiation():
    """
    Verifica a criação do modelo AdminSession com valores padrão e atributos obrigatórios.
    """
    now = datetime.now(timezone.utc)
    expires = now + timedelta(hours=12)

    session_obj = AdminSession(
        id="session-token-xyz-123",
        user_id=1,
        expires_at=expires,
        ip_address="127.0.0.1",
        user_agent="Mozilla/5.0 TestBrowser",
    )

    assert session_obj.id == "session-token-xyz-123"
    assert session_obj.user_id == 1
    assert session_obj.expires_at == expires
    assert session_obj.ip_address == "127.0.0.1"
    assert session_obj.user_agent == "Mozilla/5.0 TestBrowser"
    assert isinstance(session_obj.created_at, datetime)


def test_admin_session_persists_in_sqlite():
    """
    Verifica a persistência de AdminSession em banco de dados SQLite com relação à tabela User.
    """
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as db:
        user = User(
            login="testadmin",
            password="hashedpassword123",
            is_admin=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        assert user.id is not None

        admin_session = AdminSession(
            id="auth-token-456",
            user_id=user.id,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
        )
        db.add(admin_session)
        db.commit()

        retrieved = db.exec(
            select(AdminSession).where(AdminSession.id == "auth-token-456")
        ).first()

        assert retrieved is not None
        assert retrieved.user_id == user.id
