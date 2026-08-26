"""Commitments — the assistant's accountability ledger.

Every open row here is something the user said they would do. The nag engine
chases each one on an escalating schedule and NOTHING closes a row except an
artifact (see core/artifact.py). `/tick` is the cron entry point: it wakes a
sleeping container and runs one reminder round.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ...agents.commitment_extractor import extract_and_file, resolve_due
from ...agents.nagger import get_nag_engine, ladder_for
from ...core import commitment_repo as repo
from ...core.artifact import classify
from ...core.logging import get_logger
from ...core.task_repo import load_task

logger = get_logger("api.commitments")
router = APIRouter(prefix="/api/commitments", tags=["commitments"])


class CreateCommitmentRequest(BaseModel):
    title: str
    detail: Optional[str] = None
    # Give a due time any one of three ways; first one present wins.
    due_at: Optional[datetime] = None
    due_in_minutes: Optional[int] = None
    day: Optional[str] = None
    time_of_day: Optional[str] = None
    nag_interval_sec: int = Field(default=1800, ge=300, le=86_400)


class DoneRequest(BaseModel):
    artifact_url: Optional[str] = None
    artifact_text: Optional[str] = None


class SnoozeRequest(BaseModel):
    minutes: int = Field(default=30, ge=5, le=720)


class ExtractRequest(BaseModel):
    task_id: UUID


# ── static paths first: they must not be swallowed by /{commitment_id} ──────


@router.get("/health")
async def commitments_health() -> Dict[str, Any]:
    engine = get_nag_engine()
    return {
        "db_backed": repo.db_backed(),
        "nag": engine.state(),
        "stats": await repo.stats(),
    }


@router.post("/tick")
async def commitments_tick() -> Dict[str, Any]:
    """Run one reminder round. Called by the Cloudflare cron every few minutes
    so reminders keep firing even while the container is asleep."""
    return await get_nag_engine().tick()


@router.post("/extract")
async def commitments_extract(request: Request, body: ExtractRequest) -> Dict[str, Any]:
    """Re-run action-item extraction over a finished task's report."""
    task = await load_task(body.task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {body.task_id} not found")
    outputs = task.outputs if isinstance(task.outputs, dict) else {}
    report = str(outputs.get("final_report", ""))
    if not report.strip():
        raise HTTPException(status_code=400, detail="Task has no final report to extract from")
    filed = await extract_and_file(
        task.description,
        report,
        task_id=body.task_id,
        llm=getattr(request.app.state, "llm_router", None),
    )
    return {"task_id": str(body.task_id), "filed": len(filed), "commitments": filed}


@router.get("")
async def list_commitments(status: Optional[str] = None, limit: int = 200) -> List[Dict[str, Any]]:
    rows = await repo.list_all(status=status, limit=max(1, min(limit, 500)))
    return [repo.to_dict(r) for r in rows]


@router.post("", status_code=201)
async def create_commitment(body: CreateCommitmentRequest) -> Dict[str, Any]:
    if not body.title.strip():
        raise HTTPException(status_code=400, detail="title cannot be empty")

    if body.due_at is not None:
        due = body.due_at if body.due_at.tzinfo else body.due_at.replace(tzinfo=timezone.utc)
    elif body.due_in_minutes is not None:
        due = datetime.now(timezone.utc) + timedelta(minutes=max(0, body.due_in_minutes))
    else:
        due = resolve_due(body.day or "", body.time_of_day or "")

    row = await repo.create(
        title=body.title,
        due_at=due,
        detail=body.detail,
        source="manual",
        nag_interval_sec=body.nag_interval_sec,
    )
    if row is None:
        raise HTTPException(status_code=500, detail="could not persist commitment")
    return repo.to_dict(row)


@router.get("/{commitment_id}")
async def get_commitment(commitment_id: UUID) -> Dict[str, Any]:
    row = await repo.get(commitment_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Commitment {commitment_id} not found")
    return repo.to_dict(row)


@router.post("/{commitment_id}/done")
async def complete_commitment(commitment_id: UUID, body: DoneRequest) -> Dict[str, Any]:
    row = await repo.get(commitment_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Commitment {commitment_id} not found")

    verdict = classify(text=body.artifact_text or "", file_url=body.artifact_url)
    if not verdict["accepted"]:
        # 422, not 400: the request is well-formed, the evidence isn't good enough.
        raise HTTPException(status_code=422, detail=verdict["reason"])

    updated = await repo.complete(
        commitment_id,
        artifact_kind=verdict["kind"],
        artifact_url=verdict["url"] or body.artifact_url,
        artifact_text=verdict["text"],
    )
    if updated is None:
        raise HTTPException(status_code=500, detail="could not close commitment")
    logger.info("commitment_closed", id=str(commitment_id)[:8], kind=verdict["kind"])
    return repo.to_dict(updated)


@router.post("/{commitment_id}/snooze")
async def snooze_commitment(commitment_id: UUID, body: SnoozeRequest) -> Dict[str, Any]:
    updated = await repo.snooze(commitment_id, body.minutes)
    if updated is None:
        raise HTTPException(status_code=404, detail=f"Commitment {commitment_id} not found")
    return repo.to_dict(updated)


@router.post("/{commitment_id}/drop")
async def drop_commitment(commitment_id: UUID) -> Dict[str, Any]:
    updated = await repo.drop(commitment_id)
    if updated is None:
        raise HTTPException(status_code=404, detail=f"Commitment {commitment_id} not found")
    return repo.to_dict(updated)


@router.post("/{commitment_id}/nag")
async def nag_now(commitment_id: UUID) -> Dict[str, Any]:
    """Force a reminder immediately — used by the console's 'poke me' button."""
    row = await repo.get(commitment_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Commitment {commitment_id} not found")
    result = await get_nag_engine().nag_one(row)
    return {"nagged": result, "next_rung": ladder_for((row.nag_count or 0) + 1)}
