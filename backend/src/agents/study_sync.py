"""Study and practice sheets → things the assistant chases you about.

You keep roadmaps, question banks and a season calendar in Google Sheets. Left
alone they are reference material you mean to open and don't. This turns them
into a small, daily, finite ask: two topics from the AI tracker, one interview
question, this week's BUILD task — filed as commitments so the nag engine keeps
you honest, and marked off when you close them.

Two shapes, declared per source in `config/study_sources.json`:

  backlog — a flat list (topics, questions, projects). Each run takes the next
            `daily_count` rows you have not been handed yet. Priority-ordered
            when the sheet has a Priority column ("Must" before "Should").
  weekly  — one row per week keyed by a date column. Takes the row covering
            today and emits the columns named in `item_columns`.

Progress is tracked two ways, and the difference matters. When a sheet has a
Status column, closing a commitment writes "done" back into it, so the sheet
stays the record. When it doesn't, the commitment ledger IS the record — a row
already filed is never handed to you twice, whatever its status.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..core import commitment_repo as repo
from ..core.config import get_settings
from ..core.logging import get_logger
from ..models.commitment import CommitmentStatus
from .commitment_extractor import resolve_due
from .schedule_sync import _norm_header, parse_row_key, parse_row_period, row_key

logger = get_logger("agents.study_sync")

# Study sheets use their own vocabulary — "Skill / Topic", "Question",
# "What to Learn" — none of which the timetable's column map knows about.
_STUDY_COLUMNS: Dict[str, Tuple[str, ...]] = {
    "title": (
        "skill", "skilltopic", "topic", "question", "project", "concept", "task",
        "item", "activity", "name", "whattolearn", "whattodo", "whattobuild",
        # Routine checklists head their action column "Do this" / "Action".
        "dothis", "action", "step", "do", "checklist",
    ),
    "detail": (
        "whattolearn", "whattodo", "whattobuild", "description", "details",
        "whattheyarereallytesting", "whyitmatters", "whyitmattersinterviewfocus",
        "practiceevidence", "practice", "evidence", "notes", "milestoneproof",
        "corekills", "coreskills", "whatitis",
    ),
    "category": ("category", "phase", "theme", "area", "section"),
    "priority": ("priority", "level", "tier", "importance"),
    "status": ("status", "done", "progress", "state"),
    "week": ("weekstarting", "weekof", "week", "wk", "date", "shipby"),
}

_DONE_WORDS = {"done", "yes", "y", "true", "complete", "completed", "x", "✓", "✔", "shipped"}

_DATE_FORMATS = ("%d %b %Y", "%d %B %Y", "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%b %Y", "%B %Y")


@dataclass
class StudySource:
    key: str
    name: str
    sheet_id: str
    range: str
    kind: str = "backlog"
    daily_count: int = 1
    due_time: str = "19:00"
    item_columns: List[str] = field(default_factory=list)
    priority_order: List[str] = field(default_factory=list)
    # `routine` only: how often the whole list comes round again.
    cadence: str = "monthly"
    # Runs only on its rotation theme's day (see agents/rotation.py).
    rotation_gated: bool = False
    enabled: bool = True

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "StudySource":
        return cls(
            key=str(raw.get("key") or raw.get("name") or "source"),
            name=str(raw.get("name") or raw.get("key") or "source"),
            sheet_id=str(raw.get("sheet_id") or ""),
            range=str(raw.get("range") or "A1:Z200"),
            kind=str(raw.get("kind") or "backlog").lower(),
            daily_count=max(1, int(raw.get("daily_count") or 1)),
            due_time=str(raw.get("due_time") or "19:00"),
            item_columns=[str(c) for c in (raw.get("item_columns") or [])],
            priority_order=[str(p).lower() for p in (raw.get("priority_order") or [])],
            cadence=str(raw.get("cadence") or "monthly").lower(),
            rotation_gated=bool(raw.get("rotation_gated", False)),
            enabled=bool(raw.get("enabled", True)),
        )


def _config_path() -> Path:
    override = os.environ.get("STUDY_SOURCES_PATH")
    if override:
        return Path(override)
    # backend/src/agents/study_sync.py → backend/config/study_sources.json
    return Path(__file__).resolve().parent.parent.parent / "config" / "study_sources.json"


def load_sources(enabled_only: bool = True) -> List[StudySource]:
    """From STUDY_SOURCES (inline JSON) if set, otherwise the config file."""
    raw_env = os.environ.get("STUDY_SOURCES", "").strip()
    data: Any = None
    if raw_env:
        try:
            data = json.loads(raw_env)
        except Exception as exc:
            logger.warning("study_sources_env_invalid", error=str(exc))
    if data is None:
        path = _config_path()
        try:
            data = json.loads(path.read_text())
        except FileNotFoundError:
            logger.warning("study_sources_missing", path=str(path))
            return []
        except Exception as exc:
            logger.warning("study_sources_unreadable", path=str(path), error=str(exc))
            return []
    entries = data.get("sources", []) if isinstance(data, dict) else data
    sources = [StudySource.from_dict(e) for e in entries if isinstance(e, dict)]
    sources = [s for s in sources if s.sheet_id]
    return [s for s in sources if s.enabled] if enabled_only else sources


def map_study_columns(header: List[Any]) -> Dict[str, int]:
    """Header → {canonical: index}. First match wins, so "Skill / Topic" becomes
    the title and "What to Learn" stays available as the detail."""
    found: Dict[str, int] = {}
    for idx, raw in enumerate(header or []):
        norm = _norm_header(raw)
        if not norm:
            continue
        for canonical, aliases in _STUDY_COLUMNS.items():
            if canonical in found:
                continue
            if norm in aliases or any(norm.startswith(a) for a in aliases if len(a) > 4):
                found[canonical] = idx
                break
    return found


def score_study_header(row: List[Any]) -> int:
    score = 0
    for raw in row or []:
        norm = _norm_header(raw)
        if not norm:
            continue
        for aliases in _STUDY_COLUMNS.values():
            if norm in aliases:
                score += 2
                break
    return score


def find_study_header(values: List[List[Any]], search_rows: int = 12) -> Tuple[int, List[Any]]:
    """These sheets open with a title, a byline, a blank, sometimes a preamble —
    the tracker's header is on row 7. Never assume row 1."""
    best_idx, best_score = 0, 0
    for idx, row in enumerate(values[:search_rows]):
        score = score_study_header(row)
        if score > best_score:
            best_idx, best_score = idx, score
    return best_idx, (values[best_idx] if values else [])


def parse_week_start(text_value: str) -> Optional[datetime]:
    raw = str(text_value or "").strip()
    if not raw:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def resolve_week_column(
    header: List[Any], rows: List[List[Any]], mapped: Optional[int]
) -> Optional[int]:
    """The column that actually holds dates.

    A season calendar opens with "Wk" (the week *number*) next to "Week
    starting" (the date). Name matching picks "Wk" and every date then fails to
    parse, so the calendar looks empty. Trust the data over the label: keep the
    mapped column only if its values are dates, otherwise find one whose are.
    """
    sample = rows[:12]

    def parses(idx: int) -> int:
        return sum(1 for r in sample if parse_week_start(_cell(r, idx)) is not None)

    if mapped is not None and parses(mapped) >= 2:
        return mapped
    width = max([len(header)] + [len(r) for r in sample]) if sample else len(header)
    best, best_hits = None, 0
    for idx in range(width):
        hits = parses(idx)
        if hits > best_hits:
            best, best_hits = idx, hits
    return best if best_hits >= 2 else mapped


def period_stamp(cadence: str, now: Optional[datetime] = None) -> str:
    """The identity of the current period, so a routine recurs.

    Without this a monthly routine is consumed once and never returns:
    September's "make the contribution" would count as already handled because
    August's was.
    """
    now = now or datetime.now(timezone.utc)
    cadence = (cadence or "monthly").lower()
    if cadence == "weekly":
        iso = now.isocalendar()
        return f"{iso[0]}-W{iso[1]:02d}"
    if cadence == "quarterly":
        return f"{now.year}-Q{(now.month - 1) // 3 + 1}"
    if cadence == "daily":
        return now.strftime("%Y-%m-%d")
    return now.strftime("%Y-%m")


def _cell(row: List[Any], idx: Optional[int]) -> str:
    if idx is None or idx >= len(row):
        return ""
    return str(row[idx] or "").strip()


def _priority_rank(value: str, order: List[str]) -> int:
    """Lower sorts first. Unknown values go last, preserving sheet order after."""
    v = str(value or "").strip().lower()
    for i, p in enumerate(order):
        if v.startswith(p):
            return i
    return len(order)


class StudySync:
    def __init__(self) -> None:
        self._log = logger

    def _pa(self) -> Any:
        from .bus import get_event_bus

        return get_event_bus()._pa

    async def _call(self, tool: str, args: Dict[str, Any]) -> Dict[str, Any]:
        pa = self._pa()
        if pa is None:
            return {"error": "personal assistant not attached"}
        return await pa._call_mcp(tool, args)

    async def read(self, source: StudySource) -> Tuple[int, List[Any], List[List[Any]], Optional[str]]:
        """(header_index, header, data_rows, error)."""
        result = await self._call(
            "google_workspace.read_sheet",
            {"sheet_id": source.sheet_id, "range": source.range},
        )
        if result.get("error") or result.get("skipped"):
            return 0, [], [], str(result.get("error") or result.get("reason") or "read failed")
        values = result.get("values") or []
        if not values and isinstance(result.get("result"), dict):
            values = result["result"].get("values") or []
        if not values:
            return 0, [], [], "sheet is empty or the range matched no cells"
        idx, header = find_study_header(values)
        return idx, header, values[idx + 1 :], None

    async def _already_filed(self, sheet_id: str) -> set:
        """Row keys this sheet has already produced, in ANY status.

        Deliberately not filtered to open rows: something you finished, dropped,
        or are still being chased about should not come round again tomorrow.
        """
        keys = set()
        for c in await repo.list_all(limit=500):
            parsed = parse_row_key(c.detail)
            if parsed and parsed[0] == sheet_id:
                keys.add((parsed[1], parsed[2]))
        return keys

    async def pick_backlog(self, source: StudySource) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        header_idx, header, rows, err = await self.read(source)
        if err:
            return [], err
        cols = map_study_columns(header)
        if "title" not in cols:
            return [], (
                "no topic/question column found — header was "
                + ", ".join(str(h) for h in header[:8])
            )

        seen = await self._already_filed(source.sheet_id)
        candidates: List[Tuple[int, int, Dict[str, Any]]] = []
        for offset, row in enumerate(rows):
            row_number = offset + header_idx + 2
            title = _cell(row, cols.get("title"))
            if not title or title == _cell(header, cols.get("title")):
                continue  # blank, or a repeated header band
            if (row_number, None) in seen:
                continue
            if _cell(row, cols.get("status")).lower() in _DONE_WORDS:
                continue
            candidates.append(
                (
                    _priority_rank(_cell(row, cols.get("priority")), source.priority_order),
                    offset,
                    {
                        "title": title,
                        "detail": _cell(row, cols.get("detail")),
                        "category": _cell(row, cols.get("category")),
                        "row_number": row_number,
                        "col_index": None,
                        "status_col": cols.get("status"),
                    },
                )
            )
        candidates.sort(key=lambda c: (c[0], c[1]))
        return [c[2] for c in candidates[: source.daily_count]], None

    async def pick_weekly(
        self, source: StudySource, today: Optional[datetime] = None
    ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        header_idx, header, rows, err = await self.read(source)
        if err:
            return [], err
        cols = map_study_columns(header)
        week_col = resolve_week_column(header, rows, cols.get("week"))
        if week_col is None:
            return [], "no week/date column found in this calendar"
        cols["week"] = week_col

        today = today or datetime.now(timezone.utc)
        wanted = [c.lower() for c in source.item_columns]

        # The row for the current week: the latest start date on or before today.
        best: Optional[Tuple[datetime, int, List[Any]]] = None
        for offset, row in enumerate(rows):
            start = parse_week_start(_cell(row, cols.get("week")))
            if start is None or start > today:
                continue
            if best is None or start > best[0]:
                best = (start, offset, row)
        if best is None:
            return [], "no week in this calendar starts on or before today"

        start, offset, row = best
        row_number = offset + header_idx + 2
        seen = await self._already_filed(source.sheet_id)

        items: List[Dict[str, Any]] = []
        for col_idx, head in enumerate(header):
            head_norm = str(head or "").strip().lower()
            if wanted and not any(head_norm.startswith(w) for w in wanted):
                continue
            if not wanted and col_idx <= (cols.get("week") or 0) + 1:
                continue  # skip the index/date/phase preamble
            value = _cell(row, col_idx)
            if not value or value == "-":
                continue
            if (row_number, col_idx) in seen:
                continue
            items.append(
                {
                    "title": value,
                    "detail": f"Week of {start.strftime('%d %b %Y')}",
                    "category": _cell(row, cols.get("category")),
                    "row_number": row_number,
                    "col_index": col_idx,
                    "status_col": None,
                }
            )
        return items, None

    async def pick_routine(
        self, source: StudySource, now: Optional[datetime] = None
    ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """The whole checklist, once per period.

        The sheet's Done column is deliberately ignored here. A routine's tick
        boxes are not period-scoped — a step ticked in August is still ticked in
        September — so the ledger, keyed by period, is the only honest record.
        """
        header_idx, header, rows, err = await self.read(source)
        if err:
            return [], err
        cols = map_study_columns(header)
        if "title" not in cols:
            return [], (
                "no action column found — header was "
                + ", ".join(str(h) for h in header[:8])
            )

        stamp = period_stamp(source.cadence, now)
        filed_this_period = {
            parse_row_key(c.detail)[1]
            for c in await repo.list_all(limit=500)
            if parse_row_key(c.detail)
            and parse_row_key(c.detail)[0] == source.sheet_id
            and parse_row_period(c.detail) == stamp
        }

        items: List[Dict[str, Any]] = []
        for offset, row in enumerate(rows):
            row_number = offset + header_idx + 2
            title = _cell(row, cols.get("title"))
            if not title or title == _cell(header, cols.get("title")):
                continue
            if row_number in filed_this_period:
                continue
            items.append(
                {
                    "title": title,
                    "detail": _cell(row, cols.get("detail")),
                    "category": _cell(row, cols.get("category")),
                    "row_number": row_number,
                    "col_index": None,
                    "status_col": None,
                    "period": stamp,
                }
            )
        return items, None

    async def sync_source(self, source: StudySource) -> Dict[str, Any]:
        """Pick today's items from one source and file them. Never raises."""
        try:
            if source.kind == "weekly":
                items, err = await self.pick_weekly(source)
            elif source.kind == "routine":
                items, err = await self.pick_routine(source)
            else:
                items, err = await self.pick_backlog(source)
        except Exception as exc:
            self._log.warning("study_pick_failed", source=source.key, error=str(exc))
            return {"key": source.key, "ok": False, "error": str(exc), "filed": 0}

        if err:
            return {"key": source.key, "ok": False, "error": err, "filed": 0}

        require_approval = get_settings().commitment_require_approval
        filed: List[Dict[str, Any]] = []
        for item in items:
            marker = row_key(
                source.sheet_id, item["row_number"], item["col_index"], item.get("period")
            )
            detail_bits = [item.get("category", ""), item.get("detail", "")]
            detail = " · ".join(b for b in detail_bits if b)
            try:
                row = await repo.create(
                    title=(
                        f"{source.name}: {item['title']}"[:500]
                        if source.kind in ("weekly", "routine")
                        else item["title"]
                    ),
                    due_at=resolve_due("", "", source.due_time),
                    detail=f"{detail} {marker}".strip(),
                    source="study",
                    nag_interval_sec=1800,
                    status=(
                        CommitmentStatus.PROPOSED.value
                        if require_approval
                        else CommitmentStatus.OPEN.value
                    ),
                )
                if row is not None:
                    filed.append(repo.to_dict(row))
            except Exception as exc:
                self._log.warning("study_file_failed", source=source.key, error=str(exc))
        return {
            "key": source.key,
            "name": source.name,
            "ok": True,
            "filed": len(filed),
            "commitments": filed,
        }

    async def _rotation_tasks(self) -> List[Dict[str, Any]]:
        """File the day's themed tasks — the ones with no sheet behind them.

        Keyed by theme and date so a re-run in the same day is a no-op, and
        tomorrow's set is untouched by today's.
        """
        from .rotation import themes_for

        picked = themes_for()
        if not picked["enabled"]:
            return []
        day = picked["date"]
        require_approval = get_settings().commitment_require_approval

        existing = {
            (c.detail or "").split("[theme:", 1)[-1].split("]", 1)[0]
            for c in await repo.list_all(limit=500)
            if "[theme:" in (c.detail or "")
        }

        out: List[Dict[str, Any]] = []
        for theme in list(picked["daily"]) + ([picked["cycled"]] if picked["cycled"] else []):
            filed: List[Dict[str, Any]] = []
            for idx, task in enumerate(theme.tasks):
                marker = f"{theme.theme}@{day}#{idx}"
                if marker in existing:
                    continue
                try:
                    row = await repo.create(
                        title=task,
                        due_at=resolve_due("", "", theme.due_time),
                        detail=f"{theme.label} [theme:{marker}]",
                        source=theme.theme,
                        status=(
                            CommitmentStatus.PROPOSED.value
                            if require_approval
                            else CommitmentStatus.OPEN.value
                        ),
                    )
                    if row is not None:
                        filed.append(repo.to_dict(row))
                except Exception as exc:
                    self._log.warning("rotation_file_failed", theme=theme.theme, error=str(exc))
            if filed:
                out.append(
                    {"key": theme.theme, "name": theme.label, "ok": True,
                     "filed": len(filed), "commitments": filed}
                )
        return out

    async def sync_all(self) -> Dict[str, Any]:
        from .rotation import active_source_keys, themes_for

        sources = load_sources()
        if not sources:
            return {"ok": False, "error": "no enabled study sources configured", "results": []}

        # Themed sources only run on their theme's day, so the biggest sheet
        # cannot quietly become every day's work.
        allowed = active_source_keys()
        skipped_by_rotation: List[str] = []
        if allowed is not None:
            runnable = []
            for src in sources:
                gated = getattr(src, "rotation_gated", False)
                if gated and src.key not in allowed:
                    skipped_by_rotation.append(src.key)
                else:
                    runnable.append(src)
            sources = runnable

        results = [await self.sync_source(s) for s in sources]
        results.extend(await self._rotation_tasks())
        total = sum(r.get("filed", 0) for r in results)
        logger.info(
            "study_sync_done",
            sources=len(sources),
            filed=total,
            failed=[r["key"] for r in results if not r.get("ok")],
        )
        picked = themes_for()
        return {
            "ok": True,
            "sources": len(sources),
            "filed": total,
            "results": results,
            "themes": {
                "daily": [t.label for t in picked["daily"]],
                "cycled": picked["cycled"].label if picked["cycled"] else None,
                "skipped_by_rotation": skipped_by_rotation,
            },
            "at": datetime.now(timezone.utc).isoformat(),
        }


_sync: Optional[StudySync] = None


def get_study_sync() -> StudySync:
    global _sync
    if _sync is None:
        _sync = StudySync()
    return _sync
