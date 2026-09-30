from typing import Any
from datetime import datetime, timezone
from sqlmodel import Field
from src.models.timestamp_model import TimestampModel
from src.models.types import UTCDateTime


class UserSession(TimestampModel, table=True):
    """
    Entidade que persiste o estado e modo de navegação da sessão do usuário WhatsApp.

    Attributes:
        id: Identificador primário da sessão.
        user_id: Identificador BSUID do usuário, único por sessão.
        wa_id: Telefone do usuário quando disponível (ausente para usuários com nome de usuário).
        mode: Modo ativo de atendimento ('menu' ou 'conversational').
        current_menu_id: Identificador do menu atualmente navegado (nulo se o menu for excluído).
        last_interaction_at: Carimbo de data/hora UTC da última interação do usuário.
    """

    __tablename__: Any = "user_sessions"

    id: int | None = Field(default=None, primary_key=True)
    user_id: str = Field(index=True, unique=True)
    wa_id: str | None = Field(default=None)
    mode: str = Field(default="menu")
    current_menu_id: int | None = Field(
        default=None, foreign_key="menus.id", ondelete="SET NULL"
    )
    last_interaction_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_type=UTCDateTime,
    )
