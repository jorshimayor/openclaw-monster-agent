"""Per-day completion state for timetable blocks. Best-effort, never raises."""

from __future__ import annotations

from datetime import date as date_cls, datetime, timezone
from typing import Dict, List, Optional, Tuple
from uuid import uuid4

from sqlalchemy import select

from . import commitment_repo
from .commitment_repo import StorageUnavailable
from .db import get_session, is_db_available
from .logging import get_logger
from ..models.day_block import DayBlockStateDB

logger = get_logger("core.day_block_repo")

_MEM: Dict[Tuple[str, str, str], DayBlockStateDB] = {}


def _key(day: date_cls, slot: str, label: str) -> Tuple[str, str, str]:
    return (day.isoformat(), slot, label)


async def done_slots(day: date_cls) -> List[Dict[str, str]]:
    """[{slot, label}] completed on that day."""
    if not is_db_available():
        return [
            {"slot": r.slot, "label": r.label}
            for k, r in _MEM.items()
            if k[0] == day.isoformat() and r.done_at is not None
        ]
    try:
        async with get_session() as session:
            rows = (
                (
                    await session.execute(
                        select(DayBlockStateDB).where(DayBlockStateDB.day == day)
                    )
                )
                .scalars()
                .all()
            )
            return [{"slot": r.slot, "label": r.label} for r in rows if r.done_at is not None]
    except Exception as exc:
        logger.warning("day_block_read_failed", day=str(day), error=str(exc))
        return []


async def set_done(day: date_cls, slot: str, label: str, done: bool) -> bool:
    """Tick or untick one block on one day. Idempotent."""
    now = datetime.now(timezone.utc) if done else None

    if not is_db_available():
        if not commitment_repo.memory_fallback_allowed():
            raise StorageUnavailable(
                "DATABASE_URL is configured but unavailable — refusing to record "
                "block state in process memory, where it would vanish on restart."
            )
        key = _key(day, slot, label)
        row = _MEM.get(key) or DayBlockStateDB(
            id=uuid4(), day=day, slot=slot, label=label, created_at=datetime.now(timezone.utc)
        )
        row.done_at = now
        _MEM[key] = row
        return done

    try:
        async with get_session() as session:
            existing = (
                (
                    await session.execute(
                        select(DayBlockStateDB).where(
                            DayBlockStateDB.day == day,
                            DayBlockStateDB.slot == slot,
                            DayBlockStateDB.label == label,
                        )
                    )
                )
                .scalars()
                .first()
            )
            if existing is None:
                existing = DayBlockStateDB(
                    id=uuid4(), day=day, slot=slot, label=label,
                    created_at=datetime.now(timezone.utc),
                )
                session.add(existing)
            existing.done_at = now
        return done
    except Exception as exc:
        logger.error("day_block_write_failed", day=str(day), error=str(exc))
        raise StorageUnavailable(f"could not record block state: {exc}") from exc


async def clear_day(day: date_cls) -> int:
    if not is_db_available():
        doomed = [k for k in _MEM if k[0] == day.isoformat()]
        for k in doomed:
            _MEM.pop(k, None)
        return len(doomed)
    try:
        async with get_session() as session:
            rows = (
                (await session.execute(select(DayBlockStateDB).where(DayBlockStateDB.day == day)))
                .scalars()
                .all()
            )
            for row in rows:
                await session.delete(row)
            return len(rows)
    except Exception as exc:
        logger.warning("day_block_clear_failed", day=str(day), error=str(exc))
        return 0
