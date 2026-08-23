from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict, List, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ...agents.bus import get_event_bus
from ...core.logging import get_logger
from ...core.task_repo import load_recent_tasks, load_task, save_task
from ...core.types import Task, TaskStatus
from ..sse import EventSourceResponse

logger = get_logger(__name__)
router = APIRouter(prefix="/api/tasks", tags=["tasks"])

_TASK_STORE: Dict[str, Task] = {}


class CreateTaskRequest(BaseModel):
    description: str


def _get_executor(request: Request) -> Any:
    return getattr(request.app.state, "pipeline_executor", None)


@router.get("", response_model=List[Task])
async def list_tasks(
    request: Request,
    skip: int = 0,
    limit: int = 50,
):
    logger.info("tasks_list_requested", skip=skip, limit=limit)
    # Postgres is the durable record; overlay hot in-memory copies (fresher
    # for tasks currently running in this process).
    merged: Dict[str, Task] = {str(t.id): t for t in await load_recent_tasks(limit=max(1, limit + skip))}
    merged.update({tid: t for tid, t in _TASK_STORE.items()})
    items = list(merged.values())
    items.sort(
        key=lambda t: (
            t.outputs.get("created_at") if isinstance(t.outputs, dict) else ""
        ),
        reverse=True,
    )
    if skip < 0:
        skip = 0
    if limit <= 0 or limit > 50:
        limit = 50
    return items[skip : skip + limit]


@router.post("", response_model=Task, status_code=201)
async def create_task(
    request: Request,
    body: CreateTaskRequest,
):
    logger.info("task_create_requested", description_len=len(body.description))
    if not body.description or not body.description.strip():
        raise HTTPException(status_code=400, detail="description cannot be empty")
    task = Task(
        id=uuid4(),
        description=body.description,
        status=TaskStatus.QUEUED,
        step=None,
        outputs={},
    )
    tid = str(task.id)
    task.outputs["created_at"] = datetime.now(timezone.utc).isoformat()
    _TASK_STORE[tid] = task
    await save_task(task)  # durable row exists before we return the id
    executor = _get_executor(request)

    # ── Notify Personal Assistant Agent: TASK_CREATED ──────────────────
    try:
        bus = get_event_bus()
        bus.emit_task_created(tid, body.description)
    except Exception as exc:
        logger.warning("task_create_bus_emit_failed", error=str(exc))

    async def _event_callback(event: Dict[str, Any]) -> None:
        stored = _TASK_STORE.get(tid)
        if stored is None:
            return
        if not isinstance(stored.outputs, dict):
            stored.outputs = {}
        buf: List[Dict[str, Any]] = stored.outputs.setdefault("event_buffer", [])
        buf.append(event)
        # Write-through: ~a dozen events per pipeline run, so persisting each
        # keeps Postgres current at negligible cost.
        await save_task(stored)

    async def _run_pipeline() -> None:
        if executor is None:
            stored = _TASK_STORE.get(tid)
            if stored is not None:
                stored.status = TaskStatus.FAILED
                stored.outputs["error"] = "Pipeline executor not initialized"
            logger.warning("pipeline_executor_missing", task_id=tid)
            try:
                get_event_bus().emit_task_failed(
                    tid, body.description,
                    "Pipeline executor not initialized in app.state",
                )
            except Exception:
                pass
            return
        try:
            current = _TASK_STORE.get(tid)
            if current is not None:
                current.status = TaskStatus.RUNNING
                await save_task(current)
            try:
                bus = get_event_bus()
                bus.emit(
                    type("AgentBusEvent", (), {})()
                ) if False else None  # no-op; pipeline_start handled in executor._emit
            except Exception:
                pass
            await executor.run(task, event_callback=_event_callback)

            final_status = task.status
            final_conf = 0.0
            final_report = ""
            if isinstance(task.outputs, dict):
                final_conf = float(task.outputs.get("overall_confidence", 0.0))
                final_report = str(task.outputs.get("final_report", ""))
            if final_status == TaskStatus.COMPLETED:
                try:
                    get_event_bus().emit_task_completed(
                        tid, body.description, final_conf, final_report,
                    )
                except Exception:
                    pass
            elif final_status in (TaskStatus.FAILED, TaskStatus.CANCELLED):
                err_msg = final_report or str(task.outputs.get("error", "")) or "Unknown"
                try:
                    if final_status == TaskStatus.CANCELLED:
                        # CANCELLED is P2 (not a crash)
                        from ...core.types import AgentEventKind, AgentEventPriority, AgentBusEvent
                        get_event_bus().emit(AgentBusEvent(
                            kind=AgentEventKind.TASK_CANCELLED,
                            priority=AgentEventPriority.P2_UPDATE,
                            task_id=task.id,
                            title="Task cancelled",
                            summary=err_msg[:180],
                            details={"description": body.description, "error": err_msg},
                        ))
                    else:
                        get_event_bus().emit_task_failed(
                            tid, body.description, err_msg,
                        )
                except Exception:
                    pass
        except Exception as exc:
            logger.exception("pipeline_bg_task_failed", task_id=tid, error=str(exc))
            stored = _TASK_STORE.get(tid)
            if stored is not None:
                if stored.status not in (
                    TaskStatus.COMPLETED,
                    TaskStatus.CANCELLED,
                ):
                    stored.status = TaskStatus.FAILED
                if isinstance(stored.outputs, dict):
                    stored.outputs["pipeline_error"] = str(exc)
            try:
                get_event_bus().emit_task_failed(
                    tid, body.description, str(exc),
                )
            except Exception:
                pass
        finally:
            stored = _TASK_STORE.get(tid)
            if stored is not None and isinstance(stored.outputs, dict):
                stored.outputs["_stream_done"] = True
            if stored is not None:
                await save_task(stored)  # final durable state

    asyncio.create_task(_run_pipeline())
    return task


@router.get("/{task_id}", response_model=Task)
async def get_task(
    request: Request,
    task_id: UUID,
):
    logger.info("task_get_requested", task_id=str(task_id))
    stored = _TASK_STORE.get(str(task_id))
    if stored is None:
        # Fall back to Postgres — the task may predate this container.
        stored = await load_task(task_id)
    if stored is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return stored


@router.get("/{task_id}/stream")
async def stream_task(
    request: Request,
    task_id: UUID,
):
    logger.info("task_stream_requested", task_id=str(task_id))
    stored = _TASK_STORE.get(str(task_id))
    if stored is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    sse = EventSourceResponse()

    async def _stream_generator() -> AsyncGenerator[bytes, None]:
        if not isinstance(stored.outputs, dict):
            stored.outputs = {}
        buf: List[Dict[str, Any]] = stored.outputs.setdefault("event_buffer", [])
        idx = 0
        try:
            await sse.send(
                {
                    "task_id": str(task_id),
                    "status": stored.status,
                    "message": "SSE stream opened for pipeline events.",
                },
                event="stream_open",
                id=sse.make_sse_id(),
            )
            while True:
                while idx < len(buf):
                    evt = buf[idx]
                    idx += 1
                    await sse.send(
                        evt.get("data", {}),
                        event=evt.get("step") or "event",
                        id=sse.make_sse_id(),
                    )
                done = stored.outputs.get("_stream_done", False)
                terminal = stored.status in (
                    TaskStatus.COMPLETED,
                    TaskStatus.FAILED,
                    TaskStatus.CANCELLED,
                )
                if done or terminal:
                    break
                await asyncio.sleep(0.1)
            await sse.send(
                {
                    "task_id": str(task_id),
                    "status": stored.status,
                    "final": True,
                },
                event="stream_end",
                id=sse.make_sse_id(),
            )
            await sse.close()
        except asyncio.CancelledError:
            try:
                await sse.close()
            except Exception:
                pass
            raise
        async for chunk in sse:
            yield chunk

    return StreamingResponse(
        _stream_generator(),
        status_code=sse.status_code,
        media_type=sse.media_type,
        headers=dict(sse.headers),
    )


@router.get("/{task_id}/cancel")
async def cancel_task(
    request: Request,
    task_id: UUID,
):
    logger.info("task_cancel_requested", task_id=str(task_id))
    stored = _TASK_STORE.get(str(task_id))
    if stored is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    executor = _get_executor(request)
    cancelled = False
    if executor is not None:
        cancelled = executor.cancel(str(task_id))
    if stored.status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
        pass
    else:
        stored.status = TaskStatus.CANCELLED
        await save_task(stored)
    return {
        "task_id": str(task_id),
        "cancelled": True,
        "executor_acknowledged": cancelled,
        "status": stored.status,
    }
