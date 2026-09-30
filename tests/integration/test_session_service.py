"""
Testes de integração para session_service com persistência em SQLite em memória.
"""

from datetime import datetime, timedelta, timezone
from sqlmodel import Session, select
from src.models.menu_model import Menu
from src.models.user_session_model import UserSession
from src.services.session_service import (
    get_or_create_session,
    update_session_activity,
    SESSION_MODE_MENU,
    SESSION_MODE_CONVERSATIONAL,
)

USER_ID = "BR.1000000000001"


def _stored_session(session: Session, user_id: str) -> UserSession:
    """Confirma a transação e lê a sessão direto do banco, descartando qualquer objeto em cache."""
    session.commit()
    session.expire_all()
    return session.exec(select(UserSession).where(UserSession.user_id == user_id)).one()


def _add_menu(session: Session) -> int:
    menu = Menu(name="m", selection_name="m", message="m")
    session.add(menu)
    session.commit()
    assert menu.id is not None
    return menu.id


def test_get_or_create_session_creates_new_record_on_first_lookup(session: Session):
    before = datetime.now(timezone.utc)

    user_session = get_or_create_session(session, USER_ID, "5547998881111")

    assert user_session.user_id == USER_ID
    assert user_session.wa_id == "5547998881111"
    assert user_session.mode == SESSION_MODE_MENU
    assert user_session.current_menu_id is None
    assert before <= user_session.last_interaction_at <= datetime.now(timezone.utc)


def test_get_or_create_session_persists_the_new_record(session: Session):
    get_or_create_session(session, USER_ID, None)

    assert _stored_session(session, USER_ID).wa_id is None


def test_get_or_create_session_returns_one_session_per_user_id(session: Session):
    get_or_create_session(session, USER_ID, None)
    get_or_create_session(session, USER_ID, None)

    assert len(session.exec(select(UserSession)).all()) == 1


def test_get_or_create_session_returns_existing_active_session(session: Session):
    menu_id = _add_menu(session)
    now = datetime.now(timezone.utc)
    session.add(
        UserSession(
            user_id=USER_ID,
            mode=SESSION_MODE_CONVERSATIONAL,
            current_menu_id=menu_id,
            last_interaction_at=now - timedelta(minutes=5),
        )
    )
    session.commit()

    retrieved = get_or_create_session(session, USER_ID, None)

    assert retrieved.mode == SESSION_MODE_CONVERSATIONAL
    assert retrieved.current_menu_id == menu_id


def test_get_or_create_session_persists_ttl_reset(session: Session):
    menu_id = _add_menu(session)
    session.add(
        UserSession(
            user_id=USER_ID,
            mode=SESSION_MODE_CONVERSATIONAL,
            current_menu_id=menu_id,
            last_interaction_at=datetime.now(timezone.utc) - timedelta(minutes=16),
        )
    )
    session.commit()

    retrieved = get_or_create_session(session, USER_ID, None)

    assert (retrieved.mode, retrieved.current_menu_id) == (SESSION_MODE_MENU, None)
    stored = _stored_session(session, USER_ID)
    assert (stored.mode, stored.current_menu_id) == (SESSION_MODE_MENU, None)


def test_get_or_create_session_keeps_wa_id_current(session: Session):
    session.add(UserSession(user_id=USER_ID, wa_id=None))
    session.commit()

    get_or_create_session(session, USER_ID, "5547998881111")

    assert _stored_session(session, USER_ID).wa_id == "5547998881111"


def test_get_or_create_session_does_not_erase_known_wa_id_when_absent(session: Session):
    session.add(UserSession(user_id=USER_ID, wa_id="5547998881111"))
    session.commit()

    get_or_create_session(session, USER_ID, None)

    assert _stored_session(session, USER_ID).wa_id == "5547998881111"


def test_get_or_create_session_returns_a_session_bound_to_the_given_db_session(session: Session):
    created = get_or_create_session(session, USER_ID, None)

    assert created.user_id == USER_ID
    assert created.mode == SESSION_MODE_MENU


def test_update_session_activity_refreshes_timestamp_and_sets_the_menu(session: Session):
    menu_id = _add_menu(session)
    old_time = datetime.now(timezone.utc) - timedelta(minutes=10)
    user_session = UserSession(user_id=USER_ID, last_interaction_at=old_time)
    session.add(user_session)
    session.commit()
    before = datetime.now(timezone.utc)

    update_session_activity(user_session, menu_id)

    stored = _stored_session(session, USER_ID)
    assert stored.current_menu_id == menu_id
    assert before <= stored.last_interaction_at <= datetime.now(timezone.utc)


def test_update_session_activity_without_a_menu_clears_the_current_menu(session: Session):
    menu_id = _add_menu(session)
    user_session = UserSession(
        user_id=USER_ID,
        mode=SESSION_MODE_CONVERSATIONAL,
        current_menu_id=menu_id,
        last_interaction_at=datetime.now(timezone.utc) - timedelta(minutes=10),
    )
    session.add(user_session)
    session.commit()

    update_session_activity(user_session, None)

    stored = _stored_session(session, USER_ID)
    assert (stored.mode, stored.current_menu_id) == (SESSION_MODE_CONVERSATIONAL, None)
    assert datetime.now(timezone.utc) - stored.last_interaction_at < timedelta(minutes=1)


def test_session_functions_leave_the_commit_to_the_caller(session: Session):
    user_session = get_or_create_session(session, USER_ID, "5547998881111")
    update_session_activity(user_session, None)

    session.rollback()

    assert session.exec(select(UserSession)).all() == []
