from __future__ import annotations

from datetime import date as date_cls, datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import Date, DateTime, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base


class DayBlockStateDB(Base):
    """Whether one timetable block was done on one day.

    The template lives in a matrix sheet where a single cell is shared across
    all seven weekdays, so there is nowhere to record "I did Deep Block 1 on
    Thursday" without corrupting every other day. This table holds that
    per-day state instead, keyed by the block's slot and label so it survives
    the sheet being reordered.
    """

    __tablename__ = "day_block_state"
    __table_args__ = (UniqueConstraint("day", "slot", "label", name="uq_day_block"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    day: Mapped[date_cls] = mapped_column(Date, nullable=False, index=True)
    slot: Mapped[str] = mapped_column(Text, nullable=False)   # "05:45"
    label: Mapped[str] = mapped_column(Text, nullable=False)  # "90 min Deep Block 1"
    done_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
