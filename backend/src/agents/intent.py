"""What kind of thing is this, actually?

Every submission used to enter the same 11-step multi-agent pipeline. Asking it
to remind you to pick someone up produced a Task Complexity Assessment, a Team
Assembly table and Verifier Criteria — machinery worth minutes of model time and
useful to nobody, for something that is one row in a table.

So intent is decided first:

    REMINDER  "remind me to X at 5"      → file it, confirm, done. No pipeline.
    QUESTION  "what's my week look like?" → one model turn. No pipeline.
    SCHEDULE  "sync my schedule sheet"    → reconcile the sheet. No pipeline.
    WORK      everything else             → the full pipeline, as before.

Deterministic patterns decide the clear cases, which is most of them and costs
nothing. The model is asked only when the patterns are silent, and WORK is the
fallback — routing real research down the cheap path is the expensive mistake,
so ambiguity resolves toward doing the work.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

from ..core.logging import get_logger

logger = get_logger("agents.intent")


class Intent:
    REMINDER = "reminder"
    QUESTION = "question"
    SCHEDULE = "schedule"
    WORK = "work"


@dataclass
class IntentResult:
    kind: str
    reason: str
    by_llm: bool = False


# "remind me to…", "don't forget…", "ping me at 6" — an explicit ask to be chased.
_REMINDER_RE = re.compile(
    r"^\s*(?:hey\s+|please\s+|pls\s+)?"
    # The \b goes before the optional colon: "todo:" has no word boundary
    # after the colon, so `todo:\b` can never match.
    r"(remind me|reminder|remember to|don'?t (?:let me )?forget|ping me|nudge me|"
    r"wake me|alert me|set (?:a )?reminder|add (?:a )?reminder|todo)\b:?",
    re.I,
)

# A reminder wrapper wins even when its payload sounds like work:
# "remind me to research X at 5pm" is a reminder, not a research task.
_SCHEDULE_RE = re.compile(
    r"\b(sync|re-?sync|refresh|reload|pull|update)\b.{0,30}\b(schedule|routine|timetable|"
    r"calendar sheet|spreadsheet|google sheet)\b",
    re.I,
)

# Work verbs: things that need the pipeline.
_WORK_RE = re.compile(
    r"\b(research|analy[sz]e|audit|investigate|write|draft|compose|build|design|"
    r"implement|review|compare|summari[sz]e|digest|distill|plan|prepare|generate|"
    r"create|produce|scout|report on|deep dive)\b",
    re.I,
)

# Question shapes that a single turn can answer.
_QUESTION_RE = re.compile(
    r"^\s*(what|when|where|who|which|why|how|is|are|do|does|did|can|could|should|"
    r"will|would|am i|have i)\b.*\?*\s*$",
    re.I,
)

_CLASSIFY_PROMPT = """Classify this request into exactly one word.

reminder  — they want to be reminded/chased about doing something themselves
question  — a question you can answer in a few sentences from what you know
schedule  — they want their schedule spreadsheet re-read and synced
work      — anything needing real research, writing, analysis, or building

Request: {description}

Answer with one word only:"""

_VALID = {Intent.REMINDER, Intent.QUESTION, Intent.SCHEDULE, Intent.WORK}


def classify_fast(description: str) -> Optional[IntentResult]:
    """Pattern-only classification. None when it isn't clear-cut."""
    text = str(description or "").strip()
    if not text:
        return IntentResult(Intent.WORK, "empty description")

    if _REMINDER_RE.match(text):
        return IntentResult(Intent.REMINDER, "opens with an explicit reminder phrase")

    if _SCHEDULE_RE.search(text):
        return IntentResult(Intent.SCHEDULE, "asks to sync the schedule sheet")

    # Long, or carrying a work verb → the pipeline. Checked before the question
    # shape so "How should I research X?" doesn't take the cheap path.
    if _WORK_RE.search(text) or len(text) > 220:
        return IntentResult(Intent.WORK, "work verb or long brief")

    if text.endswith("?") and _QUESTION_RE.match(text) and len(text) <= 220:
        return IntentResult(Intent.QUESTION, "short direct question")

    return None


async def classify(description: str, llm: Any = None) -> IntentResult:
    """Never raises. Falls back to WORK, which is the safe direction."""
    fast = classify_fast(description)
    if fast is not None:
        logger.info("intent_classified", kind=fast.kind, reason=fast.reason, by_llm=False)
        return fast

    if llm is not None:
        try:
            from ..core.types import AgentRole

            result = await llm.generate(
                _CLASSIFY_PROMPT.format(description=str(description)[:600]),
                AgentRole.PERSONAL_ASSISTANT,
            )
            word = re.sub(r"[^a-z]", "", str(result.get("response", "")).strip().lower()[:20])
            for kind in _VALID:
                if word.startswith(kind):
                    logger.info("intent_classified", kind=kind, reason="model", by_llm=True)
                    return IntentResult(kind, "classified by the model", by_llm=True)
        except Exception as exc:
            logger.warning("intent_llm_failed", error=str(exc))

    logger.info("intent_classified", kind=Intent.WORK, reason="default", by_llm=False)
    return IntentResult(Intent.WORK, "no clear signal — defaulted to full pipeline")
