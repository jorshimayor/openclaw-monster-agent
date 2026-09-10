"""The day view: the shape of your day from the sheet, and what's on it.

Two different things are deliberately kept apart.

  blocks — the daily template from your timetable sheet (Book Reading 05:00,
           Deep Block 1 05:45, …). This is the *shape* of the day. It is
           read-only here: it repeats every day, and turning 21 recurring
           blocks into 21 tracked commitments would mean 21 things nagging you
           daily. It is the background the day is drawn on.

  items  — actual commitments due today: study picks, tasks, reminders,
           anything you added. These are tracked, chased, and draggable.

Dragging an item onto a slot reschedules it; nothing writes back to the
timetable sheet, so the template stays intact.
"""

from __future__ import annotations

import re
from datetime import date as date_cls, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ...agents.schedule_sync import (
    _cell,
    detect_day_columns,
    find_header,
    get_schedule_sync,
    map_columns,
)
from ...core import commitment_repo as repo
from ...core.config import get_settings
from ...core.logging import get_logger

logger = get_logger("api.day")
router = APIRouter(prefix="/api/day", tags=["day"])

# Optional seconds matter: one cell in the timetable reads "4:00:00 PM - 5:00PM",
# and without allowing them the PM is never reached — 16:00 parsed as 04:00.
_TIME_RE = re.compile(
    r"(?P<h>[01]?\d|2[0-3])\s*(?::\s*(?P<m>[0-5]\d))?(?::\s*[0-5]\d)?"
    r"\s*(?P<ampm>am|pm|a\.m\.|p\.m\.)?",
    re.I,
)


class AddItemRequest(BaseModel):
    title: str
    at_time: Optional[str] = None  # "14:30"
    date: Optional[str] = None  # YYYY-MM-DD, defaults to today
    detail: Optional[str] = None
    category: Optional[str] = None  # study | practice | build | apply | admin
    approved: bool = True  # things you type yourself need no approval step


class MoveItemRequest(BaseModel):
    at_time: str = Field(..., description="HH:MM in your local clock")
    date: Optional[str] = None


def _offset() -> timedelta:
    return timedelta(hours=get_settings().user_timezone_offset_hours)


def _local_now() -> datetime:
    return datetime.now(timezone.utc) + _offset()


def parse_hhmm(text_value: str) -> Optional[str]:
    """'5:45AM - 7:15AM' or '14:30' → 'HH:MM' (the start)."""
    raw = str(text_value or "").split("-")[0].strip()
    if not raw:
        return None
    m = _TIME_RE.search(raw)
    if not m:
        return None
    hour, minute = int(m.group("h")), int(m.group("m") or 0)
    ampm = (m.group("ampm") or "").replace(".", "").lower()
    if ampm == "pm" and hour < 12:
        hour += 12
    elif ampm == "am" and hour == 12:
        hour = 0
    return f"{hour:02d}:{minute:02d}"


def _local_bounds(day: date_cls) -> tuple[datetime, datetime]:
    """UTC instants bracketing that local calendar day."""
    start_local = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    return (start_local - _offset(), start_local + timedelta(days=1) - _offset())


def to_utc(day: date_cls, hhmm: str) -> datetime:
    hour, minute = (int(p) for p in hhmm.split(":"))
    local = datetime(day.year, day.month, day.day, hour, minute, tzinfo=timezone.utc)
    return local - _offset()


async def _blocks_for(day: date_cls) -> tuple[List[Dict[str, Any]], Optional[str]]:
    """The template blocks for that weekday, from the timetable sheet."""
    settings = get_settings()
    if not settings.schedule_sheet_id:
        return [], "SCHEDULE_SHEET_ID is not configured"

    sync = get_schedule_sync()
    header, rows, err = await sync.read_rows(
        settings.schedule_sheet_id, settings.schedule_sheet_range
    )
    if err:
        return [], err

    day_cols = detect_day_columns(header)
    if not day_cols:
        return [], "no weekday columns found in the timetable sheet"
    cols = map_columns(header)

    weekday = day.strftime("%A").lower()
    col_idx = next((i for i, name in day_cols.items() if name == weekday), None)
    if col_idx is None:
        return [], f"no column for {weekday} in the timetable sheet"

    blocks: List[Dict[str, Any]] = []
    for row in rows:
        label = _cell(row, col_idx)
        raw_time = _cell(row, cols.get("time"))
        start = parse_hhmm(raw_time)
        if not label or not start:
            continue
        blocks.append(
            {
                "start": start,
                "label": label,
                "duration": _cell(row, cols.get("duration")),
                "raw_time": raw_time,
            }
        )
    blocks.sort(key=lambda b: b["start"])
    return blocks, None


@router.get("")
async def get_day(date: Optional[str] = None) -> Dict[str, Any]:
    """The day's shape plus everything due on it."""
    try:
        day = date_cls.fromisoformat(date) if date else _local_now().date()
    except ValueError:
        raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD")

    blocks, block_error = await _blocks_for(day)
    start_utc, end_utc = _local_bounds(day)

    items: List[Dict[str, Any]] = []
    for row in await repo.list_all(limit=500):
        due = row.due_at
        if due is None:
            continue
        if due.tzinfo is None:
            due = due.replace(tzinfo=timezone.utc)
        if not (start_utc <= due < end_utc):
            continue
        entry = repo.to_dict(row)
        entry["local_time"] = (due + _offset()).strftime("%H:%M")
        items.append(entry)
    items.sort(key=lambda i: i["local_time"])

    return {
        "date": day.isoformat(),
        "weekday": day.strftime("%A"),
        "timezone_offset_hours": get_settings().user_timezone_offset_hours,
        "now_local": _local_now().strftime("%H:%M"),
        "blocks": blocks,
        "block_error": block_error,
        "items": items,
    }


@router.post("/items", status_code=201)
async def add_item(body: AddItemRequest) -> Dict[str, Any]:
    """Add something to a day. Typed by hand, so it skips the approval gate."""
    from ...models.commitment import CommitmentStatus

    if not body.title.strip():
        raise HTTPException(status_code=400, detail="title cannot be empty")
    try:
        day = date_cls.fromisoformat(body.date) if body.date else _local_now().date()
    except ValueError:
        raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD")

    hhmm = parse_hhmm(body.at_time or "") or _local_now().strftime("%H:%M")
    detail = " · ".join(b for b in [body.category or "", body.detail or ""] if b)

    row = await repo.create(
        title=body.title.strip(),
        due_at=to_utc(day, hhmm),
        detail=detail or None,
        source=body.category or "manual",
        status=(
            CommitmentStatus.OPEN.value if body.approved else CommitmentStatus.PROPOSED.value
        ),
    )
    if row is None:
        raise HTTPException(status_code=500, detail="could not save that")
    result = repo.to_dict(row)
    result["local_time"] = hhmm
    return result


@router.post("/items/{ref}/move")
async def move_item(ref: str, body: MoveItemRequest) -> Dict[str, Any]:
    """Drag-and-drop lands here: same item, new time."""
    row = await repo.resolve_ref(ref)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Commitment {ref!r} not found")
    hhmm = parse_hhmm(body.at_time)
    if not hhmm:
        raise HTTPException(status_code=400, detail=f"could not read a time from {body.at_time!r}")
    try:
        day = date_cls.fromisoformat(body.date) if body.date else _local_now().date()
    except ValueError:
        raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD")

    updated = await repo.reschedule(row.id, to_utc(day, hhmm))
    if updated is None:
        raise HTTPException(status_code=500, detail="could not move that")
    result = repo.to_dict(updated)
    result["local_time"] = hhmm
    logger.info("day_item_moved", id=str(row.id)[:8], to=hhmm)
    return result
