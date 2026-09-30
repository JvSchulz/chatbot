"""
Testes de integração da persistência dos modelos: datas UTC cientes, colunas e chaves estrangeiras.
"""

from datetime import datetime, timedelta, timezone
from sqlalchemy import inspect
from sqlmodel import Session, select
from src.models.chat_history_model import ChatHistory
from src.models.menu_model import Menu
from src.models.session_model import AdminSession
from src.models.user_model import User
from src.models.user_session_model import UserSession


def _reload(session: Session, instance):
    """Persiste, limpa o cache da sessão e devolve a linha lida de volta do banco."""
    session.add(instance)
    session.commit()
    identity = (type(instance), instance.id)
    session.expunge_all()
    return session.get(*identity)


def test_timestamp_columns_come_back_aware_utc(session: Session):
    menu = _reload(session, Menu(name="m", selection_name="m", message="m"))

    assert menu is not None
    assert menu.created_at.utcoffset() == timedelta(0)
    assert menu.updated_at.utcoffset() == timedelta(0)


def test_timestamp_model_has_no_deleted_at_column(session: Session):
    columns = {column["name"] for column in inspect(session.get_bind()).get_columns("menus")}

    assert "deleted_at" not in columns


def test_user_session_last_interaction_comes_back_aware_utc(session: Session):
    moment = datetime(2026, 9, 29, 10, 0, tzinfo=timezone(timedelta(hours=-3)))

    stored = _reload(session, UserSession(user_id="BR.1000000000001", last_interaction_at=moment))

    assert isinstance(stored, UserSession)
    assert stored.last_interaction_at == datetime(2026, 9, 29, 13, 0, tzinfo=timezone.utc)
    assert stored.last_interaction_at.utcoffset() == timedelta(0)


def test_admin_session_dates_come_back_aware_utc(session: Session):
    user = User(login="adm", password="x", is_admin=True)
    session.add(user)
    session.commit()
    expires = datetime.now(timezone.utc) + timedelta(hours=1)

    stored = _reload(
        session,
        AdminSession(id="tok", user_id=user.id, expires_at=expires),  # type: ignore
    )

    assert isinstance(stored, AdminSession)
    assert stored.expires_at.utcoffset() == timedelta(0)
    assert stored.created_at.utcoffset() == timedelta(0)


def test_chat_history_columns(session: Session):
    columns = {column["name"] for column in inspect(session.get_bind()).get_columns("chat_histories")}

    assert columns == {"id", "user_id", "wa_id", "role", "content", "menu_id", "created_at", "updated_at"}


def test_user_session_columns(session: Session):
    columns = {column["name"] for column in inspect(session.get_bind()).get_columns("user_sessions")}

    assert columns == {
        "id", "user_id", "wa_id", "mode", "current_menu_id",
        "last_interaction_at", "created_at", "updated_at",
    }


def test_chat_history_keeps_row_with_null_menu_when_menu_is_deleted(session: Session):
    menu = Menu(name="m", selection_name="m", message="m")
    session.add(menu)
    session.commit()
    session.add(ChatHistory(user_id="BR.1000000000001", role="user", content="Cursos", menu_id=menu.id))
    session.commit()

    session.delete(menu)
    session.commit()

    row = session.exec(select(ChatHistory)).one()
    assert (row.content, row.menu_id) == ("Cursos", None)


def test_user_session_keeps_row_with_null_menu_when_menu_is_deleted(session: Session):
    menu = Menu(name="m", selection_name="m", message="m")
    session.add(menu)
    session.commit()
    session.add(UserSession(user_id="BR.1000000000001", current_menu_id=menu.id))
    session.commit()

    session.delete(menu)
    session.commit()

    assert session.exec(select(UserSession)).one().current_menu_id is None


def test_user_session_user_id_is_unique(session: Session):
    import pytest
    from sqlalchemy.exc import IntegrityError

    session.add(UserSession(user_id="BR.1000000000001"))
    session.commit()
    session.add(UserSession(user_id="BR.1000000000001"))

    with pytest.raises(IntegrityError):
        session.commit()
