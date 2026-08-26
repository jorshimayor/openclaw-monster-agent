from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Integer, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, validates

from ..core.db import Base


class CommitmentStatus(str, Enum):
    OPEN = "open"
    DONE = "done"
    DROPPED = "dropped"


class CommitmentDB(Base):
    """A thing the user said they would do, that the assistant keeps chasing.

    The row is the nag state machine: `due_at` opens the chase, every reminder
    bumps `nag_count`/`escalation` and stamps `last_nagged_at`, and NOTHING
    closes it except an artifact (a link, a file, or a chunk of pasted text).
    `snooze_until` only delays the next reminder — it never clears the row.
    """

    __tablename__ = "commitments"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # "task" (extracted from a pipeline report), "manual" (API), "telegram" (/add)
    source: Mapped[str] = mapped_column(Text, default="manual")
    task_id: Mapped[Optional[UUID]] = mapped_column(PGUUID(as_uuid=True), nullable=True, index=True)

    status: Mapped[str] = mapped_column(Text, default=CommitmentStatus.OPEN.value, index=True)

    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    nag_interval_sec: Mapped[int] = mapped_column(Integer, default=1800)
    nag_count: Mapped[int] = mapped_column(Integer, default=0)
    escalation: Mapped[int] = mapped_column(Integer, default=0)
    last_nagged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    snooze_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Proof of work. `artifact_kind` is link | file | text.
    artifact_kind: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    artifact_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    artifact_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    @validates("status")
    def _validate_status(self, _key: str, value: Any) -> str:
        if isinstance(value, CommitmentStatus):
            return value.value
        if isinstance(value, str):
            allowed = {s.value for s in CommitmentStatus}
            if value not in allowed:
                raise ValueError(f"invalid commitment status: {value!r} not in {sorted(allowed)}")
            return value
        raise TypeError(f"status must be CommitmentStatus or str, got {type(value).__name__}")

    @property
    def has_artifact(self) -> bool:
        return bool(self.artifact_url or (self.artifact_text or "").strip())
