from datetime import datetime, timezone
from typing import Any
from sqlalchemy import DateTime
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator


class UTCDateTime(TypeDecorator[datetime]):
    """
    Coluna de data e hora que grava UTC ingênuo e devolve sempre datetime ciente de UTC.

    O SQLite não guarda fuso horário. Este tipo concentra a conversão em um único ponto:
    valores ingênuos são tratados como UTC e valores de outros fusos são convertidos.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        """
        Converte o valor recebido para UTC ingênuo antes de gravar.

        Args:
            value: Data e hora ingênua (tratada como UTC), ciente de qualquer fuso, ou None.
            dialect: Dialeto do banco em uso.

        Returns:
            Data e hora em UTC sem informação de fuso, ou None.
        """
        if value is None:
            return None
        if value.tzinfo is None:
            return value
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(self, value: Any, dialect: Dialect) -> datetime | None:
        """
        Marca como UTC o valor lido do banco.

        Args:
            value: Data e hora ingênua lida do banco, ou None.
            dialect: Dialeto do banco em uso.

        Returns:
            Data e hora ciente de UTC, ou None.
        """
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc)
