from __future__ import annotations

import asyncio
import html
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncGenerator, Dict, List, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ...agents.bus import get_event_bus
from ...core.config import get_settings
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
    merged: Dict[str, Task] = {
        str(t.id): t for t in await load_recent_tasks(limit=max(1, min(limit + skip, 500)))
    }
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
    # Clamp rather than reset: limit=200 used to silently become 50, which made
    # a "load more" control impossible to build against this endpoint.
    limit = max(1, min(limit, 200))
    return items[skip : skip + limit]


async def _handle_reminder(task: Task, request: Request) -> str:
    """File the reminder and confirm. No pipeline.

    Explicit reminders skip the approval gate: "remind me to X" IS the approval,
    and asking someone to confirm the reminder they just asked for is friction.
    """
    from ...agents.commitment_extractor import resolve_due, single_item_from_request
    from ...core import commitment_repo as c_repo
    from ...models.commitment import CommitmentStatus

    items = single_item_from_request(task.description)
    if not items:
        items = [{"title": task.description[:200], "day": "", "time_of_day": "", "at_time": ""}]

    filed = []
    for item in items:
        due = resolve_due(item.get("day", ""), item.get("time_of_day", ""), item.get("at_time", ""))
        row = await c_repo.create(
            title=item["title"],
            due_at=due,
            source="reminder",
            task_id=task.id,
            status=CommitmentStatus.OPEN.value,
        )
        if row is not None:
            filed.append((row, due))

    if not filed:
        return "I couldn't work out what to remind you about. Try: remind me to X at 5pm."

    lines = []
    for row, due in filed:
        local = due + timedelta(hours=get_settings().user_timezone_offset_hours)
        lines.append(
            f"Reminder set: **{row.title}** — {local.strftime('%a %d %b at %H:%M')} "
            f"(your time).\n\nI'll chase you until you tell me it's done."
        )
    return "\n\n".join(lines)


async def _handle_question(task: Task, request: Request) -> str:
    """One model turn. No pipeline, no commitments."""
    llm = getattr(request.app.state, "llm_router", None)
    if llm is None:
        return "I can't reach the model right now, so I can't answer that."
    from ...core import commitment_repo as c_repo
    from ...core.types import AgentRole
    from ...models.commitment import CommitmentStatus

    open_rows = await c_repo.list_all(status=CommitmentStatus.OPEN.value, limit=50)
    context = "\n".join(f"- {c.title} (due {c.due_at})" for c in open_rows) or "(nothing open)"
    prompt = (
        "Answer their question directly, in a few sentences. Plain language.\n"
        "Never mention agents, pipelines, or how you are built.\n"
        "Use only what is below; if the answer isn't here, say so.\n\n"
        f"What is currently on their hook:\n{context}\n\n"
        f"Their question: {task.description}\n\nAnswer:"
    )
    try:
        result = await llm.generate(prompt, AgentRole.PERSONAL_ASSISTANT)
        return str(result.get("response", "")).strip() or "I don't have an answer for that."
    except Exception as exc:
        logger.warning("question_answer_failed", error=str(exc))
        return "I couldn't reach the model to answer that."


async def _handle_schedule(task: Task, request: Request) -> str:
    from ...agents.schedule_sync import get_schedule_sync

    result = await get_schedule_sync().sync()
    if not result.get("ok"):
        return f"Couldn't sync your schedule sheet: {result.get('error')}"
    return (
        f"Schedule synced — {result['entries_seen']} entries read, "
        f"{result['filed']} new, {result['updated']} updated, "
        f"{result['closed_from_sheet']} already ticked off."
    )


@router.get("/count")
async def count_tasks() -> Dict[str, int]:
    """Total rows, so the console can paginate instead of guessing."""
    durable = await load_recent_tasks(limit=500)
    merged = {str(t.id) for t in durable} | set(_TASK_STORE.keys())
    return {"total": len(merged)}


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

    async def _finish_light(report: str) -> None:
        """Complete a task that never needed the pipeline."""
        stored = _TASK_STORE.get(tid)
        if stored is not None:
            stored.status = TaskStatus.COMPLETED
            if isinstance(stored.outputs, dict):
                stored.outputs["final_report"] = report
                stored.outputs["overall_confidence"] = 1.0
                stored.outputs["_stream_done"] = True
            await save_task(stored)
        try:
            get_event_bus().emit_task_completed(tid, body.description, 1.0, report)
        except Exception:
            pass
        try:
            from ...core import conversation_repo

            await conversation_repo.add(task.id, "assistant", report, meta={"kind": "brief"})
        except Exception:
            pass

    async def _run_pipeline() -> None:
        # Route first. A reminder does not need eleven steps, four agents and a
        # verifier — it needs one row in a table. Sending everything down the
        # same path is what produced Team Assembly tables for "pick Ibrahim up".
        try:
            from ...agents.intent import Intent, classify

            intent = await classify(body.description, getattr(request.app.state, "llm_router", None))
        except Exception as exc:
            logger.warning("intent_classify_failed", error=str(exc))
            intent = None

        if intent is not None and intent.kind != Intent.WORK:
            logger.info("task_routed", task_id=tid, intent=intent.kind, reason=intent.reason)
            handlers = {
                Intent.REMINDER: _handle_reminder,
                Intent.QUESTION: _handle_question,
                Intent.SCHEDULE: _handle_schedule,
            }
            try:
                report = await handlers[intent.kind](task, request)
            except Exception as exc:
                logger.exception("light_handler_failed", task_id=tid, error=str(exc))
                report = f"Something went wrong handling that: {exc}"
            await _finish_light(report)
            return

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
                # File the user's own action items so the assistant can chase
                # them. A plan that lands on Telegram and is never mentioned
                # again is a newsletter, not an assistant.
                try:
                    from ...agents.commitment_extractor import extract_and_file

                    filed = await extract_and_file(
                        body.description,
                        final_report,
                        task_id=task.id,
                        llm=getattr(request.app.state, "llm_router", None),
                    )
                    if filed:
                        await _announce_commitments(filed, body.description, task.id)
                except Exception as exc:
                    logger.warning("commitment_extract_failed", task_id=tid, error=str(exc))
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


async def _announce_commitments(
    filed: List[Dict[str, Any]], description: str, task_id: Optional[UUID] = None
) -> None:
    """Brief the user on what was proposed, and open the task's thread with it.

    Nothing here starts a reminder — these land as `proposed` and wait. The
    message says so explicitly, because an assistant that silently loads your
    hook is the thing that made the last version feel like spam.
    """
    from ...agents.nagger import get_nag_engine
    from ...agents.task_chat import compose_brief
    from ...core import commitment_repo as c_repo
    from ...core import conversation_repo

    console = get_settings().public_app_url.rstrip("/")
    link = f"{console}/tasks/{task_id}" if task_id else f"{console}/tasks"

    lines = [
        f"\U0001F4CB <b>{len(filed)} thing(s) to approve</b>",
        f"<i>from: {html.escape(description[:110])}</i>",
        "",
    ]
    for c in filed:
        due = str(c.get("due_at") or "")[:16].replace("T", " ")
        lines.append(
            f"  <code>{c['short_id']}</code> — {html.escape(str(c['title'])[:100])}\n"
            f"       <i>due {due} UTC</i>"
        )
    lines += [
        "",
        "<b>Nothing is chasing you yet.</b> Reply <code>/approve all</code> to start "
        "the reminders, <code>/approve &lt;id&gt;</code> for one, or "
        f'<a href="{link}">open the thread</a> to discuss it.',
    ]
    try:
        await get_nag_engine().send_message("\n".join(lines), silent=True)
    except Exception:
        pass

    if task_id is not None:
        try:
            rows = [c for c in await c_repo.list_all(limit=500) if c.task_id == task_id]
            proposed = [c for c in rows if c.status == "proposed"]
            await conversation_repo.add(
                task_id, "assistant", compose_brief(description, proposed),
                meta={"kind": "brief", "proposed": len(proposed)},
            )
        except Exception as exc:
            logger.warning("task_brief_failed", task_id=str(task_id), error=str(exc))


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


@router.delete("/{task_id}")
async def delete_task(request: Request, task_id: UUID) -> Dict[str, Any]:
    """Delete a task and everything it put on your hook.

    Cascades to commitments deliberately: a deleted task that leaves its
    extracted commitments behind means being nagged about work whose origin no
    longer exists.
    """
    from ...core.commitment_repo import delete_for_task
    from ...core.db import get_session, is_db_available
    from ...models.task import TaskDB

    executor = _get_executor(request)
    if executor is not None:
        try:
            executor.cancel(str(task_id))
        except Exception:
            pass

    from ...core.conversation_repo import delete_for_task as delete_messages

    commitments_removed = await delete_for_task(task_id)
    await delete_messages(task_id)
    in_memory = _TASK_STORE.pop(str(task_id), None) is not None

    row_removed = False
    if is_db_available():
        try:
            async with get_session() as session:
                row = await session.get(TaskDB, task_id)
                if row is not None:
                    await session.delete(row)
                    row_removed = True
        except Exception as exc:
            logger.warning("task_delete_failed", task_id=str(task_id), error=str(exc))

    if not row_removed and not in_memory:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    logger.info("task_deleted", task_id=str(task_id), commitments_removed=commitments_removed)
    return {
        "deleted": True,
        "id": str(task_id),
        "commitments_removed": commitments_removed,
    }


class ChatRequest(BaseModel):
    message: str


@router.get("/{task_id}/chat")
async def get_chat(task_id: UUID) -> Dict[str, Any]:
    from ...core import commitment_repo as c_repo
    from ...core import conversation_repo

    rows = await conversation_repo.history(task_id)
    commitments = [c for c in await c_repo.list_all(limit=500) if c.task_id == task_id]
    return {
        "task_id": str(task_id),
        "messages": [conversation_repo.to_dict(m) for m in rows],
        "commitments": [c_repo.to_dict(c) for c in commitments],
    }


@router.post("/{task_id}/chat")
async def post_chat(request: Request, task_id: UUID, body: ChatRequest) -> Dict[str, Any]:
    """Talk to the assistant about this task.

    The message is acted on first (approve, reschedule, drop, close with an
    artifact) and the reply describes only what actually changed.
    """
    from ...agents.task_chat import reply as chat_reply
    from ...core import commitment_repo as c_repo
    from ...core import conversation_repo

    text = (body.message or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="message cannot be empty")

    task = _TASK_STORE.get(str(task_id)) or await load_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    outputs = task.outputs if isinstance(task.outputs, dict) else {}

    prior = [conversation_repo.to_dict(m) for m in await conversation_repo.history(task_id)]
    await conversation_repo.add(task_id, "user", text)

    result = await chat_reply(
        task_id=task_id,
        message=text,
        task_description=task.description,
        report=str(outputs.get("final_report", "")),
        history=prior,
        llm=getattr(request.app.state, "llm_router", None),
    )
    await conversation_repo.add(
        task_id, "assistant", result["reply"], meta={"actions": result["actions"]}
    )
    return {
        "reply": result["reply"],
        "actions": result["actions"],
        "commitments": result["commitments"],
    }


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
