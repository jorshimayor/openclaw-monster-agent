"""Turn a finished pipeline report into commitments the assistant will chase.

A weekly plan that lands on Telegram and is never mentioned again is a
newsletter, not an assistant. This module reads the final report, pulls out the
things the *user* is supposed to do (not what the agents did), and files each
one with a due time so the nag engine can start chasing it.

Two strategies, in order:
  1. LLM extraction — strict JSON, handles free-form reports.
  2. Deterministic markdown fallback — day headings ("**Monday, August 24**")
     with bullet items under them, which is the exact shape the planning
     prompts produce. Runs when the LLM is unavailable or returns nothing.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from ..core import commitment_repo as repo
from ..core.config import get_settings
from ..core.logging import get_logger

logger = get_logger("agents.commitment_extractor")

_WEEKDAYS = {
    "monday": 0, "mon": 0,
    "tuesday": 1, "tue": 1, "tues": 1,
    "wednesday": 2, "wed": 2,
    "thursday": 3, "thu": 3, "thur": 3, "thurs": 3,
    "friday": 4, "fri": 4,
    "saturday": 5, "sat": 5,
    "sunday": 6, "sun": 6,
}

# Rough local times a plan means when it says "morning"/"evening".
_TIME_OF_DAY = {
    "morning": time(9, 0),
    "midday": time(12, 30),
    "noon": time(12, 30),
    "afternoon": time(15, 0),
    "evening": time(19, 0),
    "night": time(21, 0),
    "tonight": time(21, 0),
}

_DEFAULT_TIME = time(19, 0)  # evenings, for a plan built around a day job

_EXTRACT_PROMPT = """You are extracting the user's OWN action items from a report an AI assistant produced for them.

Return ONLY a JSON array. No prose, no markdown fence. Each element:
{{"title": "<imperative, <=110 chars>", "detail": "<one sentence of context, optional>", "day": "<monday|tuesday|...|today|tomorrow or empty>", "time_of_day": "<morning|afternoon|evening|night or empty>"}}

Rules:
- ONLY things the USER must personally do. Skip anything the assistant already did, skip observations, skip background.
- Merge duplicates. Maximum 10 items. If the report contains no user action items, return [].
- Titles start with a verb: "Rewrite the chelsea_bot README for a hiring manager".
- Use the day/time the report assigns. If it assigns none, leave both empty.

TASK THE USER ASKED FOR:
{description}

REPORT:
{report}

JSON array:"""


def _local_offset() -> timedelta:
    return timedelta(hours=get_settings().user_timezone_offset_hours)


def _now_local() -> datetime:
    return datetime.now(timezone.utc) + _local_offset()


def resolve_due(day: str, time_of_day: str, now_local: Optional[datetime] = None) -> datetime:
    """Map ("monday", "evening") onto the next such local moment, returned UTC.

    An empty day means "today if that slot is still ahead, otherwise tomorrow"
    — a plan item with no assigned day is still a thing due soon, not someday.
    """
    now_local = now_local or _now_local()
    day = (day or "").strip().lower()
    tod = (time_of_day or "").strip().lower()
    at = _TIME_OF_DAY.get(tod, _DEFAULT_TIME)

    if day in ("today", "tonight", ""):
        target = now_local.replace(hour=at.hour, minute=at.minute, second=0, microsecond=0)
        if target <= now_local:
            target = target + timedelta(days=1)
    elif day == "tomorrow":
        target = (now_local + timedelta(days=1)).replace(
            hour=at.hour, minute=at.minute, second=0, microsecond=0
        )
    elif day in _WEEKDAYS:
        delta = (_WEEKDAYS[day] - now_local.weekday()) % 7
        target = (now_local + timedelta(days=delta)).replace(
            hour=at.hour, minute=at.minute, second=0, microsecond=0
        )
        if delta == 0 and target <= now_local:
            target = target + timedelta(days=7)
    else:
        target = now_local.replace(hour=at.hour, minute=at.minute, second=0, microsecond=0)
        if target <= now_local:
            target = target + timedelta(days=1)

    return (target - _local_offset()).replace(tzinfo=timezone.utc)


def _strip_md(s: str) -> str:
    s = re.sub(r"\*\*(.+?)\*\*", r"\1", s)
    s = re.sub(r"`([^`]+)`", r"\1", s)
    return s.strip(" -*·:\t")


def parse_markdown_plan(report: str) -> List[Dict[str, str]]:
    """Fallback: day headings + bullets beneath them.

    Matches lines like `**Monday, August 24**` / `## Tuesday` followed by
    `- **Evening**: do the thing`.
    """
    items: List[Dict[str, str]] = []
    current_day = ""
    for raw in str(report).splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        heading = _strip_md(re.sub(r"^\s*#{1,6}\s*", "", line))
        first_word = heading.split(",")[0].split()[0].lower() if heading.split() else ""
        is_heading = bool(re.match(r"^\s*(#{1,6}\s+|\*\*)", line)) and first_word in _WEEKDAYS
        if is_heading:
            current_day = first_word
            continue
        m = re.match(r"^\s*[-*]\s+(.*)", line)
        if not m:
            continue
        body = _strip_md(m.group(1))
        if not body or len(body) < 8:
            continue
        tod = ""
        lead = re.match(r"^([A-Za-z]+)\s*[:\-–]\s*(.+)$", body)
        if lead and lead.group(1).lower() in _TIME_OF_DAY:
            tod = lead.group(1).lower()
            body = lead.group(2).strip()
        items.append({"title": body[:200], "detail": "", "day": current_day, "time_of_day": tod})
        if len(items) >= 10:
            break
    return items


def _parse_json_array(text: str) -> List[Dict[str, Any]]:
    raw = str(text or "").strip()
    fence = re.search(r"```(?:json)?\s*(.+?)```", raw, re.S)
    if fence:
        raw = fence.group(1).strip()
    start, end = raw.find("["), raw.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return []
    try:
        parsed = json.loads(raw[start : end + 1])
    except Exception:
        return []
    return [p for p in parsed if isinstance(p, dict)] if isinstance(parsed, list) else []


async def extract_items(description: str, report: str, llm: Any = None) -> List[Dict[str, str]]:
    """Action items as {title, detail, day, time_of_day}. Never raises."""
    if not (report or "").strip():
        return []
    if llm is not None:
        try:
            from ..core.types import AgentRole

            result = await llm.generate(
                _EXTRACT_PROMPT.format(
                    description=str(description)[:1200], report=str(report)[:8000]
                ),
                AgentRole.PERSONAL_ASSISTANT,
            )
            items = _parse_json_array(result.get("response", ""))
            cleaned = [
                {
                    "title": str(i.get("title", "")).strip()[:200],
                    "detail": str(i.get("detail", "") or "").strip()[:800],
                    "day": str(i.get("day", "") or "").strip().lower(),
                    "time_of_day": str(i.get("time_of_day", "") or "").strip().lower(),
                }
                for i in items
                if str(i.get("title", "")).strip()
            ]
            if cleaned:
                return cleaned[:10]
            logger.info("commitment_extract_llm_empty")
        except Exception as exc:
            logger.warning("commitment_extract_llm_failed", error=str(exc))
    return parse_markdown_plan(report)[:10]


async def extract_and_file(
    description: str,
    report: str,
    task_id: Optional[UUID] = None,
    llm: Any = None,
) -> List[Dict[str, Any]]:
    """Extract, persist, and return the filed commitments. Never raises."""
    settings = get_settings()
    if not settings.commitment_auto_extract:
        return []
    try:
        items = await extract_items(description, report, llm=llm)
    except Exception as exc:
        logger.warning("commitment_extract_failed", error=str(exc))
        return []

    filed: List[Dict[str, Any]] = []
    for item in items:
        try:
            due = resolve_due(item.get("day", ""), item.get("time_of_day", ""))
            row = await repo.create(
                title=item["title"],
                due_at=due,
                detail=item.get("detail") or None,
                source="task",
                task_id=task_id,
            )
            if row is not None:
                filed.append(repo.to_dict(row))
        except Exception as exc:
            logger.warning("commitment_file_failed", title=item.get("title", "")[:60], error=str(exc))
    if filed:
        logger.info("commitments_filed", count=len(filed), task_id=str(task_id) if task_id else None)
    return filed
