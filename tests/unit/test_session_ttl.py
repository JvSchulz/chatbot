"""
Testes unitários para cálculo e expiração do TTL de inatividade da sessão de usuário.
"""

from datetime import datetime, timedelta, timezone
from src.models.user_session_model import UserSession
from src.services.session_service import is_session_expired, evaluate_session_ttl


def test_is_session_expired_when_within_15_minutes():
    """
    Sessão com última interação há 14 minutos não deve estar expirada.
    """
    now = datetime.now(timezone.utc)
    last_interaction = now - timedelta(minutes=14)

    assert is_session_expired(last_interaction, current_time=now) is False


def test_is_session_expired_when_exceeding_15_minutes():
    """
    Sessão com última interação há 16 minutos deve estar expirada.
    """
    now = datetime.now(timezone.utc)
    last_interaction = now - timedelta(minutes=16)

    assert is_session_expired(last_interaction, current_time=now) is True


def test_is_session_expired_boundary_condition():
    """
    Sessão exatamente no limite de 15 minutos não deve ser considerada expirada (<= 15 min).
    """
    now = datetime.now(timezone.utc)
    last_interaction = now - timedelta(minutes=15)

    assert is_session_expired(last_interaction, current_time=now) is False


def test_evaluate_session_ttl_preserves_conversational_when_active():
    """
    Deve preservar o modo conversacional e o menu atual se a inatividade for inferior a 15 minutos.
    """
    now = datetime.now(timezone.utc)
    session = UserSession(
        user_id="BR.1000000000001",
        mode="conversational",
        current_menu_id=5,
        last_interaction_at=now - timedelta(minutes=10),
    )

    evaluated = evaluate_session_ttl(session, current_time=now)

    assert evaluated.mode == "conversational"
    assert evaluated.current_menu_id == 5


def test_evaluate_session_ttl_resets_to_menu_when_expired():
    """
    Deve resetar o modo para 'menu' e current_menu_id para None se ultrapassar 15 minutos.
    """
    now = datetime.now(timezone.utc)
    session = UserSession(
        user_id="BR.1000000000001",
        mode="conversational",
        current_menu_id=5,
        last_interaction_at=now - timedelta(minutes=20),
    )

    evaluated = evaluate_session_ttl(session, current_time=now)

    assert evaluated.mode == "menu"
    assert evaluated.current_menu_id is None


def test_evaluate_session_ttl_uses_the_given_reference_time_not_the_clock():
    last_interaction = datetime(2020, 1, 1, 12, 0, tzinfo=timezone.utc)
    session = UserSession(
        user_id="BR.1000000000001",
        mode="conversational",
        current_menu_id=5,
        last_interaction_at=last_interaction,
    )

    evaluated = evaluate_session_ttl(session, current_time=last_interaction + timedelta(minutes=5))

    assert (evaluated.mode, evaluated.current_menu_id) == ("conversational", 5)


def test_is_session_expired_defaults_to_the_current_time():
    now = datetime.now(timezone.utc)

    assert is_session_expired(now - timedelta(minutes=1)) is False
    assert is_session_expired(now - timedelta(minutes=20)) is True
