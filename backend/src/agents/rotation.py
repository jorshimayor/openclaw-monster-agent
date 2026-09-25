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
class Variant:
    """One rotation inside a theme.

    Four chains sharing a single "web3 study" slot would mean whichever one is
    listed first gets studied every day. A variant advances per day, so EVM,
    Solana, Cosmos and infra each come round in turn.
    """

    name: str
    tasks: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "Variant":
        return cls(
            name=str(raw.get("name") or "variant"),
            tasks=[str(t) for t in (raw.get("tasks") or [])],
        )


@dataclass
class Theme:
    theme: str
    label: str
    due_time: str = "19:00"
    tasks: List[str] = field(default_factory=list)
    sources: List[str] = field(default_factory=list)
    remind: bool = True
    variants: List[Variant] = field(default_factory=list)
    variant_name: Optional[str] = None
    plan: Optional[str] = None

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "Theme":
        return cls(
            theme=str(raw.get("theme") or "theme"),
            label=str(raw.get("label") or raw.get("theme") or "Theme"),
            due_time=str(raw.get("due_time") or "19:00"),
            tasks=[str(t) for t in (raw.get("tasks") or [])],
            sources=[str(s) for s in (raw.get("sources") or [])],
            remind=bool(raw.get("remind", True)),
            variants=[Variant.from_dict(v) for v in (raw.get("variants") or [])],
            plan=raw.get("plan"),
        )

    def resolve(self, day: date_cls, stride: int = 1) -> "Theme":
        """Pick today's variant, folding its tasks and name into the theme.

        `stride` is how many days pass between appearances of this theme — 1 for
        a daily theme, the cycle length for a cycled one. Indexing on the raw
        ordinal instead resonates whenever the cycle length is a multiple of the
        variant count: an 8-day cycle with 4 variants would show variant 0 on
        every single appearance, forever.
        """
        if not self.variants:
            return self
        occurrence = day.toordinal() // max(1, stride)
        picked = self.variants[occurrence % len(self.variants)]
        return Theme(
            theme=f"{self.theme}-{picked.name.lower().replace(' ', '-').replace('/', '-')}",
            label=f"{self.label} · {picked.name}",
            due_time=self.due_time,
            tasks=list(picked.tasks) + list(self.tasks),
            sources=list(self.sources),
            remind=self.remind,
            variants=[],
            variant_name=picked.name,
            plan=self.plan,
        )


def _expand_plan(theme: Theme, day: date_cls) -> Theme:
    """Fill a scheduled theme's tasks from its plan.

    Most themes cycle, so what lands today is the date modulo a cycle length.
    A plan does not cycle — it has a start, an end, and a week 31 that makes no
    sense before week 30 — so its tasks come from a resolver instead of from
    this file. The theme still files, reminds and closes like any other.
    """
    if theme.plan != "fellowship":
        return theme
    try:
        from .fellowship import tasks_for
    except Exception as exc:  # pragma: no cover - import guard
        logger.warning("fellowship_unavailable", error=str(exc))
        return theme
    scheduled = tasks_for(day)
    if not scheduled:
        # Before week 1 or after week 48 the theme goes quiet rather than
        # filing its standing tasks against a programme that is not running.
        return Theme(theme=theme.theme, label=theme.label, due_time=theme.due_time,
                     tasks=[], sources=theme.sources, remind=theme.remind, plan=theme.plan)
    theme.tasks = scheduled + list(theme.tasks)
    return theme


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

    daily = [_expand_plan(Theme.from_dict(t).resolve(day), day) for t in config.get("daily", [])]
    cycle = [Theme.from_dict(t) for t in config.get("cycle", [])]
    stride = max(1, len(cycle))
    cycled = cycle[cycle_index(day, len(cycle))].resolve(day, stride) if cycle else None

    upcoming = []
    for ahead in range(1, min(4, len(cycle) + 1)):
        nxt = date_cls.fromordinal(day.toordinal() + ahead)
        upcoming.append(
            {
                "date": nxt.isoformat(),
                "theme": cycle[cycle_index(nxt, len(cycle))].resolve(nxt, stride).label,
            }
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
