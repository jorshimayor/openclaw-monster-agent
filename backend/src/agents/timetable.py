"""Turning timetable rows into blocks that have a shape.

A row gives a start time, a label and a duration. The page needs an end, and
it needs the blocks not to overlap, because a timeline that draws two things
in the same place is worse than a list.

Three problems this handles, all of them real in the sheet as written:

  - no end time anywhere, so nothing could show how long a block runs
  - "10:45 PM" for a morning break, which sorts to the end of the day
  - Breakfast and Deep Block 2 both at 09:00, where the duration column says
    what was meant
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from ..core.logging import get_logger

logger = get_logger("agents.timetable")

_DURATION = re.compile(r"(\d+(?:\.\d+)?)\s*(hour|hr|h|min|minute)", re.I)


def parse_duration(text: str) -> Optional[int]:
    """"90 mins" -> 90, "1 hour" -> 60, "1.5 hours" -> 90."""
    if not text:
        return None
    total = 0
    found = False
    for amount, unit in _DURATION.findall(str(text)):
        value = float(amount)
        total += value * (60 if unit.lower().startswith("h") else 1)
        found = True
    return int(total) if found and total > 0 else None


def _minutes(hhmm: str) -> int:
    hours, _, mins = hhmm.partition(":")
    return int(hours) * 60 + int(mins)


def _hhmm(minutes: int) -> str:
    minutes %= 24 * 60
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def fix_meridiem(blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Correct an AM/PM that contradicts the order of the rows.

    A timetable is written in chronological order, so a row whose time jumps
    backwards past its neighbours has the wrong half of the day. The sheet
    says "10:45 PM" for a break that sits between a block ending at 10:45 and
    a study session at 11:00; flipping it to AM is the only reading that keeps
    the rows in the order they were written.

    Row order is the evidence here, so this runs before sorting.

    A correction has to carry forward: once the break is read as 10:45, the
    11:00 study session after it is in order. Comparing against the row as
    written would make that session look like the backwards jump instead, and
    flip it to 23:00.
    """
    out: List[Dict[str, Any]] = []
    for i, block in enumerate(blocks):
        current = _minutes(block["start"])
        before = _minutes(out[-1]["start"]) if out else None
        after = _minutes(blocks[i + 1]["start"]) if i + 1 < len(blocks) else None

        out_of_order = (before is not None and current < before) or (
            after is not None and current > after
        )
        if out_of_order:
            flipped = current - 12 * 60 if current >= 12 * 60 else current + 12 * 60
            fits = (before is None or flipped >= before) and (
                after is None or flipped <= after
            )
            if fits:
                logger.info(
                    "timetable_meridiem_corrected",
                    label=block.get("label"), was=block["start"], now=_hhmm(flipped),
                )
                block = {**block, "start": _hhmm(flipped), "meridiem_corrected": True}
        out.append(block)
    return out


def add_ends(blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Give every block an end, and stop them overlapping.

    The end comes from the duration column. Where a block would start before
    the previous one finished — Breakfast at 09:00 for fifteen minutes and a
    ninety-minute block also written as 09:00 — the later block is pushed to
    where the earlier one ends. The duration is what was meant; the start
    column was approximate.

    A block with no parsable duration runs until the next one starts, which is
    the only honest guess available.
    """
    ordered = sorted(blocks, key=lambda b: _minutes(b["start"]))
    out: List[Dict[str, Any]] = []

    for i, block in enumerate(ordered):
        start = _minutes(block["start"])
        if out:
            previous_end = _minutes(out[-1]["end"])
            if start < previous_end:
                start = previous_end

        minutes = parse_duration(block.get("duration", ""))
        if minutes is None:
            nxt = _minutes(ordered[i + 1]["start"]) if i + 1 < len(ordered) else None
            minutes = max(15, (nxt - start)) if nxt and nxt > start else 30
            inferred = True
        else:
            inferred = False

        out.append({
            **block,
            "start": _hhmm(start),
            "end": _hhmm(start + minutes),
            "minutes": minutes,
            "duration_inferred": inferred,
            "shifted": start != _minutes(block["start"]),
        })
    return out


def shape(blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Rows in, drawable blocks out."""
    return add_ends(fix_meridiem(blocks))
