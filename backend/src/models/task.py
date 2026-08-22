from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional
from uuid import UUID, uuid4

from sqlalchemy import DateTime, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, validates

from ..core.db import Base


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskDB(Base):
    __tablename__ = "tasks"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        Text,
        default=TaskStatus.PENDING.value,
        index=True,
    )
    plan: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    result: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    current_step: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    progress_pct: Mapped[int] = mapped_column(default=0)
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    @validates("status")
    def _validate_status(self, _key: str, value: Any) -> str:
        if isinstance(value, TaskStatus):
            return value.value
        if isinstance(value, str):
            allowed = {s.value for s in TaskStatus}
            if value not in allowed:
                raise ValueError(f"invalid task status: {value!r} not in {sorted(allowed)}")
            return value
        raise TypeError(f"status must be TaskStatus or str, got {type(value).__name__}")
