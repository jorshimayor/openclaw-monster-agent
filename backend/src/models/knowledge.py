from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID, uuid4

from sqlalchemy import DateTime, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base
from ..core.types import KnowledgeCrystals


class KnowledgeCrystalDB(Base):
    __tablename__ = "knowledge_crystals"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    source_task_id: Mapped[Optional[UUID]] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    entities: Mapped[List[str]] = mapped_column(ARRAY(Text), default=list)
    strategies: Mapped[List[str]] = mapped_column(ARRAY(Text), default=list)
    pitfalls: Mapped[List[str]] = mapped_column(ARRAY(Text), default=list)
    frameworks: Mapped[List[str]] = mapped_column(ARRAY(Text), default=list)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    raw_extras: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )

    def to_domain(self) -> KnowledgeCrystals:
        return KnowledgeCrystals(
            id=self.id,
            source_task_id=self.source_task_id,
            entities=list(self.entities or []),
            strategies=list(self.strategies or []),
            pitfalls=list(self.pitfalls or []),
            frameworks=list(self.frameworks or []),
            summary=self.summary or "",
            created_at=self.created_at or datetime.now(timezone.utc),
        )

    @classmethod
    def from_domain(cls, crystal: KnowledgeCrystals) -> "KnowledgeCrystalDB":
        def _pick_category() -> Optional[str]:
            buckets = [
                ("entities", crystal.entities),
                ("strategies", crystal.strategies),
                ("pitfalls", crystal.pitfalls),
                ("frameworks", crystal.frameworks),
            ]
            best = None
            best_len = 0
            for name, items in buckets:
                if len(items) > best_len:
                    best_len = len(items)
                    best = name
            return best

        return cls(
            id=crystal.id,
            source_task_id=crystal.source_task_id,
            entities=list(crystal.entities or []),
            strategies=list(crystal.strategies or []),
            pitfalls=list(crystal.pitfalls or []),
            frameworks=list(crystal.frameworks or []),
            summary=crystal.summary or None,
            category=_pick_category(),
            raw_extras={},
            created_at=crystal.created_at or datetime.now(timezone.utc),
        )
