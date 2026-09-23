from datetime import datetime, timezone, timedelta
from sqlmodel import Session, select
from src.core.db import engine
from src.models.user_session_model import UserSession

SESSION_TTL_MINUTES = 15
MODE_MENU = "menu"
MODE_CONVERSATIONAL = "conversational"


def _ensure_utc(dt: datetime) -> datetime:
    """Garante que a data/hora esteja ciente de fuso horário UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def is_session_expired(
    last_interaction_at: datetime,
    max_inactivity_minutes: int = SESSION_TTL_MINUTES,
    current_time: datetime | None = None,
) -> bool:
    """
    Verifica se a inatividade da sessão ultrapassou o limite em minutos.

    Args:
        last_interaction_at: Carimbo de data/hora da última interação.
        max_inactivity_minutes: Tempo máximo de inatividade em minutos (padrão 15).
        current_time: Carimbo de data/hora atual para cálculo relativo.

    Returns:
        True se a inatividade for estritamente superior ao limite estipulado, False caso contrário.
    """
    now = _ensure_utc(current_time or datetime.now(timezone.utc))
    last_dt = _ensure_utc(last_interaction_at)
    elapsed = now - last_dt
    return elapsed > timedelta(minutes=max_inactivity_minutes)


def evaluate_session_ttl(
    session: UserSession,
    current_time: datetime | None = None,
) -> UserSession:
    """
    Avalia a expiração da sessão, revertendo para o menu raiz caso tenha expirado.

    Args:
        session: Instância de UserSession a ser inspecionada.
        current_time: Carimbo de data/hora atual opcional para testes.

    Returns:
        Instância de UserSession com estado atualizado após checagem de TTL.
    """
    if is_session_expired(session.last_interaction_at, current_time=current_time):
        session.mode = MODE_MENU
        session.current_menu_id = None
    return session


def get_or_create_session(
    wa_id: str,
    db_session: Session | None = None,
) -> UserSession:
    """
    Recupera a sessão existente do usuário ou instancia uma nova em caso de primeira visita.

    Args:
        wa_id: Identificador WhatsApp do remetente.
        db_session: Sessão opcional do banco para reaproveitamento em transações.

    Returns:
        Instância de UserSession recuperada ou recém-criada.
    """
    now = datetime.now(timezone.utc)

    def _query(s: Session) -> UserSession:
        statement = select(UserSession).where(UserSession.wa_id == wa_id)
        existing = s.exec(statement).first()
        if existing:
            existing.last_interaction_at = _ensure_utc(existing.last_interaction_at)
            return evaluate_session_ttl(existing, current_time=now)

        new_session = UserSession(
            wa_id=wa_id,
            mode=MODE_MENU,
            current_menu_id=None,
            last_interaction_at=now,
        )
        s.add(new_session)
        s.commit()
        s.refresh(new_session)
        new_session.last_interaction_at = _ensure_utc(new_session.last_interaction_at)
        return new_session

    if db_session:
        return _query(db_session)

    with Session(engine) as s:
        return _query(s)


def update_session_activity(
    wa_id: str,
    mode: str | None = None,
    menu_id: int | None = None,
) -> UserSession:
    """
    Atualiza o carimbo de última atividade e opcionalmente o modo/menu da sessão.

    Args:
        wa_id: Identificador WhatsApp do remetente.
        mode: Novo modo opcional para a sessão ('menu' ou 'conversational').
        menu_id: Identificador opcional do menu atualmente ativo.

    Returns:
        Instância de UserSession atualizada.
    """
    now = datetime.now(timezone.utc)
    with Session(engine) as s:
        statement = select(UserSession).where(UserSession.wa_id == wa_id)
        user_session = s.exec(statement).first()
        if not user_session:
            user_session = UserSession(
                wa_id=wa_id,
                mode=mode or MODE_MENU,
                current_menu_id=menu_id,
                last_interaction_at=now,
            )
            s.add(user_session)
        else:
            user_session.last_interaction_at = now
            if mode is not None:
                user_session.mode = mode
            if menu_id is not None:
                user_session.current_menu_id = menu_id

        s.commit()
        s.refresh(user_session)
        user_session.last_interaction_at = _ensure_utc(user_session.last_interaction_at)
        return user_session
