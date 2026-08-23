"""Notification diagnostics — exercise the task-completed alert path
(Telegram + Slack) inside the running process and return the raw result.
Exists because notification failures are otherwise silent: the bus catches
everything so the pipeline never breaks on a notify error.
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter

from ...agents.bus import get_event_bus
from ...core.logging import get_logger
from ...core.types import AgentBusEvent, AgentEventKind, AgentEventPriority

logger = get_logger("api.notify")

router = APIRouter(prefix="/api/notify", tags=["notify"])


@router.post("/test")
async def notify_test() -> Dict[str, Any]:
    bus = get_event_bus()
    state: Dict[str, Any] = {
        "bus_started": bus._started,
        "pa_ready": bus._pa is not None,
        "queue_size": bus._queue.qsize(),
        "worker_alive": bus._worker_task is not None and not bus._worker_task.done(),
    }
    if bus._pa is None:
        state["result"] = {"error": "personal assistant not attached to bus"}
        return state
    state["pa_mcp_attached"] = getattr(bus._pa, "_mcp_manager", None) is not None
    event = AgentBusEvent(
        kind=AgentEventKind.TASK_COMPLETED,
        priority=AgentEventPriority.P2_UPDATE,
        title="Notification test · conf 100%",
        summary="This is a notification-path test fired from /api/notify/test — if you can read this on Telegram and Slack, completion alerts are working.",
        details={"description": "notification path test"},
    )
    try:
        state["result"] = await bus._pa.ingest_event(event)
    except Exception as exc:
        logger.exception("notify_test_failed", error=str(exc))
        state["result"] = {"error": str(exc)}
    return state
