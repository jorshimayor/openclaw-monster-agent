"""Which themes today belongs to.

Left alone, whichever area has the most sheet rows quietly eats the week — the
AI tracker has 48 topics and the football calendar has one BUILD, so the tracker
would dominate every single day while video, writing, code review and job
applications never appeared at all.

So each day gets the `daily` themes (Web3 bounty and study, which are the
priority) plus exactly one theme from the `cycle`, advancing by date. Anchoring
on the date rather than a stored counter means the rotation survives restarts,
never drifts, and you can see what tomorrow holds.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date as date_cls, datetime, timezone
from typing import Any, Dict, List, Optional

from ..core.config import get_settings
from ..core.logging import get_logger
from .study_sync import _config_path

logger = get_logger("agents.rotation")


@dataclass
class Theme:
    theme: str
    label: str
    due_time: str = "19:00"
    tasks: List[str] = field(default_factory=list)
    sources: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "Theme":
        return cls(
            theme=str(raw.get("theme") or "theme"),
            label=str(raw.get("label") or raw.get("theme") or "Theme"),
            due_time=str(raw.get("due_time") or "19:00"),
            tasks=[str(t) for t in (raw.get("tasks") or [])],
            sources=[str(s) for s in (raw.get("sources") or [])],
        )


def load_rotation() -> Dict[str, Any]:
    try:
        data = json.loads(_config_path().read_text())
    except Exception as exc:
        logger.warning("rotation_config_unreadable", error=str(exc))
        return {"enabled": False, "daily": [], "cycle": []}
    return data.get("rotation") or {"enabled": False, "daily": [], "cycle": []}


def _local_today() -> date_cls:
    offset = get_settings().user_timezone_offset_hours
    from datetime import timedelta

    return (datetime.now(timezone.utc) + timedelta(hours=offset)).date()


def cycle_index(day: date_cls, length: int) -> int:
    """Position in the cycle, derived from the date.

    `toordinal()` counts days since year 1, so consecutive days always advance
    by exactly one — unlike day-of-year, which jumps at every new year and would
    repeat or skip a theme each January.
    """
    return day.toordinal() % length if length else 0


def themes_for(day: Optional[date_cls] = None) -> Dict[str, Any]:
    """{date, daily: [Theme], cycled: Theme|None, upcoming: [...]}"""
    day = day or _local_today()
    config = load_rotation()
    if not config.get("enabled"):
        return {"date": day.isoformat(), "enabled": False, "daily": [], "cycled": None, "upcoming": []}

    daily = [Theme.from_dict(t) for t in config.get("daily", [])]
    cycle = [Theme.from_dict(t) for t in config.get("cycle", [])]
    cycled = cycle[cycle_index(day, len(cycle))] if cycle else None

    upcoming = []
    for ahead in range(1, min(4, len(cycle) + 1)):
        nxt = date_cls.fromordinal(day.toordinal() + ahead)
        upcoming.append(
            {"date": nxt.isoformat(), "theme": cycle[cycle_index(nxt, len(cycle))].label}
        )

    return {
        "date": day.isoformat(),
        "enabled": True,
        "daily": daily,
        "cycled": cycled,
        "upcoming": upcoming,
    }


def active_source_keys(day: Optional[date_cls] = None) -> Optional[set]:
    """Study sources allowed to run today.

    None means "no gating configured" — every source runs, which is what
    happens when the rotation is switched off.
    """
    picked = themes_for(day)
    if not picked["enabled"]:
        return None
    allowed = set()
    for t in picked["daily"]:
        allowed.update(t.sources)
    if picked["cycled"]:
        allowed.update(picked["cycled"].sources)
    return allowed
