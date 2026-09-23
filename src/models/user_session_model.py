from typing import Any
from datetime import datetime, timezone
from sqlmodel import Field
from src.models.timestamp_model import TimestampModel


class UserSession(TimestampModel, table=True):
    """
    Entidade que persiste o estado e modo de navegação da sessão do usuário WhatsApp.

    Attributes:
        id: Identificador primário da sessão.
        wa_id: Identificador WhatsApp do remetente (telefone com DDD).
        mode: Modo ativo de atendimento ('menu' ou 'conversational').
        current_menu_id: Identificador do menu atualmente navegado.
        last_interaction_at: Carimbo de data/hora UTC da última interação do usuário.
    """

    __tablename__: Any = "user_sessions"

    id: int | None = Field(default=None, primary_key=True)
    wa_id: str = Field(index=True, unique=True)
    mode: str = Field(default="menu")
    current_menu_id: int | None = Field(default=None, foreign_key="menus.id")
    last_interaction_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
