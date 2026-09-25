"""The Flow Research fellowship, as a schedule rather than a rotation.

Everything else in the rotation cycles: themes come round again, and which one
lands today is derived from the date modulo a cycle length. The fellowship does
not work like that. It is 48 dated weeks with a beginning and an end, week 17
depends on a decision made at week 17, and week 31 makes no sense before week
30. So it is resolved from a start date, not a cycle position.

One value has to be right — `start_date` in config/fellowship.json, the Monday
of week 1. Every due date and every reminder derives from it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date as date_cls, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..core.config import get_settings
from ..core.logging import get_logger

logger = get_logger("agents.fellowship")

TOTAL_WEEKS = 48


def _config_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "fellowship.json"


@dataclass
class WeekPlan:
    week: int
    block: str
    topic: str
    concepts: str = ""
    lab: str = ""
    reading: Optional[Dict[str, str]] = None
    deliverable: str = ""
    path: Optional[str] = None

    @property
    def label(self) -> str:
        suffix = f" · Path {self.path}" if self.path else ""
        return f"W{self.week:02d} {self.block}{suffix}"

    @property
    def slug(self) -> str:
        safe = "".join(c if c.isalnum() else "-" for c in self.topic.lower())
        while "--" in safe:
            safe = safe.replace("--", "-")
        return f"w{self.week:02d}-{safe.strip('-')[:48]}"


@dataclass
class ScheduledTask:
    """One line of work, with when it is due and how often it is filed.

    `day`/`time` map onto resolve_due, so "sunday"/"20:00" means this week's
    Sunday rather than a fixed date. `key` is the dedup identity: a task with
    one is filed once for the whole week, a task without one is filed fresh
    every day. The daily ones carry the pressure; the weekly ones are the gate.
    """

    text: str
    day: str = ""
    time: str = ""
    key: str = ""


@dataclass
class Position:
    """Where today sits on the 48 weeks."""

    start: date_cls
    today: date_cls
    week: int
    week_start: date_cls
    week_end: date_cls
    started: bool
    finished: bool
    anchor: date_cls | None = None  # the Monday week 1 begins on
    plan: Optional[WeekPlan] = None
    path: Optional[str] = None
    alternatives: List[WeekPlan] = field(default_factory=list)

    @property
    def days_in(self) -> int:
        return (self.today - self.week_start).days + 1

    @property
    def weeks_left(self) -> int:
        return max(0, TOTAL_WEEKS - self.week)


def load_config() -> Dict[str, Any]:
    try:
        return json.loads(_config_path().read_text())
    except Exception as exc:
        logger.warning("fellowship_config_unreadable", error=str(exc))
        return {"enabled": False, "weeks": []}


def _local_today() -> date_cls:
    offset = get_settings().user_timezone_offset_hours
    return (datetime.now(timezone.utc) + timedelta(hours=offset)).date()


def _plan_for(raw: Dict[str, Any], path: Optional[str]) -> tuple[Optional[WeekPlan], List[WeekPlan]]:
    """Resolve one week's entry, folding in the chosen path if there is one.

    While `path` is still null the caller gets both tracks back as alternatives
    rather than an arbitrary pick, because weeks 17-21 are exactly where the
    choice is supposed to be made deliberately.
    """
    base = dict(raw)
    paths = base.pop("paths", None)
    common = WeekPlan(
        week=base["week"], block=base.get("block", ""), topic=base.get("topic", ""),
        concepts=base.get("concepts", ""), lab=base.get("lab", ""),
        reading=base.get("reading"), deliverable=base.get("deliverable", ""),
    )
    if not paths:
        return common, []

    def merged(key: str) -> WeekPlan:
        side = paths[key]
        return WeekPlan(
            week=common.week, block=common.block,
            topic=side.get("topic") or common.topic,
            concepts=common.concepts,
            lab=side.get("lab") or common.lab,
            reading=side.get("reading") or common.reading,
            deliverable=common.deliverable, path=key,
        )

    if path in paths:
        return merged(path), []
    return None, [merged(k) for k in sorted(paths)]


def position(day: Optional[date_cls] = None, config: Optional[Dict[str, Any]] = None) -> Optional[Position]:
    """Where `day` falls on the programme, or None if it is switched off."""
    config = config or load_config()
    if not config.get("enabled"):
        return None
    try:
        start = date_cls.fromisoformat(str(config["start_date"]))
    except Exception:
        logger.warning("fellowship_start_date_invalid", value=config.get("start_date"))
        return None

    day = day or _local_today()
    # Week 1 is the calendar week containing start_date, counted from its Monday,
    # so a mid-week start still puts the whole of that week in week 1.
    anchor = start - timedelta(days=start.weekday())
    index = (day - anchor).days // 7
    week = index + 1

    week_start = anchor + timedelta(weeks=index)
    pos = Position(
        start=start, today=day, week=week,
        week_start=week_start, week_end=week_start + timedelta(days=6),
        started=day >= anchor, finished=week > TOTAL_WEEKS,
        anchor=anchor,
        path=config.get("path"),
    )
    if not pos.started or pos.finished:
        return pos

    raw = next((w for w in config.get("weeks", []) if w.get("week") == week), None)
    if raw:
        pos.plan, pos.alternatives = _plan_for(raw, config.get("path"))
    return pos


# The week closes on Sunday evening. Everything weekly lands here.
WEEK_CLOSES = ("sunday", "20:00")


def scheduled_for(day: Optional[date_cls] = None, config: Optional[Dict[str, Any]] = None) -> List[ScheduledTask]:
    """This week's fellowship work, with due dates and filing frequency.

    The anchor reading and the lab are filed every day, because twenty hours a
    week does not happen by remembering on Monday. The book chapter, the
    deliverable and the artifact are filed once and due Sunday — chasing a
    weekly chapter daily is noise, and the artifact is the gate, not the grind.
    """
    config = config or load_config()
    pos = position(day, config)
    if pos is None or not pos.started or pos.finished:
        return []

    wk = f"w{pos.week:02d}"

    if pos.plan is None and pos.alternatives:
        # Week 17-21 with no path chosen. The decision IS the task.
        both = " | ".join(f"Path {p.path}: {p.topic}" for p in pos.alternatives)
        return [ScheduledTask(
            text=(f"W{pos.week:02d} — choose your track before anything else this week. "
                  f"Set \"path\" in backend/config/fellowship.json to \"A\" or \"B\". {both}"),
            key=f"{wk}-path-choice",
        )]

    plan = pos.plan
    if plan is None:
        return []

    out: List[ScheduledTask] = []
    if plan.reading:
        r = plan.reading
        out.append(ScheduledTask(
            f"{plan.label} — ANCHOR READING, read and reproduce: "
            f"{r['title']} ({r['cite']}) — {r['url']}"
        ))
    if plan.lab:
        out.append(ScheduledTask(f"{plan.label} — lab: {plan.lab}"))

    for chapter in books_for(pos.week, config):
        out.append(ScheduledTask(chapter, *WEEK_CLOSES, key=f"{wk}-book"))

    if plan.deliverable:
        out.append(ScheduledTask(
            f"{plan.label} — DELIVERABLE: {plan.deliverable}",
            *WEEK_CLOSES, key=f"{wk}-deliverable",
        ))

    for index, extra in enumerate(extras_for(pos.week, config)):
        out.append(ScheduledTask(extra, *WEEK_CLOSES, key=f"{wk}-extra-{index}"))

    out.append(ScheduledTask(
        f"W{pos.week:02d} weekly update by Sunday — what shipped, what broke, what is "
        "next. This is the habit the programme grades, not an extra — "
        "https://learn.flowresearch.tech/",
        *WEEK_CLOSES, key=f"{wk}-update",
    ))

    # The gate. Nothing about this week is finished until something exists that
    # someone else could open, which is also the only thing that closes it —
    # the commitment will not accept an acknowledgement in place of a link.
    out.append(ScheduledTask(
        f"W{pos.week:02d} CLOSE THE WEEK by Sunday 20:00 — post the artifact: the "
        f"notebook (fellowship/labs/{plan.slug}.ipynb), a published article, or a "
        "link. Saying it is done does not close this.",
        *WEEK_CLOSES, key=f"{wk}-artifact",
    ))
    return out


def tasks_for(day: Optional[date_cls] = None, config: Optional[Dict[str, Any]] = None) -> List[str]:
    return [t.text for t in scheduled_for(day, config)]


def books_for(week: int, config: Optional[Dict[str, Any]] = None) -> List[str]:
    """One chapter a week, from whatever books are running alongside the plan.

    Chapter number is derived from the week rather than stored, so nothing has
    to be ticked off for the count to stay right. A book runs out rather than
    looping.
    """
    config = config or load_config()
    out = []
    for book in config.get("books") or []:
        start = int(book.get("start_week", 1))
        if week < start:
            continue
        index = week - start
        chapters = book.get("chapters") or []
        total = int(book.get("chapter_count") or len(chapters))
        if not total or index >= total:
            continue
        title = chapters[index] if index < len(chapters) else ""
        label = f"ch.{index + 1}" + (f" — {title}" if title else "")
        url = f" — {book['url']}" if book.get("url") else ""
        out.append(
            f"W{week:02d} BOOK: {book['title']} ({book.get('author', '')}) {label}{url}"
        )
    return out


def extras_for(week: int, config: Optional[Dict[str, Any]] = None) -> List[str]:
    """Work handed to you during the programme, filed against the week it is due.

    The 48-week plan is the skeleton; assignments, set books and project briefs
    arrive on top of it and are the part that actually gets marked. They live in
    `assignments` in the config so they file and nag exactly like planned work
    rather than sitting in a document nobody opens.
    """
    config = config or load_config()
    out = []
    for item in config.get("assignments") or []:
        if int(item.get("week", 0)) != week:
            continue
        kind = str(item.get("kind", "assignment")).upper()
        title = item.get("title", "")
        url = item.get("url") or ""
        due = f" (due {item['due']})" if item.get("due") else ""
        out.append(f"W{week:02d} {kind}{due}: {title}" + (f" — {url}" if url else ""))
    return out


def summary(day: Optional[date_cls] = None) -> Dict[str, Any]:
    """For /day and /study — where you are and what the week holds."""
    pos = position(day)
    if pos is None:
        return {"enabled": False}
    config = load_config()
    plan = pos.plan
    return {
        "enabled": True,
        "cohort": config.get("cohort"),
        "start_date": pos.start.isoformat(),
        # The Monday week 1 runs from, which is not pos.week_start before the
        # programme begins — that one is the week today happens to fall in.
        "programme_start": (pos.anchor or pos.start).isoformat(),
        "week": pos.week,
        "total_weeks": TOTAL_WEEKS,
        "weeks_left": pos.weeks_left,
        "started": pos.started,
        "finished": pos.finished,
        "week_start": pos.week_start.isoformat(),
        "week_end": pos.week_end.isoformat(),
        "day_of_week": pos.days_in,
        "path": pos.path,
        "block": plan.block if plan else None,
        "topic": plan.topic if plan else None,
        "reading": plan.reading if plan else None,
        "lab": plan.lab if plan else None,
        "deliverable": plan.deliverable if plan else None,
        "awaiting_path_choice": plan is None and bool(pos.alternatives),
        "alternatives": [
            {"path": a.path, "topic": a.topic, "lab": a.lab, "reading": a.reading}
            for a in pos.alternatives
        ],
        "tasks": tasks_for(day),
    }
