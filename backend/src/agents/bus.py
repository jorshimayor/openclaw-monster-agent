from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict, List, Optional, TYPE_CHECKING

from ..core.logging import get_logger
from ..core.types import (
    AgentBusEvent,
    AgentEventKind,
    AgentEventPriority,
)
from . import get_agent
from .personal_assistant import PersonalAssistantAgent

if TYPE_CHECKING:
    from ..mcp.manager import McpServerManager

logger = get_logger("agents.bus")


class AgentEventBus:
    """In-process agent event bus. All agents report here → Personal Assistant dispatches.

    Intentionally tiny:
      - `emit(event)` — enqueue AgentBusEvent. Caller never blocks (fire-and-forget).
      - `on(kind, subscriber)` — register optional subscribers (future: Slack mirror, webhooks).
      - Singleton via `get_event_bus()`.
      - Worker runs a background task that pops events + invokes PersonalAssistantAgent.ingest_event()
        so notifications don't block the pipeline executor.
      - If P.A. fails or Telegram is unconfigured, events are still added to the P.A. digest
        queue AND all errors are swallowed/logged — pipeline never crashes because notif fails.
    """

    _instance: Optional["AgentEventBus"] = None

    def __init__(self) -> None:
        self._queue: "asyncio.Queue[AgentBusEvent]" = asyncio.Queue(maxsize=10_000)
        self._subscribers: Dict[AgentEventKind, List[Callable[[AgentBusEvent], Awaitable[Any] | Any]]] = {}
        self._worker_task: Optional[asyncio.Task[None]] = None
        self._pa: Optional[PersonalAssistantAgent] = None
        self._started = False
        self._log = logger

    @classmethod
    def instance(cls) -> "AgentEventBus":
        if cls._instance is None:
            cls._instance = AgentEventBus()
        return cls._instance

    # ── lifecycle ──────────────────────────────────────────────────────────

    def start(
        self,
        mcp_manager: Optional["McpServerManager"] = None,
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ) -> None:
        if self._started:
            return
        loop = loop or asyncio.get_event_loop_policy().get_event_loop()
        try:
            self._pa = get_agent("PERSONAL_ASSISTANT")  # type: ignore[assignment]
        except Exception as exc:  # pragma: no cover - safety
            self._log.exception("pa_instantiate_failed", error=str(exc))
            self._pa = None
        if self._pa is not None and mcp_manager is not None:
            try:
                self._pa.attach_mcp(mcp_manager)  # type: ignore[attr-defined]
            except Exception as exc:
                self._log.warning("pa_attach_mcp_failed", error=str(exc))
        self._worker_task = loop.create_task(self._run_worker())
        self._started = True
        self._log.info("agent_event_bus_started", pa_ready=self._pa is not None)

    async def stop(self) -> None:
        if self._worker_task is not None and not self._worker_task.done():
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        self._started = False
        self._log.info("agent_event_bus_stopped", queue_size=self._queue.qsize())

    # ── public API ────────────────────────────────────────────────────────

    def emit(self, event: AgentBusEvent) -> None:
        """Fire-and-forget event post. Never raises — always enqueues.

        The pipeline / REST handlers call this synchronously so their own
        latency is never affected by Telegram send times.
        """
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            self._log.warning("event_bus_queue_full", event_kind=event.kind.value, priority=event.priority.value)
        except Exception as exc:
            self._log.warning("event_bus_emit_failed", error=str(exc))

    # helpers (used by pipeline/_emit() to avoid building events by hand)

    def emit_task_created(self, task_id, description: str) -> None:
        self.emit(AgentBusEvent(
            kind=AgentEventKind.TASK_CREATED,
            priority=AgentEventPriority.P2_UPDATE,
            task_id=task_id,
            title="New task queued",
            summary=description[:200],
            details={"description": description},
        ))

    def emit_task_failed(self, task_id, description: str, error: str, source_agent_role=None) -> None:
        self.emit(AgentBusEvent(
            kind=AgentEventKind.TASK_FAILED,
            priority=AgentEventPriority.P0_CRITICAL,
            task_id=task_id,
            source_agent_role=source_agent_role,
            title="Task FAILED",
            summary=str(error)[:240],
            details={"description": description, "error": str(error)},
            action_items=[
                "Reply: /rerun <task_id>  to rerun",
                "Reply: /inspect <task_id>  to see logs + last output",
                "Reply: /cancel <task_id>  to stop future retries",
            ],
        ))

    def emit_task_completed(self, task_id, description: str, confidence: float, final_report: str) -> None:
        conf_pct = int(round((confidence or 0.0) * 100))
        self.emit(AgentBusEvent(
            kind=AgentEventKind.TASK_COMPLETED,
            priority=AgentEventPriority.P2_UPDATE,
            task_id=task_id,
            title=f"Task completed · conf {conf_pct}%",
            summary=str(final_report or description)[:320],
            details={
                "description": description,
                "report": str(final_report or "")[:3500],
                "overall_confidence": confidence,
                "final_report_preview": (final_report or "")[:280],
            },
            action_items=[
                "Reply: /view <task_id>  for full report",
                "Reply: /share <task_id> doc  to save as Google Doc",
                "Reply: /crystalize <task_id>  to extract knowledge crystal",
            ],
        ))

    def emit_pipeline_step(self, task_id, step_name: str, state: Dict[str, Any], description: str = "") -> None:
        # only milestone steps are worth P2; the rest are P3 digest-only
        milestone = step_name in (
            "pipeline_start", "step4_team", "step6_execution",
            "step8_quality_gate", "step10_synthesizer", "step11_reflection",
        )
        kind = AgentEventKind.PIPELINE_STEP
        priority = AgentEventPriority.P2_UPDATE if milestone else AgentEventPriority.P3_INFO
        preview = ""
        if isinstance(state, dict):
            for k in ("status", "overall", "outputs", "passed", "seconds", "waves"):
                if k in state:
                    preview += f"{k}={state[k]}; "
        self.emit(AgentBusEvent(
            kind=kind,
            priority=priority,
            task_id=task_id,
            title=f"Step · {step_name}",
            summary=preview[:160] or description[:160] or step_name,
            details={"step": step_name, "description": description, "state": state or {}},
        ))

    def emit_integration(self, name: str, status: str, message: str = "") -> None:
        if status == "healthy":
            kind = AgentEventKind.MANUAL_NOTIFY
            priority = AgentEventPriority.P3_INFO
        elif status == "degraded":
            kind = AgentEventKind.INTEGRATION_DEGRADED
            priority = AgentEventPriority.P1_ACTION
        else:
            kind = AgentEventKind.INTEGRATION_DOWN
            priority = AgentEventPriority.P0_CRITICAL
        self.emit(AgentBusEvent(
            kind=kind,
            priority=priority,
            integration=name,
            title=f"Integration {name}: {status}",
            summary=str(message)[:180] or f"{name} is now {status}",
            details={"integration": name, "status": status, "message": message},
        ))

    def emit_knowledge_crystal(self, crystal_id, summary: str, task_id=None) -> None:
        self.emit(AgentBusEvent(
            kind=AgentEventKind.KNOWLEDGE_CRYSTAL,
            priority=AgentEventPriority.P2_UPDATE,
            task_id=task_id,
            title="New knowledge crystal",
            summary=str(summary)[:200],
            details={"crystal_id": str(crystal_id), "summary": summary, "task_id": str(task_id) if task_id else None},
        ))

    def on(self, kind: AgentEventKind, subscriber: Callable[[AgentBusEvent], Awaitable[Any] | Any]) -> None:
        self._subscribers.setdefault(kind, []).append(subscriber)

    # ── worker ────────────────────────────────────────────────────────────

    async def _run_worker(self) -> None:
        self._log.info("agent_event_bus_worker_start")
        while True:
            try:
                event = await self._queue.get()
            except asyncio.CancelledError:
                break
            try:
                await self._dispatch(event)
            except Exception as exc:
                self._log.exception("event_bus_dispatch_error", kind=event.kind.value, error=str(exc))
            finally:
                self._queue.task_done()

    async def _dispatch(self, event: AgentBusEvent) -> None:
        subs = self._subscribers.get(event.kind, []) + self._subscribers.get("*", [])  # type: ignore[arg-type]
        for sub in subs:
            try:
                maybe_coro = sub(event)
                if asyncio.iscoroutine(maybe_coro):
                    await maybe_coro
            except Exception as exc:
                self._log.warning("event_bus_subscriber_failed", error=str(exc))

        if self._pa is not None:
            try:
                await self._pa.ingest_event(event)
            except Exception as exc:
                # Do NOT let a Telegram failure drop digest info: enqueueing to P.A.
                # _digest_events deque already happened inside ingest_event if possible,
                # but catch-all here just in case.
                self._log.warning("pa_ingest_failed", kind=event.kind.value, error=str(exc))


def get_event_bus() -> AgentEventBus:
    return AgentEventBus.instance()
