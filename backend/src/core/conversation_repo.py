"""Persistence for per-task conversations. Best-effort, like the other repos."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from sqlalchemy import select

from .commitment_repo import StorageUnavailable, memory_fallback_allowed
from .db import get_session, is_db_available
from .logging import get_logger
from ..models.conversation import MessageRole, TaskMessageDB

logger = get_logger("core.conversation_repo")

_MEM: Dict[str, List[TaskMessageDB]] = {}


def to_dict(m: TaskMessageDB) -> Dict[str, Any]:
    created = m.created_at
    if created is not None and created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return {
        "id": str(m.id),
        "task_id": str(m.task_id),
        "role": m.role,
        "content": m.content,
        "meta": m.meta or {},
        "created_at": created.isoformat() if created else None,
    }


async def add(
    task_id: UUID,
    role: str,
    content: str,
    meta: Optional[Dict[str, Any]] = None,
) -> Optional[TaskMessageDB]:
    row = TaskMessageDB(
        id=uuid4(),
        task_id=task_id,
        role=role.value if isinstance(role, MessageRole) else role,
        content=str(content)[:20000],
        meta=meta or None,
        created_at=datetime.now(timezone.utc),
    )
    if not is_db_available():
        if not memory_fallback_allowed():
            raise StorageUnavailable(
                "DATABASE_URL is configured but unavailable — refusing to keep the "
                "conversation in process memory, where it would vanish on restart."
            )
        _MEM.setdefault(str(task_id), []).append(row)
        return row
    try:
        async with get_session() as session:
            session.add(row)
        return row
    except Exception as exc:
        logger.error("message_add_failed", task_id=str(task_id), error=str(exc))
        raise StorageUnavailable(f"could not persist message: {exc}") from exc


async def history(task_id: UUID, limit: int = 100) -> List[TaskMessageDB]:
    if not is_db_available():
        return _MEM.get(str(task_id), [])[-limit:]
    try:
        async with get_session() as session:
            rows = (
                (
                    await session.execute(
                        select(TaskMessageDB)
                        .where(TaskMessageDB.task_id == task_id)
                        .order_by(TaskMessageDB.created_at.asc())
                        .limit(limit)
                    )
                )
                .scalars()
                .all()
            )
            return list(rows)
    except Exception as exc:
        logger.warning("message_history_failed", task_id=str(task_id), error=str(exc))
        return []


async def delete_for_task(task_id: UUID) -> int:
    if not is_db_available():
        return len(_MEM.pop(str(task_id), []))
    try:
        async with get_session() as session:
            rows = (
                (await session.execute(select(TaskMessageDB).where(TaskMessageDB.task_id == task_id)))
                .scalars()
                .all()
            )
            for row in rows:
                await session.delete(row)
            return len(rows)
    except Exception as exc:
        logger.warning("message_delete_failed", task_id=str(task_id), error=str(exc))
        return 0
