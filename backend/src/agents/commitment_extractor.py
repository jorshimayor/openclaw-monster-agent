"""Turn a finished pipeline report into commitments the assistant will chase.

A weekly plan that lands on Telegram and is never mentioned again is a
newsletter, not an assistant. This module reads the final report, pulls out the
things the *user* is supposed to do, and files each one with a due time so the
nag engine can start chasing it.

The hard part is not extraction, it's restraint. The pipeline's "final report"
frequently contains its own scaffolding — team-assembly tables, prompt-injection
strategy, verifier criteria — and an eager parser turns "Estimated effort: < 5
min" into something the user gets nagged about. So:

  1. LLM extraction runs first, and is told to extract from the REQUEST when the
     report is internal planning noise.
  2. The markdown fallback only fires on reports that are actually day-by-day
     plans (it requires weekday headings). On anything else it returns nothing
     rather than scraping every bullet in sight.
  3. Everything is filtered through `looks_like_scaffolding()` and deduped, then
     hard-capped.

A one-line request must never produce ten commitments.
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
from ..models.commitment import CommitmentStatus

logger = get_logger("agents.commitment_extractor")

MAX_COMMITMENTS_PER_TASK = 10

_STOPWORDS = {
    "the", "a", "an", "and", "or", "for", "with", "from", "into", "that", "this",
    "your", "you", "yours", "please", "can", "could", "would", "should", "will",
    "about", "out", "over", "under", "then", "than", "them", "they", "have", "has",
}

_WEEKDAYS = {
    "monday": 0, "mon": 0,
    "tuesday": 1, "tue": 1, "tues": 1,
    "wednesday": 2, "wed": 2,
    "thursday": 3, "thu": 3, "thur": 3, "thurs": 3,
    "friday": 4, "fri": 4,
    "saturday": 5, "sat": 5,
    "sunday": 6, "sun": 6,
}

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

# Labels the pipeline uses for its own bookkeeping. A line that opens with one
# of these is describing the work, not asking the user to do anything.
_SCAFFOLDING_LABELS = {
    "scope", "dependencies", "dependency", "risk", "risks", "pattern",
    "justification", "rationale", "estimated effort", "effort", "confidence",
    "owner", "wave", "waves", "agent", "agents", "tool", "tools", "purpose",
    "criteria", "verifier", "verification", "note", "notes", "assumption",
    "assumptions", "input", "inputs", "output", "outputs", "status",
    "complexity", "step", "steps", "prompt", "model", "latency", "summary",
    "overall confidence", "final report", "task", "result", "results",
    "execution", "plan", "strategy", "constraints", "limitations",
}

_SCAFFOLDING_PATTERNS = [
    re.compile(r"^\s*(wave|step|phase)\s*\d+\b", re.I),
    re.compile(r"\bagent\s+prompt\b", re.I),
    re.compile(r"^\s*[a-z_]+agent\b", re.I),
    re.compile(r"\bworkflowpattern\b", re.I),
    # Third-person assertions about the output ("Event title matches ...",
    # "Start time is ...") are verifier criteria, not user tasks.
    re.compile(r"^\s*\w[\w\s]{0,40}\s+(matches|is set|is|are|appears?|exists?)\s+", re.I),
    re.compile(r"^\s*(the\s+)?(system|pipeline|orchestrator|assistant|agent)\b", re.I),
    re.compile(r"^[\s\W]*$"),
]

# "1:30 pm", "13:30", "1.30pm", "9am"
_CLOCK_RE = re.compile(
    r"\b(?P<h>[01]?\d|2[0-3])\s*(?:[:.]\s*(?P<m>[0-5]\d))?\s*(?P<ampm>am|pm|a\.m\.|p\.m\.)?\b",
    re.I,
)

_EXTRACT_PROMPT = """Extract the action items the USER personally has to do.

Return ONLY a JSON array. No prose, no markdown fence. Each element:
{{"title": "<imperative, <=110 chars>", "detail": "<one sentence of context, optional>", "day": "<monday|tuesday|...|today|tomorrow or empty>", "time_of_day": "<morning|afternoon|evening|night or empty>", "at_time": "<HH:MM 24-hour, or empty>"}}

CRITICAL RULES:
- The REPORT below is often an AI pipeline's internal working notes. NEVER extract
  its scaffolding. Reject anything that is: a scope/risk/effort/dependency note, a
  pattern or justification, an agent name or agent prompt, a wave/step/phase label,
  a verifier criterion ("Event title matches X", "Start time is Y"), a table row, or
  anything inside a code block.
- If the report is mostly such scaffolding, IGNORE IT and extract straight from the
  REQUEST instead.
- Extract only what a person would put on a to-do list. If the REQUEST is one simple
  thing, return exactly ONE item.
- Copy any explicit clock time from the request into "at_time" (24-hour). "1:30 pm"
  becomes "13:30". Times are already in the user's local zone — do not convert them.
- NEVER return the request itself back as an item. If the REQUEST asked YOU to write,
  research, or build something, producing it was YOUR job — the report IS the
  deliverable. Only list things the user must still personally do afterwards.
- Return [] if there is genuinely nothing for the user to do. That is the common
  case for research and writing requests.
- Maximum {max_items} items.

EXAMPLE
REQUEST: Remind me to pick Ibrahim up at Penthoush estate by 1:30 pm WAT
CORRECT: [{{"title": "Pick up Ibrahim at Penthoush Estate", "detail": "", "day": "today", "time_of_day": "", "at_time": "13:30"}}]
WRONG:   [{{"title": "Scope: 1 x reminder"}}, {{"title": "CalendarAgent Prompt"}}, {{"title": "Start time is 13:30 WAT"}}]

REQUEST:
{description}

REPORT:
{report}

JSON array:"""


def _local_offset() -> timedelta:
    return timedelta(hours=get_settings().user_timezone_offset_hours)


def _now_local() -> datetime:
    return datetime.now(timezone.utc) + _local_offset()


def parse_clock(text_value: str) -> Optional[str]:
    """"1:30 pm" / "13:30" / "9am" → "HH:MM". None when there's no clock time."""
    if not text_value:
        return None
    m = _CLOCK_RE.search(str(text_value))
    if not m:
        return None
    hour = int(m.group("h"))
    minute = int(m.group("m") or 0)
    ampm = (m.group("ampm") or "").replace(".", "").lower()
    if ampm == "pm" and hour < 12:
        hour += 12
    elif ampm == "am" and hour == 12:
        hour = 0
    elif not ampm and m.group("m") is None:
        # A bare number with no colon and no am/pm ("by 5") is too ambiguous.
        return None
    if not (0 <= hour <= 23):
        return None
    return f"{hour:02d}:{minute:02d}"


def resolve_due(
    day: str,
    time_of_day: str,
    at_time: str = "",
    now_local: Optional[datetime] = None,
) -> datetime:
    """Map ("monday", "evening") or ("today", "", "13:30") onto a UTC instant.

    An explicit clock time is honoured exactly. When one is given for today and
    it has already passed, the commitment stays due today (and so nags at once)
    — a reminder you missed is more urgent, not less. Fuzzy slots with no clock
    time roll forward instead, because "evening" with no date means the next one.
    """
    now_local = now_local or _now_local()
    day = (day or "").strip().lower()
    tod = (time_of_day or "").strip().lower()
    clock = parse_clock(at_time) if at_time else None

    if clock:
        hh, mm = clock.split(":")
        at = time(int(hh), int(mm))
    else:
        at = _TIME_OF_DAY.get(tod, _DEFAULT_TIME)

    def _at(d: datetime) -> datetime:
        return d.replace(hour=at.hour, minute=at.minute, second=0, microsecond=0)

    if day in ("today", "tonight", ""):
        target = _at(now_local)
        if target <= now_local and not clock:
            target += timedelta(days=1)
    elif day == "tomorrow":
        target = _at(now_local + timedelta(days=1))
    elif day in _WEEKDAYS:
        delta = (_WEEKDAYS[day] - now_local.weekday()) % 7
        target = _at(now_local + timedelta(days=delta))
        if delta == 0 and target <= now_local and not clock:
            target += timedelta(days=7)
    else:
        target = _at(now_local)
        if target <= now_local and not clock:
            target += timedelta(days=1)

    return (target - _local_offset()).replace(tzinfo=timezone.utc)


def _strip_md(s: str) -> str:
    s = re.sub(r"\*\*(.+?)\*\*", r"\1", s)
    s = re.sub(r"`([^`]+)`", r"\1", s)
    return s.strip(" -*·:\t")


def looks_like_scaffolding(title: str) -> bool:
    """True when a candidate is the pipeline describing itself.

    This is the guard that stops "Estimated effort: < 5 min (human + agent)"
    from becoming something you get nagged about every 10 minutes.
    """
    t = _strip_md(str(title or "")).strip()
    if len(t) < 8:
        return True
    for pat in _SCAFFOLDING_PATTERNS:
        if pat.search(t):
            return True
    # "Label: value" where the label is pipeline bookkeeping.
    head, sep, _ = t.partition(":")
    if sep and head.strip().lower() in _SCAFFOLDING_LABELS:
        return True
    if t.strip().startswith("{") or t.strip().startswith("["):
        return True  # raw JSON leaked out of a code block
    return False


def parse_markdown_plan(report: str) -> List[Dict[str, str]]:
    """Fallback for genuine day-by-day plans: weekday headings plus bullets.

    Deliberately returns nothing when the report has no weekday headings. This
    parser exists for the weekly-planning prompt's output shape; run loose over
    an arbitrary report it produces garbage, which is exactly what happened
    before this guard was added.
    """
    lines = str(report).splitlines()

    def _heading_day(line: str) -> Optional[str]:
        if not re.match(r"^\s*(#{1,6}\s+|\*\*)", line):
            return None
        heading = _strip_md(re.sub(r"^\s*#{1,6}\s*", "", line))
        if not heading.split():
            return None
        first = heading.split(",")[0].split()[0].lower()
        return first if first in _WEEKDAYS else None

    if not any(_heading_day(l) for l in lines):
        logger.info("commitment_markdown_fallback_skipped", reason="no weekday headings")
        return []

    items: List[Dict[str, str]] = []
    current_day = ""
    in_fence = False
    for raw in lines:
        line = raw.rstrip()
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence or not line.strip():
            continue
        if line.strip().startswith("|"):
            continue  # table row
        day = _heading_day(line)
        if day:
            current_day = day
            continue
        m = re.match(r"^\s*[-*]\s+(.*)", line)
        if not m:
            continue
        body = _strip_md(m.group(1))
        tod = ""
        lead = re.match(r"^([A-Za-z]+)\s*[:\-–]\s*(.+)$", body)
        if lead and lead.group(1).lower() in _TIME_OF_DAY:
            tod = lead.group(1).lower()
            body = lead.group(2).strip()
        if looks_like_scaffolding(body):
            continue
        items.append(
            {
                "title": body[:200],
                "detail": "",
                "day": current_day,
                "time_of_day": tod,
                "at_time": parse_clock(body) or "",
            }
        )
    return items


def _parse_json_array(text_value: str) -> List[Dict[str, Any]]:
    raw = str(text_value or "").strip()
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


def _tokens(text_value: str) -> set:
    return {
        w
        for w in re.split(r"[^a-z0-9]+", str(text_value or "").lower())
        if len(w) > 2 and w not in _STOPWORDS
    }


def restates_the_request(title: str, description: str) -> bool:
    """True when an "action item" is just the task itself, reworded.

    "Write a scannable market research digest for Lagos readers" is what the
    ASSISTANT was asked to do. Filing it as a user commitment produced 83 pinned
    reminders chasing the user to do the assistant's job.
    """
    t, d = _tokens(title), _tokens(description)
    if not t or not d:
        return False
    overlap = len(t & d) / len(t)
    return overlap >= 0.7


def clean_items(
    items: List[Dict[str, Any]], max_items: int, description: str = ""
) -> List[Dict[str, str]]:
    """Drop scaffolding and restatements, dedupe on title, cap the count."""
    out: List[Dict[str, str]] = []
    seen: set = set()
    for i in items:
        title = _strip_md(str(i.get("title", "") or ""))[:200].strip()
        if not title or looks_like_scaffolding(title):
            continue
        if description and restates_the_request(title, description):
            logger.info("commitment_dropped_restatement", title=title[:80])
            continue
        key = re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "title": title,
                "detail": str(i.get("detail", "") or "").strip()[:800],
                "day": str(i.get("day", "") or "").strip().lower(),
                "time_of_day": str(i.get("time_of_day", "") or "").strip().lower(),
                "at_time": str(i.get("at_time", "") or "").strip(),
            }
        )
        if len(out) >= max_items:
            break
    return out


async def extract_items(
    description: str,
    report: str,
    llm: Any = None,
    max_items: int = MAX_COMMITMENTS_PER_TASK,
) -> List[Dict[str, str]]:
    """Action items as {title, detail, day, time_of_day, at_time}. Never raises."""
    if not (report or "").strip() and not (description or "").strip():
        return []

    if llm is not None:
        try:
            from ..core.types import AgentRole

            result = await llm.generate(
                _EXTRACT_PROMPT.format(
                    description=str(description)[:1200],
                    report=str(report)[:8000],
                    max_items=max_items,
                ),
                AgentRole.PERSONAL_ASSISTANT,
            )
            cleaned = clean_items(
                _parse_json_array(result.get("response", "")), max_items, description
            )
            if cleaned:
                return cleaned
            logger.info("commitment_extract_llm_empty")
        except Exception as exc:
            logger.warning("commitment_extract_llm_failed", error=str(exc))

    fallback = clean_items(parse_markdown_plan(report), max_items, description)
    if fallback:
        return fallback

    # Last resort: the request itself was a plain single instruction and the
    # report gave us nothing usable. Better one right commitment than ten wrong.
    return single_item_from_request(description)


def single_item_from_request(description: str) -> List[Dict[str, str]]:
    """Treat a short imperative request as one commitment.

    "Remind me to pick Ibrahim up at Penthoush estate by 1:30 pm WAT"
    → "Pick Ibrahim up at Penthoush estate", due today 13:30 local.
    """
    text_value = str(description or "").strip()
    if not text_value or len(text_value) > 300:
        return []
    lowered = text_value.lower()
    if not re.match(r"^\s*(remind me( to)?|remember to|don'?t forget( to)?|todo:?)\b", lowered):
        return []

    title = re.sub(
        r"^\s*(remind me( to)?|remember to|don'?t forget( to)?|todo:?)\s*", "", text_value, flags=re.I
    )
    clock = parse_clock(title)
    # Strip the trailing time phrase so the title reads as a task, not a sentence.
    title = re.sub(
        r"\s*\b(by|at|before|around)\s+[0-9][^,]*?(am|pm|a\.m\.|p\.m\.|[0-9])\s*\w*\s*$",
        "",
        title,
        flags=re.I,
    ).strip(" .,")
    day = ""
    for token in ("today", "tomorrow", "tonight", *(_WEEKDAYS.keys())):
        if re.search(rf"\b{token}\b", lowered):
            day = token
            break
    if not day and clock:
        day = "today"
    if not title:
        return []
    return [{"title": title[:200], "detail": "", "day": day, "time_of_day": "", "at_time": clock or ""}]


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
            due = resolve_due(
                item.get("day", ""), item.get("time_of_day", ""), item.get("at_time", "")
            )
            row = await repo.create(
                title=item["title"],
                due_at=due,
                detail=item.get("detail") or None,
                source="task",
                task_id=task_id,
                # Proposed, not open: the assistant briefs you and waits. It
                # does not start chasing you about work you never agreed to.
                status=(
                    CommitmentStatus.PROPOSED.value
                    if settings.commitment_require_approval
                    else CommitmentStatus.OPEN.value
                ),
            )
            if row is not None:
                filed.append(repo.to_dict(row))
        except Exception as exc:
            logger.warning(
                "commitment_file_failed", title=item.get("title", "")[:60], error=str(exc)
            )
    if filed:
        logger.info(
            "commitments_filed", count=len(filed), task_id=str(task_id) if task_id else None
        )
    return filed
