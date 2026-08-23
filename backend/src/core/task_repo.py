"""Postgres persistence for pipeline tasks.

The API keeps a hot in-memory copy (SSE streaming, zero-latency polling), and
this module writes every state change through to Neon so tasks survive
container sleep, redeploys, and crashes. All functions are best-effort and
never raise: a Neon hiccup must not kill a running pipeline, and a missing
DATABASE_URL (local dev, unit tests) silently disables persistence.

Status mapping: the API enum is UPPERCASE and includes QUEUED; the tasks
table (migrations/0001) uses lowercase without QUEUED. QUEUED maps to
'pending' on write and 'pending' maps back to QUEUED on read.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, List, Optional
from uuid import UUID

from sqlalchemy import select

from .db import get_session, is_db_available
from .logging import get_logger
from .types import Task, TaskStatus
from ..models.task import TaskDB

logger = get_logger("core.task_repo")

_TO_DB = {
    "PENDING": "pending",
    "QUEUED": "pending",
    "RUNNING": "running",
    "COMPLETED": "completed",
    "FAILED": "failed",
    "CANCELLED": "cancelled",
}
_FROM_DB = {
    "pending": TaskStatus.QUEUED,
    "running": TaskStatus.RUNNING,
    "completed": TaskStatus.COMPLETED,
    "failed": TaskStatus.FAILED,
    "cancelled": TaskStatus.CANCELLED,
}

_TERMINAL_DB = {"completed", "failed", "cancelled"}


def _json_safe(obj: Any) -> Any:
    """Outputs may hold datetimes/enums from step states — round-trip through
    JSON with default=str so JSONB never rejects a write."""
    try:
        return json.loads(json.dumps(obj, default=str))
    except Exception:
        return {}


def _status_to_db(status: Any) -> str:
    s = status.value if hasattr(status, "value") else str(status)
    return _TO_DB.get(s, "pending")


def _step_str(step: Any) -> Optional[str]:
    if step is None:
        return None
    s = step.value if hasattr(step, "value") else str(step)
    return s[:128]


async def save_task(task: Task) -> None:
    """Upsert the API task's current state into Postgres."""
    if not is_db_available():
        return
    try:
        outputs = _json_safe(task.outputs if isinstance(task.outputs, dict) else {})
        s_db = _status_to_db(task.status)
        now = datetime.now(timezone.utc)
        async with get_session() as session:
            row = await session.get(TaskDB, task.id)
            if row is None:
                row = TaskDB(
                    id=task.id,
                    description=task.description,
                    status=s_db,
                    result=outputs,
                    current_step=_step_str(task.step),
                )
                if s_db == "running":
                    row.started_at = now
                session.add(row)
            else:
                row.status = s_db
                row.result = outputs
                row.current_step = _step_str(task.step)
                if s_db == "running" and row.started_at is None:
                    row.started_at = now
            if s_db in _TERMINAL_DB and row.completed_at is None:
                row.completed_at = now
                err = outputs.get("error") or outputs.get("pipeline_error") or ""
                row.error_message = str(err)[:2000] or None
    except Exception as exc:
        logger.warning("task_persist_failed", task_id=str(task.id), error=str(exc))


def _row_to_task(row: TaskDB) -> Task:
    outputs = dict(row.result) if isinstance(row.result, dict) else {}
    if row.created_at and "created_at" not in outputs:
        outputs["created_at"] = row.created_at.isoformat()
    return Task(
        id=row.id,
        description=row.description,
        status=_FROM_DB.get(row.status, TaskStatus.FAILED),
        step=None,  # step enums are pipeline-internal; terminal rows don't need one
        outputs=outputs,
    )


async def load_task(task_id: UUID) -> Optional[Task]:
    if not is_db_available():
        return None
    try:
        async with get_session() as session:
            row = await session.get(TaskDB, task_id)
            return _row_to_task(row) if row is not None else None
    except Exception as exc:
        logger.warning("task_load_failed", task_id=str(task_id), error=str(exc))
        return None


async def load_recent_tasks(limit: int = 50) -> List[Task]:
    if not is_db_available():
        return []
    try:
        async with get_session() as session:
            rows = (
                (
                    await session.execute(
                        select(TaskDB).order_by(TaskDB.created_at.desc()).limit(limit)
                    )
                )
                .scalars()
                .all()
            )
            return [_row_to_task(r) for r in rows]
    except Exception as exc:
        logger.warning("task_list_failed", error=str(exc))
        return []
