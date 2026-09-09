"""Schedule sheet endpoints — read the Sheet, reconcile it with the ledger."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ...agents.schedule_sync import detect_day_columns, get_schedule_sync, map_columns
from ...core.config import get_settings
from ...core.logging import get_logger

logger = get_logger("api.schedule")
router = APIRouter(prefix="/api/schedule", tags=["schedule"])


class SyncRequest(BaseModel):
    sheet_id: Optional[str] = None
    sheet_range: Optional[str] = None
    write_back: bool = True
    # Matrix sheets (days across the top) sync one day at a time; defaults to today.
    days: Optional[List[str]] = None


@router.get("/state")
async def schedule_state() -> Dict[str, Any]:
    s = get_settings()
    return {
        "sheet_configured": bool(s.schedule_sheet_id),
        "sheet_id_prefix": (s.schedule_sheet_id or "")[:8],
        "range": s.schedule_sheet_range,
    }


@router.get("/preview")
async def schedule_preview(
    sheet_id: Optional[str] = None, sheet_range: Optional[str] = None
) -> Dict[str, Any]:
    """Show what the sync would see — header mapping and the first rows.
    Use this to check column names before letting it file anything."""
    s = get_settings()
    sid = sheet_id or s.schedule_sheet_id
    if not sid:
        raise HTTPException(status_code=400, detail="SCHEDULE_SHEET_ID is not configured")
    header, rows, err = await get_schedule_sync().read_rows(
        sid, sheet_range or s.schedule_sheet_range
    )
    if err:
        raise HTTPException(status_code=502, detail=err)
    cols = map_columns(header)
    day_cols = detect_day_columns(header)
    return {
        "header": [str(h) for h in header],
        "layout": "matrix" if day_cols else "long",
        "columns_matched": cols,
        "day_columns": {str(k): v for k, v in day_cols.items()},
        "task_column_found": bool(day_cols) or "task" in cols,
        "write_back_possible": not day_cols and ("status" in cols or "artifact" in cols),
        "row_count": len(rows),
        "sample_rows": [[str(c) for c in r] for r in rows[:5]],
    }


@router.post("/sync")
async def schedule_sync(body: SyncRequest) -> Dict[str, Any]:
    result = await get_schedule_sync().sync(
        sheet_id=body.sheet_id,
        sheet_range=body.sheet_range,
        write_back=body.write_back,
        days=body.days,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error", "sync failed"))
    return result
