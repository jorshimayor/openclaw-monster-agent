from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, validates

from ..core.db import Base


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"  # state changes worth showing in the thread


class TaskMessageDB(Base):
    """One turn in the conversation attached to a task.

    A task stops being a fire-and-forget job and becomes a thread: the
    assistant briefs you, you approve or push back, ask questions, or hand over
    an artifact — all against the same context.
    """

    __tablename__ = "task_messages"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Actions the turn performed (approvals, reschedules, artifacts) so the UI
    # can render them without re-deriving intent from the prose.
    meta: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )

    @validates("role")
    def _validate_role(self, _key: str, value: Any) -> str:
        if isinstance(value, MessageRole):
            return value.value
        allowed = {r.value for r in MessageRole}
        if value not in allowed:
            raise ValueError(f"invalid message role: {value!r} not in {sorted(allowed)}")
        return value
