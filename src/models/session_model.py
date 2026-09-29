"""
Modelo de dados para persistência de sessões administrativas no SQLite.
"""

from datetime import datetime, timezone
from typing import Optional, Literal
from sqlmodel import SQLModel, Field


class AdminSession(SQLModel, table=True):
    """
    Representa uma sessão ativa de administrador autenticado no painel web.
    """

    __tablename__: Literal["admin_sessions"] = "admin_sessions"  # pyright: ignore[reportIncompatibleVariableOverride,reportAssignmentType]

    id: str = Field(primary_key=True, description="Token criptográfico único da sessão")
    user_id: int = Field(
        index=True,
        foreign_key="users.id",
        description="Identificador do usuário administrador proprietário",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Data e hora de criação da sessão em UTC",
    )
    expires_at: datetime = Field(
        index=True,
        description="Data e hora limite de expiração da sessão em UTC",
    )
    ip_address: Optional[str] = Field(
        default=None,
        description="Endereço IP de origem da conexão",
    )
    user_agent: Optional[str] = Field(
        default=None,
        description="Cabeçalho User-Agent do navegador solicitante",
    )
