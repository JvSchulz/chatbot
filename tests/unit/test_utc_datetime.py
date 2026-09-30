"""
Testes unitários do tipo de coluna UTCDateTime (armazena UTC ingênuo, devolve UTC ciente).
"""

from datetime import datetime, timedelta, timezone
from sqlalchemy import Column, Integer, MetaData, Table, create_engine, text
from sqlalchemy.pool import StaticPool
from src.models.types import UTCDateTime

metadata = MetaData()
events = Table(
    "events",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("moment", UTCDateTime),
)


def _round_trip(value: datetime | None) -> tuple[datetime | None, str | None]:
    """Grava o valor em uma tabela temporária e devolve (valor lido, texto bruto no SQLite)."""
    engine = create_engine("sqlite://", poolclass=StaticPool)
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(events.insert().values(id=1, moment=value))
    with engine.connect() as connection:
        read = connection.execute(events.select()).one().moment
        raw = connection.execute(text("SELECT moment FROM events")).scalar()
    return read, raw


def test_aware_utc_value_comes_back_aware_utc():
    value = datetime(2026, 9, 29, 12, 30, 15, 123456, tzinfo=timezone.utc)

    read, _ = _round_trip(value)

    assert read == value
    assert read is not None and read.tzinfo is not None
    assert read.utcoffset() == timedelta(0)


def test_naive_value_is_treated_as_utc():
    read, raw = _round_trip(datetime(2026, 9, 29, 12, 30, 15))

    assert read == datetime(2026, 9, 29, 12, 30, 15, tzinfo=timezone.utc)
    assert raw is not None and raw.startswith("2026-09-29 12:30:15")


def test_other_timezone_is_converted_to_utc():
    minus_three = timezone(timedelta(hours=-3))

    read, raw = _round_trip(datetime(2026, 9, 29, 9, 30, 15, tzinfo=minus_three))

    assert read == datetime(2026, 9, 29, 12, 30, 15, tzinfo=timezone.utc)
    assert raw is not None and raw.startswith("2026-09-29 12:30:15")


def test_none_stays_none():
    read, raw = _round_trip(None)

    assert read is None
    assert raw is None
