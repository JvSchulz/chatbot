from datetime import datetime, timezone
from sqlmodel import SQLModel, Field
from sqlalchemy import func

from src.models.types import UTCDateTime


class TimestampModel(SQLModel):
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_type=UTCDateTime,
        sa_column_kwargs={"server_default": func.now()},
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_type=UTCDateTime,
        sa_column_kwargs={"server_default": func.now(), "onupdate": func.now()},
    )
