"""
Testes de integração para session_service com persistência em SQLite em memória.
"""

from datetime import datetime, timedelta, timezone
from sqlmodel import Session
from src.models.user_session_model import UserSession
from src.services.session_service import (
    get_or_create_session,
    update_session_activity,
    MODE_MENU,
    MODE_CONVERSATIONAL,
)


def test_get_or_create_session_creates_new_record_on_first_lookup(session: Session):
    """
    Primeira chamada para um wa_id desconhecido deve criar um registro com modo 'menu'.
    """
    wa_id = "5547998881111"

    user_session = get_or_create_session(wa_id=wa_id)

    assert user_session is not None
    assert user_session.wa_id == wa_id
    assert user_session.mode == MODE_MENU
    assert user_session.current_menu_id is None
    assert user_session.last_interaction_at is not None


def test_get_or_create_session_returns_existing_active_session(session: Session):
    """
    Chamada para sessão existente ativa deve manter o modo atual inalterado.
    """
    wa_id = "5547998882222"
    now = datetime.now(timezone.utc)
    existing = UserSession(
        wa_id=wa_id,
        mode=MODE_CONVERSATIONAL,
        current_menu_id=3,
        last_interaction_at=now - timedelta(minutes=5),
    )
    session.add(existing)
    session.commit()

    retrieved = get_or_create_session(wa_id=wa_id)

    assert retrieved.wa_id == wa_id
    assert retrieved.mode == MODE_CONVERSATIONAL
    assert retrieved.current_menu_id == 3


def test_get_or_create_session_expires_stale_session_to_menu_mode(session: Session):
    """
    Sessão em modo conversacional inativa por mais de 15 minutos deve ser resetada para 'menu'.
    """
    wa_id = "5547998883333"
    now = datetime.now(timezone.utc)
    stale = UserSession(
        wa_id=wa_id,
        mode=MODE_CONVERSATIONAL,
        current_menu_id=7,
        last_interaction_at=now - timedelta(minutes=25),
    )
    session.add(stale)
    session.commit()

    retrieved = get_or_create_session(wa_id=wa_id)

    assert retrieved.wa_id == wa_id
    assert retrieved.mode == MODE_MENU
    assert retrieved.current_menu_id is None


def test_update_session_activity_updates_timestamp_and_state(session: Session):
    """
    update_session_activity deve atualizar o carimbo temporal e persistir as transições de modo e menu.
    """
    wa_id = "5547998884444"
    old_time = datetime.now(timezone.utc) - timedelta(minutes=10)
    existing = UserSession(
        wa_id=wa_id,
        mode=MODE_MENU,
        current_menu_id=None,
        last_interaction_at=old_time,
    )
    session.add(existing)
    session.commit()

    updated = update_session_activity(
        wa_id=wa_id,
        mode=MODE_CONVERSATIONAL,
        menu_id=12,
    )

    assert updated.wa_id == wa_id
    assert updated.mode == MODE_CONVERSATIONAL
    assert updated.current_menu_id == 12
    assert updated.last_interaction_at > old_time


def test_get_or_create_session_with_explicit_db_session(session: Session):
    """
    get_or_create_session deve utilizar a sessão fornecida explicitamente.
    """
    wa_id = "5547998885555"
    created = get_or_create_session(wa_id=wa_id, db_session=session)
    assert created.wa_id == wa_id
    assert created.mode == MODE_MENU

