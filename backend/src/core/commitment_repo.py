"""Persistence for commitments — the things the assistant chases you about.

Postgres is the record. When DATABASE_URL is unset (local dev, tests) the
module falls back to a process-local dict so the nag loop still works end to
end; that fallback is lost on container sleep, which is why `db_backed()` is
surfaced through /api/commitments/health rather than hidden.

Every function is best-effort and never raises — a Neon hiccup must not stop a
reminder from going out, and must never crash the pipeline that created the
commitment.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from sqlalchemy import select

from .db import get_session, is_db_available
from .logging import get_logger
from ..models.commitment import CommitmentDB, CommitmentStatus

logger = get_logger("core.commitment_repo")

# Fallback store keyed by str(id). Only consulted when Postgres is unavailable.
_MEM: Dict[str, CommitmentDB] = {}


def db_backed() -> bool:
    return is_db_available()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    """Rows written before a tz-aware default, or read back from a driver that
    drops tzinfo, would blow up every comparison in the nag loop."""
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def to_dict(c: CommitmentDB) -> Dict[str, Any]:
    def iso(dt: Optional[datetime]) -> Optional[str]:
        d = _aware(dt)
        return d.isoformat() if d else None

    return {
        "id": str(c.id),
        "short_id": str(c.id)[:8],
        "title": c.title,
        "detail": c.detail,
        "source": c.source,
        "task_id": str(c.task_id) if c.task_id else None,
        "status": c.status,
        "due_at": iso(c.due_at),
        "nag_interval_sec": c.nag_interval_sec,
        "nag_count": c.nag_count,
        "escalation": c.escalation,
        "last_nagged_at": iso(c.last_nagged_at),
        "snooze_until": iso(c.snooze_until),
        "artifact_kind": c.artifact_kind,
        "artifact_url": c.artifact_url,
        "artifact_text": c.artifact_text,
        "completed_at": iso(c.completed_at),
        "created_at": iso(c.created_at),
        "overdue_sec": max(0, int((_now() - _aware(c.due_at)).total_seconds()))
        if c.due_at and c.status == CommitmentStatus.OPEN.value
        else 0,
    }


async def create(
    title: str,
    due_at: datetime,
    detail: Optional[str] = None,
    source: str = "manual",
    task_id: Optional[UUID] = None,
    nag_interval_sec: int = 1800,
) -> Optional[CommitmentDB]:
    row = CommitmentDB(
        id=uuid4(),
        title=title.strip()[:500],
        detail=(detail or "").strip()[:4000] or None,
        source=source,
        task_id=task_id,
        status=CommitmentStatus.OPEN.value,
        due_at=due_at,
        nag_interval_sec=max(300, int(nag_interval_sec)),
        created_at=_now(),
        updated_at=_now(),
    )
    if not is_db_available():
        _MEM[str(row.id)] = row
        return row
    try:
        async with get_session() as session:
            session.add(row)
        return row
    except Exception as exc:
        logger.warning("commitment_create_failed", error=str(exc))
        _MEM[str(row.id)] = row
        return row


async def list_all(
    status: Optional[str] = None,
    limit: int = 200,
) -> List[CommitmentDB]:
    if not is_db_available():
        rows = list(_MEM.values())
        if status:
            rows = [r for r in rows if r.status == status]
        rows.sort(key=lambda r: _aware(r.due_at) or _now())
        return rows[:limit]
    try:
        async with get_session() as session:
            stmt = select(CommitmentDB)
            if status:
                stmt = stmt.where(CommitmentDB.status == status)
            stmt = stmt.order_by(CommitmentDB.due_at.asc()).limit(limit)
            return list((await session.execute(stmt)).scalars().all())
    except Exception as exc:
        logger.warning("commitment_list_failed", error=str(exc))
        return []


async def get(commitment_id: UUID) -> Optional[CommitmentDB]:
    if not is_db_available():
        return _MEM.get(str(commitment_id))
    try:
        async with get_session() as session:
            return await session.get(CommitmentDB, commitment_id)
    except Exception as exc:
        logger.warning("commitment_get_failed", id=str(commitment_id), error=str(exc))
        return None


async def resolve_ref(ref: str) -> Optional[CommitmentDB]:
    """Look up by full uuid or by the 8-char short id people actually type."""
    ref = (ref or "").strip().lower().lstrip("#")
    if not ref:
        return None
    try:
        return await get(UUID(ref))
    except (ValueError, AttributeError):
        pass
    for row in await list_all(status=CommitmentStatus.OPEN.value, limit=500):
        if str(row.id).lower().startswith(ref):
            return row
    for row in await list_all(limit=500):
        if str(row.id).lower().startswith(ref):
            return row
    return None


async def due_for_nag(now: Optional[datetime] = None) -> List[CommitmentDB]:
    """Open commitments whose due time has passed and whose nag interval has
    elapsed since the last reminder (snooze respected)."""
    now = now or _now()
    rows = await list_all(status=CommitmentStatus.OPEN.value, limit=500)
    out: List[CommitmentDB] = []
    for r in rows:
        due = _aware(r.due_at)
        if due is None or due > now:
            continue
        snooze = _aware(r.snooze_until)
        if snooze is not None and snooze > now:
            continue
        last = _aware(r.last_nagged_at)
        if last is not None and (now - last) < timedelta(seconds=r.nag_interval_sec):
            continue
        out.append(r)
    return out


async def _mutate(commitment_id: UUID, **fields: Any) -> Optional[CommitmentDB]:
    if not is_db_available():
        row = _MEM.get(str(commitment_id))
        if row is None:
            return None
        for k, v in fields.items():
            setattr(row, k, v)
        row.updated_at = _now()
        return row
    try:
        async with get_session() as session:
            row = await session.get(CommitmentDB, commitment_id)
            if row is None:
                return None
            for k, v in fields.items():
                setattr(row, k, v)
            row.updated_at = _now()
            session.add(row)
            return row
    except Exception as exc:
        logger.warning("commitment_update_failed", id=str(commitment_id), error=str(exc))
        return None


async def mark_nagged(
    commitment_id: UUID, next_interval_sec: int, escalation: int
) -> Optional[CommitmentDB]:
    row = await get(commitment_id)
    if row is None:
        return None
    return await _mutate(
        commitment_id,
        nag_count=(row.nag_count or 0) + 1,
        last_nagged_at=_now(),
        nag_interval_sec=max(300, int(next_interval_sec)),
        escalation=escalation,
        snooze_until=None,
    )


async def complete(
    commitment_id: UUID,
    artifact_kind: str,
    artifact_url: Optional[str] = None,
    artifact_text: Optional[str] = None,
) -> Optional[CommitmentDB]:
    """Close a commitment. Callers MUST pass an artifact — a bare 'done' is
    rejected upstream, which is the entire point of this feature."""
    if not artifact_url and not (artifact_text or "").strip():
        return None
    return await _mutate(
        commitment_id,
        status=CommitmentStatus.DONE.value,
        artifact_kind=artifact_kind,
        artifact_url=artifact_url,
        artifact_text=(artifact_text or "")[:8000] or None,
        completed_at=_now(),
        snooze_until=None,
    )


async def snooze(commitment_id: UUID, minutes: int) -> Optional[CommitmentDB]:
    minutes = max(5, min(int(minutes), 720))
    return await _mutate(commitment_id, snooze_until=_now() + timedelta(minutes=minutes))


async def drop(commitment_id: UUID) -> Optional[CommitmentDB]:
    return await _mutate(
        commitment_id, status=CommitmentStatus.DROPPED.value, completed_at=_now()
    )


async def stats() -> Dict[str, int]:
    rows = await list_all(limit=500)
    now = _now()
    open_rows = [r for r in rows if r.status == CommitmentStatus.OPEN.value]
    return {
        "open": len(open_rows),
        "overdue": len([r for r in open_rows if (_aware(r.due_at) or now) <= now]),
        "done": len([r for r in rows if r.status == CommitmentStatus.DONE.value]),
        "dropped": len([r for r in rows if r.status == CommitmentStatus.DROPPED.value]),
        "total": len(rows),
    }
