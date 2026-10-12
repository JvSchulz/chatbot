from datetime import datetime, timezone, timedelta
from sqlmodel import Session, select
from src.models.user_session_model import UserSession

SESSION_TTL_MINUTES = 15
SESSION_MODE_MENU = "menu"
SESSION_MODE_CONVERSATIONAL = "conversational"


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
    now = current_time or datetime.now(timezone.utc)
    elapsed = now - last_interaction_at
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
        session.mode = SESSION_MODE_MENU
        session.current_menu_id = None
    return session


def get_or_create_session(session: Session, user_id: str, wa_id: str | None) -> UserSession:
    """
    Recupera a sessão do usuário (chave BSUID) ou registra uma nova na primeira visita.

    A expiração por inatividade e a atualização do wa_id ficam na sessão do banco recebida e
    são gravadas quando quem chamou confirma a transação do evento; esta função não faz commit.

    Args:
        session: Sessão ativa do banco de dados, dona da transação do evento.
        user_id: BSUID do usuário.
        wa_id: Telefone do usuário quando disponível; mantém o valor gravado se for None.

    Returns:
        Instância de UserSession recuperada ou recém-criada.
    """
    now = datetime.now(timezone.utc)
    user_session = session.exec(select(UserSession).where(UserSession.user_id == user_id)).first()
    if user_session:
        evaluate_session_ttl(user_session, current_time=now)
        if wa_id:
            user_session.wa_id = wa_id
    else:
        user_session = UserSession(
            user_id=user_id,
            wa_id=wa_id,
            mode=SESSION_MODE_MENU,
            current_menu_id=None,
            last_interaction_at=now,
        )
        session.add(user_session)
    return user_session


def update_session_activity(user_session: UserSession, menu_id: int | None) -> None:
    """
    Registra na sessão o carimbo da última atividade e o menu atualmente exibido ao usuário.

    A alteração fica na sessão do banco a que o objeto pertence e é gravada quando quem chamou
    confirma a transação do evento; esta função não faz commit.

    Args:
        user_session: Sessão do usuário obtida em get_or_create_session.
        menu_id: Identificador do menu exibido; None indica o menu raiz e limpa a referência.
    """
    user_session.last_interaction_at = datetime.now(timezone.utc)
    user_session.current_menu_id = menu_id
