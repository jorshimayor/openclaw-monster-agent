"""What to study in each block, and what to study it with.

The timetable says when you work. The rotation says what the work is. Until
now those two lived apart: the sheet drew "90 min Deep Block 1" and the
rotation filed "RareSkills: Proxy patterns" at some due time that happened to
land nearby. You had to hold the mapping in your head.

This joins them. Each rotation theme names the block it belongs in, matched on
the sheet's own label, and every task it carries is split into the instruction
and the link it ends with — so a block can show the thing to do and the page to
do it from, rather than a time and a title.

Matching is by label, not by clock. Pairing on due_time alone put RareSkills in
Morning Tea and the fellowship in dinner, because a due time is when you are
chased about something, which is not the same question as where it belongs.
A theme with no block still falls back to the clock, so nothing silently
disappears when a label is renamed in the sheet.
"""

from __future__ import annotations

import re
from datetime import date as date_cls
from typing import Any, Dict, List, Optional

from ..core.logging import get_logger

logger = get_logger("agents.daily_plan")

# A task reads "do the thing — https://where". Any trailing URL is the
# resource; everything before it is the instruction.
_URL = re.compile(r"(https?://\S+)")
_TRAILING_DASH = re.compile(r"\s*[—–-]\s*$")


def split_resource(task: str) -> Dict[str, Optional[str]]:
    """"One chapter — https://x" -> {text: "One chapter", url: "https://x"}."""
    text = str(task or "").strip()
    found = _URL.search(text)
    if not found:
        return {"text": text, "url": None}
    url = found.group(1).rstrip(".,);")
    without = (text[: found.start()] + text[found.end() :]).strip()
    return {"text": _TRAILING_DASH.sub("", without).strip() or text, "url": url}


def _as_task(value: Any) -> Optional[str]:
    """A reading entry is {title, cite, url}, not a sentence.

    Stringifying it put a Python dict on the page. Rendered back into the
    "instruction — url" shape, it goes through the same splitter as every
    other task and comes out as a title with a link behind it.
    """
    if isinstance(value, dict):
        title = str(value.get("title") or "").strip()
        cite = str(value.get("cite") or "").strip()
        url = str(value.get("url") or "").strip()
        if not title and not url:
            return None
        head = f"{title} ({cite})" if title and cite else title or url
        return f"{head} — {url}" if url else head
    text = str(value or "").strip()
    return text or None


def _minutes(hhmm: str) -> int:
    hours, _, mins = str(hhmm or "0:00").partition(":")
    try:
        return int(hours) * 60 + int(mins or 0)
    except ValueError:
        return 0


def _match_by_label(blocks: List[Dict[str, Any]], wanted: str) -> Optional[int]:
    if not wanted:
        return None
    needle = wanted.strip().lower()
    for i, block in enumerate(blocks):
        if needle in str(block.get("label", "")).lower():
            return i
    return None


def _match_by_clock(blocks: List[Dict[str, Any]], due_time: str) -> Optional[int]:
    """The block the due time falls inside, else the last one starting before it."""
    at = _minutes(due_time)
    fallback = None
    for i, block in enumerate(blocks):
        start, end = _minutes(block.get("start", "")), _minutes(block.get("end", ""))
        if start <= at < end:
            return i
        if start <= at:
            fallback = i
    return fallback


def _entry(
    label: str, theme: str, tasks: List[str], kind: str, hooked: bool = False
) -> Dict[str, Any]:
    """One strand of work on a block.

    A theme whose tasks are filled by a hook — an ordered track, the
    fellowship week — can come back empty when the thing behind the hook is
    unreachable. Rendering that as a bare heading is the worst of both: the
    block looks scheduled and says nothing. `unavailable` lets the page tell
    you the difference between "nothing today" and "could not load".
    """
    items = [split_resource(t) for t in tasks if str(t).strip()]
    entry = {"theme": theme, "label": label, "kind": kind, "items": items}
    if not items and hooked:
        entry["unavailable"] = True
        entry["items"] = [
            {
                "text": "Could not load this — the backend could not reach its store.",
                "url": None,
            }
        ]
    return entry


def attach(
    day: date_cls,
    blocks: List[Dict[str, Any]],
    themes: Optional[Dict[str, Any]] = None,
    fellowship: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Give every block a `plan`: what this hour is for, with its links.

    Blocks are returned as given, each with a `plan` list that is usually
    empty — most of the day is upkeep, and inventing study for breakfast would
    make the ones that matter harder to see.
    """
    # Replaced, not appended to: `attach` has to be safe to run twice over the
    # same blocks, and a setdefault here quietly doubled every strand when it
    # was handed blocks that had already been through it once.
    for block in blocks:
        block["plan"] = []
    if not blocks:
        return blocks

    if themes is None:
        from .rotation import themes_for

        themes = themes_for(day)

    picked = list(themes.get("daily") or [])
    if themes.get("cycled"):
        picked.append(themes["cycled"])

    for theme in picked:
        # Themes arrive as dataclasses from the rotation, dicts from a test.
        get = theme.get if isinstance(theme, dict) else lambda k, d=None: getattr(theme, k, d)
        index = _match_by_label(blocks, get("block", "") or "")
        if index is None:
            index = _match_by_clock(blocks, get("due_time", "") or "")
        if index is None:
            continue
        blocks[index]["plan"].append(
            _entry(
                label=get("label", "") or get("theme", "") or "Study",
                theme=get("base", "") or get("theme", "") or "study",
                tasks=list(get("tasks", []) or []),
                kind="daily" if theme is not themes.get("cycled") else "cycled",
                hooked=bool(get("plan", "")),
            )
        )

    _attach_fellowship(day, blocks, fellowship)
    return blocks


def _attach_fellowship(
    day: date_cls, blocks: List[Dict[str, Any]], summary: Optional[Dict[str, Any]]
) -> None:
    """The week's reading goes on the reading block, the lab on its own block.

    The fellowship is the one strand with an outside deadline, and its week
    carries two different kinds of work. Filing both against one slot buries
    the reading, which is the part that has to happen early to be any use.
    """
    if summary is None:
        from .fellowship import summary as fellowship_summary

        summary = fellowship_summary(day)
    if not summary or not summary.get("enabled") or not summary.get("started"):
        return

    week = summary.get("week")
    raw_reading = summary.get("reading")
    readings = raw_reading if isinstance(raw_reading, list) else [raw_reading]
    tasks = [t for t in (_as_task(r) for r in readings) if t]
    if tasks:
        index = _match_by_label(blocks, "book reading")
        if index is not None:
            blocks[index]["plan"].append(
                _entry(
                    label=f"Fellowship week {week} · paper",
                    theme="flow-fellowship",
                    tasks=tasks,
                    kind="fellowship",
                )
            )

    try:
        from .fellowship import books_for

        chapters = books_for(int(week)) if week else []
    except Exception as exc:  # a malformed book list must not take the page down
        logger.warning("fellowship_books_failed", error=str(exc))
        chapters = []
    if chapters:
        index = _match_by_label(blocks, "book reading")
        if index is not None:
            blocks[index]["plan"].append(
                _entry(
                    label="This week's chapter",
                    theme="flow-fellowship-book",
                    tasks=[str(c) for c in chapters],
                    kind="weekly",
                )
            )
