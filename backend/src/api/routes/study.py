"""Study source endpoints — what's configured, what today's picks would be."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ...agents.study_sync import get_study_sync, load_sources
from ...core.logging import get_logger

logger = get_logger("api.study")
router = APIRouter(prefix="/api/study", tags=["study"])


class StudySyncRequest(BaseModel):
    key: Optional[str] = None  # sync one source; omit for all enabled


@router.get("/sources")
async def list_sources() -> List[Dict[str, Any]]:
    return [
        {
            "key": s.key,
            "name": s.name,
            "sheet_id_prefix": s.sheet_id[:12],
            "range": s.range,
            "kind": s.kind,
            "daily_count": s.daily_count,
            "due_time": s.due_time,
            "enabled": s.enabled,
        }
        for s in load_sources(enabled_only=False)
    ]


@router.get("/preview/{key}")
async def preview_source(key: str) -> Dict[str, Any]:
    """What this source would hand you next, without filing anything."""
    source = next((s for s in load_sources(enabled_only=False) if s.key == key), None)
    if source is None:
        raise HTTPException(status_code=404, detail=f"no study source named {key!r}")
    sync = get_study_sync()
    header_idx, header, rows, err = await sync.read(source)
    if err:
        raise HTTPException(status_code=502, detail=err)
    items, pick_err = (
        await sync.pick_weekly(source) if source.kind == "weekly" else await sync.pick_backlog(source)
    )
    return {
        "key": source.key,
        "name": source.name,
        "kind": source.kind,
        "header_row": header_idx + 1,
        "header": [str(h) for h in header],
        "data_rows": len(rows),
        "would_pick": items,
        "error": pick_err,
    }


@router.get("/resources")
async def study_resources(refresh: bool = False) -> Dict[str, Any]:
    """The grouped reading list: sheet resource tabs + your GitHub repos.

    Cached for 15 minutes — this fans out to a dozen network calls and the
    underlying sheets change on the order of weeks. `?refresh=true` bypasses it.
    """
    from ...agents.resources import get_resource_collector

    return await get_resource_collector().collect(refresh=refresh)


@router.post("/sync")
async def sync_study(body: StudySyncRequest) -> Dict[str, Any]:
    sync = get_study_sync()
    if body.key:
        source = next((s for s in load_sources(enabled_only=False) if s.key == body.key), None)
        if source is None:
            raise HTTPException(status_code=404, detail=f"no study source named {body.key!r}")
        return await sync.sync_source(source)
    result = await sync.sync_all()
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error", "sync failed"))
    return result
