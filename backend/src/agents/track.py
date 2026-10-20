"""Ordered curricula, with a cursor.

The rotation cycles and the fellowship runs on a calendar. A track does
neither: it advances when you finish something. That makes it the right shape
for a book you are working through and the wrong shape for anything that
should happen on a Tuesday.

One item is filed at a time, on purpose. A reading list that files sixteen
commitments is a reading list you archive.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select

from ..core.db import get_session, is_db_available
from ..core.logging import get_logger
from ..models.track_state import TrackStateDB
from .study_sync import _config_path

logger = get_logger("agents.track")


@dataclass
class TrackItem:
    key: str
    title: str
    url: str
    note: str = ""


@dataclass
class Track:
    key: str
    label: str
    due_time: str
    items: List[TrackItem]
    start_at: str = ""

    def index_of(self, key: str) -> int:
        for i, item in enumerate(self.items):
            if item.key == key:
                return i
        return -1


def load_tracks() -> List[Track]:
    try:
        raw = json.loads(_config_path().read_text()).get("tracks") or []
    except Exception as exc:
        logger.warning("tracks_config_unreadable", error=str(exc))
        return []
    out = []
    for t in raw:
        out.append(Track(
            key=t["key"], label=t.get("label", t["key"]),
            due_time=t.get("due_time", "06:00"),
            start_at=t.get("start_at", ""),
            items=[TrackItem(**{k: v for k, v in i.items() if k in ("key", "title", "url", "note")})
                   for i in t.get("items", [])],
        ))
    return out


def get_track(key: str) -> Optional[Track]:
    return next((t for t in load_tracks() if t.key == key), None)


async def _state(track: Track) -> Optional[TrackStateDB]:
    if not is_db_available():
        return None
    async with get_session() as session:
        rows = (await session.execute(
            select(TrackStateDB).where(TrackStateDB.track_key == track.key)
        )).scalars().all()
    return rows[0] if rows else None


async def current(track_key: str) -> Dict[str, Any]:
    """The item you are on, or a finished marker."""
    track = get_track(track_key)
    if track is None or not track.items:
        return {"track": track_key, "found": False}

    row = await _state(track)
    cursor = row.cursor_key if row else (track.start_at or track.items[0].key)
    index = track.index_of(cursor)
    if index < 0:
        # Cursor points at an item that was renamed or removed from the order.
        # Falling back to the start is wrong; the configured start is the only
        # safe answer, and the mismatch is worth saying out loud.
        logger.warning("track_cursor_unknown", track=track_key, cursor=cursor)
        index = max(0, track.index_of(track.start_at))

    finished = bool(row and row.finished_at)
    item = track.items[index]
    return {
        "track": track.key, "label": track.label, "found": True,
        "finished": finished,
        "position": index + 1, "total": len(track.items),
        "due_time": track.due_time,
        "item": None if finished else {
            "key": item.key, "title": item.title, "url": item.url, "note": item.note
        },
        "next": (track.items[index + 1].title if index + 1 < len(track.items) else None),
    }


async def advance(track_key: str) -> Dict[str, Any]:
    """Finished the current item. Move on."""
    track = get_track(track_key)
    if track is None or not track.items:
        return {"track": track_key, "found": False}

    row = await _state(track)
    cursor = row.cursor_key if row else (track.start_at or track.items[0].key)
    index = track.index_of(cursor)
    if index < 0:
        index = max(0, track.index_of(track.start_at))

    done_title = track.items[index].title
    at_end = index + 1 >= len(track.items)
    new_cursor = cursor if at_end else track.items[index + 1].key

    async with get_session() as session:
        fresh = (await session.execute(
            select(TrackStateDB).where(TrackStateDB.track_key == track.key)
        )).scalars().first()
        if fresh is None:
            fresh = TrackStateDB(track_key=track.key, cursor_key=new_cursor, completed=1)
            session.add(fresh)
        else:
            fresh.cursor_key = new_cursor
            fresh.completed = (fresh.completed or 0) + 1
        if at_end:
            fresh.finished_at = datetime.now(timezone.utc)
        await session.commit()

    logger.info("track_advanced", track=track.key, finished=done_title, at_end=at_end)
    return {"track": track.key, "finished": done_title,
            "now_on": None if at_end else track.items[index + 1].title,
            "complete": at_end}


async def tasks_for(track_key: str) -> List[str]:
    """One commitment line. Not sixteen."""
    state = await current(track_key)
    if not state.get("found") or state.get("finished"):
        return []
    item = state["item"]
    nxt = f" (next: {state['next']})" if state.get("next") else " — last one"
    return [
        f"{state['label']} {state['position']}/{state['total']} — {item['title']}: "
        f"{item['note']} — {item['url']}{nxt}"
    ]
