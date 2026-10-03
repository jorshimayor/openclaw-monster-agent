"""Study recommendations pushed in by other agents.

Separate from commitments on purpose. A commitment is something you have been
held to and will be chased for; a suggestion is something another agent thinks
you should learn next. Filing the second as the first is how you end up with
forty reminders you never agreed to, which is the failure this whole system
already learned once.

So a suggestion sits in a queue, shows on /study, and becomes a commitment only
when you promote it.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Integer, Text, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base


class StudySuggestionDB(Base):
    __tablename__ = "study_suggestions"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)

    topic: Mapped[str] = mapped_column(Text, nullable=False)
    # Why this, now. The field that stops a suggestion being a bare link.
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Which part of the work this serves: build | audit | interview | write | fundamentals
    track: Mapped[str] = mapped_column(Text, default="fundamentals", nullable=False)
    # 1 highest. Used only for ordering, never for nagging.
    priority: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    est_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Who suggested it, so a bad source can be ignored wholesale later.
    suggested_by: Mapped[str] = mapped_column(Text, default="unknown", nullable=False)

    # queued | promoted | dismissed
    status: Mapped[str] = mapped_column(Text, default="queued", nullable=False)
    promoted_commitment_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "short_id": str(self.id)[:8],
            "topic": self.topic,
            "rationale": self.rationale,
            "url": self.url,
            "track": self.track,
            "priority": self.priority,
            "est_minutes": self.est_minutes,
            "suggested_by": self.suggested_by,
            "status": self.status,
            "promoted_commitment_id": (
                str(self.promoted_commitment_id) if self.promoted_commitment_id else None
            ),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


TRACKS = ("build", "audit", "interview", "write", "fundamentals")
STATUSES = ("queued", "promoted", "dismissed")
