"""Where you have got to on an ordered track.

The order lives in config and belongs in git, because the order is an
opinion. The cursor does not: it is progress, it changes from a phone, and a
container restart must not lose it.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Integer, Text, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base


class TrackStateDB(Base):
    __tablename__ = "track_state"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    track_key: Mapped[str] = mapped_column(Text, unique=True, nullable=False, index=True)
    cursor_key: Mapped[str] = mapped_column(Text, nullable=False)
    completed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    finished_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def to_dict(self) -> dict:
        return {
            "track": self.track_key,
            "cursor": self.cursor_key,
            "completed": self.completed,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
