"""The study queue: what other agents think you should learn next.

Deliberately not commitments. Anything filed here is a recommendation that
waits for you to promote it, so an agent cannot fill your day with reminders
you never agreed to.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from ...core import commitment_repo
from ...core.db import get_session
from ...models.study_suggestion import STATUSES, TRACKS, StudySuggestionDB

router = APIRouter(prefix="/api/study/queue", tags=["study"])


class SuggestRequest(BaseModel):
    topic: str = Field(min_length=6, max_length=300)
    # Required, and the point: a bare link is not a recommendation. If you
    # cannot say why this now, it is not ready to be suggested.
    rationale: str = Field(min_length=20, max_length=2000)
    url: Optional[str] = None
    track: str = Field(default="fundamentals")
    priority: int = Field(default=3, ge=1, le=5)
    est_minutes: Optional[int] = Field(default=None, ge=5, le=600)
    suggested_by: str = Field(default="unknown", max_length=80)


@router.get("")
async def list_queue(status: str = "queued", limit: int = 100) -> List[Dict[str, Any]]:
    if status not in STATUSES and status != "all":
        raise HTTPException(400, f"status must be one of {STATUSES} or 'all'")
    async with get_session() as session:
        stmt = select(StudySuggestionDB)
        if status != "all":
            stmt = stmt.where(StudySuggestionDB.status == status)
        stmt = stmt.order_by(
            StudySuggestionDB.priority.asc(), StudySuggestionDB.created_at.asc()
        ).limit(max(1, min(limit, 300)))
        rows = (await session.execute(stmt)).scalars().all()
    return [r.to_dict() for r in rows]


@router.post("", status_code=201)
async def suggest(body: SuggestRequest) -> Dict[str, Any]:
    if body.track not in TRACKS:
        raise HTTPException(400, f"track must be one of {TRACKS}")
    async with get_session() as session:
        row = StudySuggestionDB(
            topic=body.topic.strip(),
            rationale=body.rationale.strip(),
            url=(body.url or "").strip() or None,
            track=body.track,
            priority=body.priority,
            est_minutes=body.est_minutes,
            suggested_by=body.suggested_by.strip() or "unknown",
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
    return row.to_dict()


async def _resolve(ref: str) -> StudySuggestionDB:
    async with get_session() as session:
        rows = (await session.execute(select(StudySuggestionDB))).scalars().all()
    for row in rows:
        if str(row.id) == ref or str(row.id).startswith(ref):
            return row
    raise HTTPException(404, f"suggestion {ref!r} not found")


@router.post("/{ref}/promote")
async def promote(ref: str, day: str = "today", time_of_day: str = "") -> Dict[str, Any]:
    """Turn a suggestion into a commitment. Only you do this, never an agent."""
    from ...agents.commitment_extractor import resolve_due

    row = await _resolve(ref)
    if row.status == "promoted":
        raise HTTPException(409, "already promoted")

    created = await commitment_repo.create(
        title=f"Study: {row.topic}",
        due_at=resolve_due(day, time_of_day),
        detail=f"{row.rationale}" + (f" — {row.url}" if row.url else ""),
        source=f"study-queue:{row.track}",
    )
    if created is None:
        raise HTTPException(500, "could not create the commitment")

    async with get_session() as session:
        fresh = await session.get(StudySuggestionDB, row.id)
        fresh.status = "promoted"
        fresh.promoted_commitment_id = created.id
        await session.commit()
    return {"promoted": True, "commitment": commitment_repo.to_dict(created)}


@router.post("/{ref}/dismiss")
async def dismiss(ref: str) -> Dict[str, Any]:
    row = await _resolve(ref)
    async with get_session() as session:
        fresh = await session.get(StudySuggestionDB, row.id)
        fresh.status = "dismissed"
        await session.commit()
    return {"dismissed": True, "id": str(row.id)}
