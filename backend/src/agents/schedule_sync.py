"""Google Sheet ⇄ commitments: your weekly schedule as the source of truth.

You keep your schedule in a Sheet. This reads it, files each row as a
commitment so the nag engine chases it, and writes the outcome back into the
Sheet so the two never drift apart. Editing the Sheet edits your schedule;
closing a commitment on Telegram ticks the Sheet.

Expected layout — a header row plus one row per item. Column names are matched
case-insensitively and loosely, so "Task"/"What"/"Item" all work:

    | Day      | Time  | Task                     | Status | Artifact | Notes |
    |----------|-------|--------------------------|--------|----------|-------|
    | Monday   | 19:00 | Rewrite the bot README   | done   | https:// |       |
    | Tuesday  | 07:30 | Gym                      |        |          |       |

Only `Task` is required. Missing `Day`/`Time` fall back to the same defaults the
report extractor uses. `Status`/`Artifact` are written back by the sync; if they
aren't in the header, write-back is skipped and the sync is read-only.

Rows are matched to commitments by a stable key (sheet id + row number) held in
the commitment's `detail`, so re-running the sync updates rather than duplicates.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from ..core import commitment_repo as repo
from ..core.config import get_settings
from ..core.logging import get_logger
from ..models.commitment import CommitmentStatus
from .commitment_extractor import resolve_due

logger = get_logger("agents.schedule_sync")

# Header aliases → canonical column. Everything is lowercased and stripped of
# non-letters first, so "Time (WAT)" matches "time".
_COLUMNS: Dict[str, Tuple[str, ...]] = {
    "task": ("task", "what", "item", "activity", "todo", "action", "description", "title"),
    "duration": ("duration", "length", "mins", "minutes"),
    "day": ("day", "date", "when", "weekday"),
    "time": ("time", "at", "start", "starttime", "clock"),
    "status": ("status", "done", "state", "complete", "completed"),
    "artifact": ("artifact", "proof", "link", "evidence", "url", "output"),
    "notes": ("notes", "note", "detail", "details", "comment"),
}

_ROW_KEY = re.compile(
    r"\[sheet:(?P<sheet>[^\]#]+)#(?P<row>\d+)(?:\.(?P<col>\d+))?(?:@(?P<period>[\w-]+))?\]"
)

_DONE_WORDS = {"done", "yes", "y", "true", "complete", "completed", "x", "✓", "✔"}

# A "matrix" schedule puts the days across the top and the time slots down the
# side — the shape a human actually builds a weekly template in:
#
#     DURATION | TIME    | SUN          | MON          | TUE ...
#     30 mins  | 5:00 AM | Book Reading | Book Reading | ...
#
# Long format (one row per item, with a Day column) is the other shape. Both
# are supported; the layout is detected from the header.
_DAY_HEADERS = {
    "sun": "sunday", "sunday": "sunday",
    "mon": "monday", "monday": "monday",
    "tue": "tuesday", "tues": "tuesday", "tuesday": "tuesday",
    "wed": "wednesday", "wednesday": "wednesday",
    "thu": "thursday", "thur": "thursday", "thurs": "thursday", "thursday": "thursday",
    "fri": "friday", "friday": "friday",
    "sat": "saturday", "saturday": "saturday",
}


def _norm_header(value: str) -> str:
    return re.sub(r"[^a-z]", "", str(value or "").lower())


def map_columns(header: List[Any]) -> Dict[str, int]:
    """Header row → {canonical name: column index}. Unknown columns ignored."""
    found: Dict[str, int] = {}
    for idx, raw in enumerate(header or []):
        norm = _norm_header(raw)
        if not norm:
            continue
        for canonical, aliases in _COLUMNS.items():
            if canonical in found:
                continue
            if norm in aliases or any(norm.startswith(a) for a in aliases):
                found[canonical] = idx
                break
    return found


# How far down to hunt for the header. Real sheets open with a title row, a
# blank spacer, sometimes a note — assuming row 1 is the header made a perfectly
# good timetable look like it had no columns at all.
_HEADER_SEARCH_ROWS = 8


def score_header(row: List[Any]) -> int:
    """How much this row looks like a header. Higher wins."""
    if not row:
        return 0
    score = 0
    for raw in row:
        norm = _norm_header(raw)
        if not norm:
            continue
        if norm in _DAY_HEADERS:
            score += 3  # day columns are the strongest signal
            continue
        for aliases in _COLUMNS.values():
            if norm in aliases:
                score += 2
                break
    return score


def find_header(values: List[List[Any]]) -> Tuple[int, List[Any]]:
    """(index, row) of the best header candidate in the first few rows.

    Falls back to row 0 so a sheet with no recognisable header still produces
    the same "no task column found" error as before, rather than an exception.
    """
    best_idx, best_score = 0, 0
    for idx, row in enumerate(values[:_HEADER_SEARCH_ROWS]):
        score = score_header(row)
        if score > best_score:
            best_idx, best_score = idx, score
    return best_idx, (values[best_idx] if values else [])


def detect_day_columns(header: List[Any]) -> Dict[int, str]:
    """{column index: weekday} for a matrix-layout header. Empty for long format."""
    found: Dict[int, str] = {}
    for idx, raw in enumerate(header or []):
        norm = _norm_header(raw)
        if norm in _DAY_HEADERS:
            found[idx] = _DAY_HEADERS[norm]
    return found


def _first_time_cell(row: List[Any], cols: Dict[str, int]) -> str:
    """The slot's start time. Matrix sheets write "5:45AM - 7:15AM"; take the start."""
    raw = _cell(row, cols.get("time"))
    return raw.split("-")[0].strip() if raw else ""


def flatten_matrix(
    header: List[Any],
    rows: List[List[Any]],
    day_cols: Dict[int, str],
    cols: Dict[str, int],
    header_offset: int = 0,
) -> List[Dict[str, Any]]:
    """Matrix → one entry per (time slot × day), skipping blanks and repeats.

    A daily template repeats the same activity across all seven columns. That is
    seven real commitments a week, not one — but they are only worth filing for
    the day being synced, which the caller decides.
    """
    out: List[Dict[str, Any]] = []
    for offset, row in enumerate(rows):
        row_number = offset + header_offset + 2
        time_cell = _first_time_cell(row, cols)
        for col_idx, day in day_cols.items():
            title = _cell(row, col_idx)
            if not title:
                continue
            out.append(
                {
                    "title": title,
                    "day": day,
                    "time": time_cell,
                    "row_number": row_number,
                    "col_index": col_idx,
                    "duration": _cell(row, cols.get("duration")),
                }
            )
    return out


def row_key(
    sheet_id: str,
    row_number: int,
    col_index: Optional[int] = None,
    period: Optional[str] = None,
) -> str:
    """Stable identity for a sheet cell, stored in the commitment's detail.

    Matrix layouts need the column too — row 3 holds seven different days. A
    recurring routine needs the period as well ("2026-09"), or September's
    contribution step would count as already done because August's was.
    """
    suffix = f".{col_index}" if col_index is not None else ""
    stamp = f"@{period}" if period else ""
    return f"[sheet:{sheet_id}#{row_number}{suffix}{stamp}]"


def parse_row_key(
    detail: Optional[str],
) -> Optional[Tuple[str, int, Optional[int]]]:
    """(sheet_id, row, col). The period, when present, is read separately by
    `parse_row_period` — callers that dedupe by cell should ignore it."""
    m = _ROW_KEY.search(str(detail or ""))
    if not m:
        return None
    col = m.group("col")
    return (m.group("sheet"), int(m.group("row")), int(col) if col is not None else None)


def parse_row_period(detail: Optional[str]) -> Optional[str]:
    m = _ROW_KEY.search(str(detail or ""))
    return m.group("period") if m else None


def _cell(row: List[Any], idx: Optional[int]) -> str:
    if idx is None or idx >= len(row):
        return ""
    return str(row[idx] or "").strip()


def _today_name() -> str:
    return datetime.now(timezone.utc).strftime("%A").lower()


def _column_letter(index: int) -> str:
    """0 → A, 25 → Z, 26 → AA (Sheets A1 notation)."""
    letters = ""
    index += 1
    while index > 0:
        index, rem = divmod(index - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


class ScheduleSync:
    """Reads the schedule Sheet and reconciles it with the commitment ledger."""

    def __init__(self) -> None:
        self._log = logger
        # Sheet row number of the detected header (0-based), so entry row
        # numbers stay true to the spreadsheet even when it opens with a title.
        self._header_offset = 0

    def _pa(self) -> Any:
        from .bus import get_event_bus

        return get_event_bus()._pa

    async def _call(self, tool: str, args: Dict[str, Any]) -> Dict[str, Any]:
        pa = self._pa()
        if pa is None:
            return {"error": "personal assistant not attached"}
        return await pa._call_mcp(tool, args)

    async def read_rows(
        self, sheet_id: str, sheet_range: str
    ) -> Tuple[List[Any], List[List[Any]], Optional[str]]:
        """(header, data_rows, error)."""
        result = await self._call(
            "google_workspace.read_sheet", {"sheet_id": sheet_id, "range": sheet_range}
        )
        if result.get("stub") or result.get("error"):
            return [], [], str(result.get("error") or result.get("reason") or "sheet read failed")
        values = result.get("values") or []
        # The MCP transport may wrap the payload; unwrap one level if needed.
        if not values and isinstance(result.get("result"), dict):
            values = result["result"].get("values") or []
        if not values:
            return [], [], "sheet is empty or the range matched no cells"
        header_idx, header = find_header(values)
        self._header_offset = header_idx
        return header, values[header_idx + 1 :], None

    async def sync(
        self,
        sheet_id: Optional[str] = None,
        sheet_range: Optional[str] = None,
        write_back: bool = True,
        days: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """One reconciliation pass. Never raises."""
        settings = get_settings()
        sheet_id = sheet_id or settings.schedule_sheet_id
        sheet_range = sheet_range or settings.schedule_sheet_range
        if not sheet_id:
            return {"ok": False, "error": "SCHEDULE_SHEET_ID is not configured"}

        header, rows, err = await self.read_rows(sheet_id, sheet_range)
        if err:
            return {"ok": False, "error": err, "sheet_id": sheet_id, "range": sheet_range}

        cols = map_columns(header)
        day_cols = detect_day_columns(header)
        matrix = bool(day_cols)

        if not matrix and "task" not in cols:
            return {
                "ok": False,
                "error": (
                    "no task column and no weekday columns found — the header row "
                    "needs either one of: " + ", ".join(_COLUMNS["task"])
                    + "; or day columns (Mon, Tue, …)"
                ),
                "header_seen": [str(h) for h in header],
            }

        # A daily template repeats across all seven columns. Filing the whole
        # grid would put 150+ items a week on the hook, so only the requested
        # days are synced — today by default.
        wanted_days = {d.lower() for d in (days or [_today_name()])} if matrix else set()

        entries: List[Dict[str, Any]] = []
        if matrix:
            for e in flatten_matrix(header, rows, day_cols, cols, self._header_offset):
                if e["day"] in wanted_days:
                    entries.append(e)
        else:
            for offset, row in enumerate(rows):
                title = _cell(row, cols.get("task"))
                if not title:
                    continue
                entries.append(
                    {
                        "title": title,
                        "day": _cell(row, cols.get("day")).lower(),
                        "time": _cell(row, cols.get("time")),
                        "row_number": offset + self._header_offset + 2,
                        "col_index": None,
                        "duration": "",
                        "status": _cell(row, cols.get("status")).lower(),
                        "artifact": _cell(row, cols.get("artifact")),
                        "notes": _cell(row, cols.get("notes")),
                    }
                )

        existing = {
            parse_row_key(c.detail): c
            for c in await repo.list_all(limit=500)
            if parse_row_key(c.detail)
        }

        filed: List[Dict[str, Any]] = []
        updated: List[Dict[str, Any]] = []
        closed_from_sheet: List[str] = []
        skipped = max(0, len(rows) - len(entries)) if not matrix else 0

        for e in entries:
            marker = row_key(sheet_id, e["row_number"], e["col_index"])
            key = (sheet_id, e["row_number"], e["col_index"])
            sheet_status = str(e.get("status", "")).lower()
            sheet_artifact = str(e.get("artifact", ""))
            notes_bits = [str(e.get("notes", "")), e.get("duration", "")]
            detail = " ".join([b for b in notes_bits if b] + [marker]).strip()
            due = resolve_due(e["day"], "", e["time"])
            current = existing.get(key)

            if current is None:
                if sheet_status in _DONE_WORDS:
                    skipped += 1
                    continue
                created = await repo.create(
                    title=e["title"],
                    due_at=due,
                    detail=detail,
                    source="sheet",
                    status=(
                        CommitmentStatus.PROPOSED.value
                        if get_settings().commitment_require_approval
                        else CommitmentStatus.OPEN.value
                    ),
                )
                if created is not None:
                    filed.append(repo.to_dict(created))
                continue

            if current.title != e["title"] or current.detail != detail:
                await repo._mutate(current.id, title=e["title"][:500], detail=detail[:4000])
                updated.append({"id": str(current.id), "title": e["title"]})

            if current.status in (
                CommitmentStatus.OPEN.value,
                CommitmentStatus.PROPOSED.value,
            ):
                if sheet_status in _DONE_WORDS:
                    await repo.complete(
                        current.id,
                        artifact_kind="link" if sheet_artifact.startswith("http") else "text",
                        artifact_url=sheet_artifact if sheet_artifact.startswith("http") else None,
                        artifact_text=sheet_artifact
                        or f"Marked done in the schedule sheet ({marker})",
                    )
                    closed_from_sheet.append(str(current.id))
                elif current.due_at != due:
                    await repo._mutate(current.id, due_at=due, snooze_until=None)
                    updated.append({"id": str(current.id), "rescheduled_to": due.isoformat()})

        wrote = 0
        write_error = None
        if matrix:
            # A matrix cell holds the activity name; there is nowhere to write a
            # status without destroying the template.
            write_error = "matrix layout — status write-back not applicable"
        elif write_back:
            wrote, write_error = await self._write_back(sheet_id, cols, rows, existing)

        summary = {
            "ok": True,
            "sheet_id": sheet_id,
            "range": sheet_range,
            "layout": "matrix" if matrix else "long",
            "days_synced": sorted(wanted_days) if matrix else None,
            "rows_seen": len(rows),
            "entries_seen": len(entries),
            "filed": len(filed),
            "updated": len(updated),
            "closed_from_sheet": len(closed_from_sheet),
            "skipped": skipped,
            "written_back": wrote,
            "commitments": filed,
            "at": datetime.now(timezone.utc).isoformat(),
        }
        if write_error:
            summary["write_back_error"] = write_error
        logger.info("schedule_sync_done", **{k: v for k, v in summary.items() if k != "commitments"})
        return summary

    async def _write_back(
        self,
        sheet_id: str,
        cols: Dict[str, int],
        rows: List[List[Any]],
        existing: Dict[Any, Any],
    ) -> Tuple[int, Optional[str]]:
        """Push commitment outcomes into the Status/Artifact columns."""
        status_col = cols.get("status")
        artifact_col = cols.get("artifact")
        if status_col is None and artifact_col is None:
            return 0, "no status or artifact column in the sheet — sync is read-only"

        written = 0
        last_error = None
        # Refresh: rows may have been closed earlier in this same pass.
        current = {
            parse_row_key(c.detail): c
            for c in await repo.list_all(limit=500)
            if parse_row_key(c.detail)
        }
        for offset, row in enumerate(rows):
            row_number = offset + 2
            c = current.get((sheet_id, row_number, None))
            if c is None or c.status == CommitmentStatus.OPEN.value:
                continue
            desired_status = "done" if c.status == CommitmentStatus.DONE.value else "dropped"
            desired_artifact = c.artifact_url or (c.artifact_text or "")[:200]

            if _cell(row, status_col).lower() == desired_status:
                continue  # already in sync

            for col_idx, value in ((status_col, desired_status), (artifact_col, desired_artifact)):
                if col_idx is None or not value:
                    continue
                cell = f"{_column_letter(col_idx)}{row_number}"
                result = await self._call(
                    "google_workspace.write_sheet",
                    {"sheet_id": sheet_id, "range": cell, "values": [[value]]},
                )
                if result.get("error") or result.get("stub"):
                    last_error = str(result.get("error") or result.get("reason"))
                else:
                    written += 1
        return written, last_error


_sync: Optional[ScheduleSync] = None


def get_schedule_sync() -> ScheduleSync:
    global _sync
    if _sync is None:
        _sync = ScheduleSync()
    return _sync
