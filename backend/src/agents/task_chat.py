"""The conversation attached to a task.

A finished task used to be a wall of text and a set of reminders that started
whether you wanted them or not. Now it is a thread: the assistant briefs you on
what it proposes to chase, and you answer in plain language — approve, push
back, ask a question, or hand over an artifact.

Intent is resolved before the LLM is involved, and acted on directly, because
an assistant that *says* "approved!" without changing any state is worse than
one that says nothing. The model writes the reply; this module performs the
work and tells the model what it actually did.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from ..core import commitment_repo as repo
from ..core.artifact import classify
from ..core.config import get_settings
from ..core.logging import get_logger
from ..models.commitment import CommitmentStatus
from .commitment_extractor import parse_clock, resolve_due

logger = get_logger("agents.task_chat")

MAX_HISTORY_TURNS = 12

_APPROVE_ALL_RE = re.compile(
    r"\b(approve|accept|confirm|yes|ok|okay|go ahead|do it|sounds good|lgtm)\b.{0,20}\b(all|everything|them|it)?\b",
    re.I,
)
_APPROVE_WORD_RE = re.compile(
    r"^\s*(approve|approved|accept|confirm|yes|yep|yeah|ok|okay|go ahead|do it|sounds good|lgtm)\b",
    re.I,
)
_REJECT_RE = re.compile(r"\b(reject|decline|drop|cancel|remove|delete|no thanks|not now)\b", re.I)
_SHORT_ID_RE = re.compile(r"\b([0-9a-f]{8})\b", re.I)
_RESCHEDULE_RE = re.compile(
    r"\b(move|reschedule|push|shift|change)\b.{0,40}?\b(to|until|till)\b\s*(?P<when>.{3,40})", re.I
)

_DAY_WORDS = (
    "today", "tomorrow", "tonight", "monday", "tuesday", "wednesday",
    "thursday", "friday", "saturday", "sunday",
)
_TOD_WORDS = ("morning", "afternoon", "evening", "night", "noon")


_CHAT_PROMPT = """You are this person's assistant, talking to them about one task you ran for them.

WHAT THEY ASKED FOR:
{description}

WHAT YOU PRODUCED:
{report}

WHAT IS CURRENTLY ON THEIR HOOK FROM THIS TASK:
{commitments}

{action_note}CONVERSATION SO FAR:
{history}

THEIR MESSAGE:
{message}

Reply as their assistant. Rules:
- Short. Two or three sentences unless they asked for something long.
- If you performed an action, say plainly what changed. Do not claim anything the
  note above does not say you did.
- If they asked a question, answer it from the material above. If the answer is
  not there, say so — never invent a fact, a figure, or a link.
- Never mention agents, pipelines, steps, confidence scores, or how the work was
  organised. They do not know or care that any of that exists.
- Plain language. No headings unless you are genuinely listing several things.

Your reply:"""


def _short(c: Any) -> str:
    return str(c.id)[:8]


def _fmt_commitments(rows: List[Any]) -> str:
    if not rows:
        return "(nothing)"
    out = []
    for c in rows:
        due = c.due_at.isoformat(timespec="minutes") if c.due_at else "no due time"
        out.append(f"- [{_short(c)}] {c.title} — {c.status}, due {due}")
    return "\n".join(out)


def _extract_when(text: str) -> Dict[str, str]:
    lowered = text.lower()
    day = next((d for d in _DAY_WORDS if re.search(rf"\b{d}\b", lowered)), "")
    tod = next((t for t in _TOD_WORDS if re.search(rf"\b{t}\b", lowered)), "")
    return {"day": day, "time_of_day": tod, "at_time": parse_clock(text) or ""}


async def _task_commitments(task_id: UUID) -> List[Any]:
    return [c for c in await repo.list_all(limit=500) if c.task_id == task_id]


async def apply_intent(task_id: UUID, message: str) -> Dict[str, Any]:
    """Do what the message asks, before any text is generated.

    Returns {actions: [...], note: str}. `note` is fed to the model so its reply
    can only describe changes that actually happened.
    """
    actions: List[Dict[str, Any]] = []
    rows = await _task_commitments(task_id)
    by_short = {_short(c): c for c in rows}
    proposed = [c for c in rows if c.status == CommitmentStatus.PROPOSED.value]
    open_rows = [c for c in rows if c.status == CommitmentStatus.OPEN.value]

    targets = [by_short[m.lower()] for m in _SHORT_ID_RE.findall(message) if m.lower() in by_short]

    # 1. An artifact closes something, whatever else the message says.
    verdict = classify(text=message)
    if verdict["accepted"]:
        candidates = targets or open_rows
        if len(candidates) == 1:
            c = candidates[0]
            updated = await repo.complete(
                c.id,
                artifact_kind=verdict["kind"],
                artifact_url=verdict["url"],
                artifact_text=verdict["text"],
            )
            if updated is not None:
                actions.append({"type": "closed", "id": str(c.id), "title": c.title})
        elif len(candidates) > 1:
            actions.append(
                {"type": "ambiguous_artifact", "candidates": [_short(c) for c in candidates]}
            )

    # 2. Reschedule.
    resched = _RESCHEDULE_RE.search(message)
    if resched:
        when = _extract_when(resched.group("when"))
        if any(when.values()):
            due = resolve_due(when["day"], when["time_of_day"], when["at_time"])
            for c in targets or proposed or open_rows:
                await repo.reschedule(c.id, due)
                actions.append(
                    {"type": "rescheduled", "id": str(c.id), "title": c.title, "due": due.isoformat()}
                )
                if not targets:
                    break

    # 3. Reject / drop.
    if _REJECT_RE.search(message) and not verdict["accepted"]:
        for c in targets or proposed:
            await repo.drop(c.id)
            actions.append({"type": "dropped", "id": str(c.id), "title": c.title})
        if not targets and not proposed:
            actions.append({"type": "nothing_to_reject"})

    # 4. Approve — only when nothing above already handled the message.
    approving = bool(_APPROVE_WORD_RE.match(message.strip())) or bool(
        _APPROVE_ALL_RE.search(message) and not _REJECT_RE.search(message)
    )
    if approving and not verdict["accepted"] and proposed:
        for c in targets or proposed:
            updated = await repo.approve(c.id)
            if updated is not None:
                actions.append({"type": "approved", "id": str(c.id), "title": c.title})

    return {"actions": actions, "note": _action_note(actions)}


def _action_note(actions: List[Dict[str, Any]]) -> str:
    if not actions:
        return ""
    lines = ["WHAT YOU JUST DID (describe only these, accurately):"]
    for a in actions:
        t = a["type"]
        if t == "approved":
            lines.append(f"- Approved \"{a['title']}\" — reminders for it start now.")
        elif t == "dropped":
            lines.append(f"- Dropped \"{a['title']}\" — it will not be chased.")
        elif t == "closed":
            lines.append(f"- Closed \"{a['title']}\" — artifact recorded, reminders stopped.")
        elif t == "rescheduled":
            lines.append(f"- Moved \"{a['title']}\" to {a['due']}.")
        elif t == "ambiguous_artifact":
            lines.append(
                "- They sent an artifact but several things are open, so you closed "
                f"NOTHING. Ask which one: {', '.join(a['candidates'])}."
            )
        elif t == "nothing_to_reject":
            lines.append("- There was nothing waiting for approval, so you changed nothing.")
    return "\n".join(lines) + "\n\n"


def compose_brief(task_description: str, proposed: List[Any]) -> str:
    """The opening message: here is what I propose to chase you about."""
    if not proposed:
        return (
            "That's done. Nothing from it needs chasing, so I haven't put anything "
            "on your hook. Ask me anything about it here."
        )
    lines = [
        f"I've pulled {len(proposed)} thing{'s' if len(proposed) != 1 else ''} out of this "
        "that you'd need to do. Nothing starts chasing you until you say go.",
        "",
    ]
    for c in proposed:
        due = c.due_at.strftime("%a %d %b, %H:%M UTC") if c.due_at else "no due time"
        lines.append(f"• {c.title}  —  {due}")
    lines += [
        "",
        'Reply "approve" to start the reminders, tell me to move something '
        '("push the README to Friday evening"), or say what to drop.',
    ]
    return "\n".join(lines)


async def reply(
    task_id: UUID,
    message: str,
    task_description: str,
    report: str,
    history: List[Dict[str, Any]],
    llm: Any = None,
) -> Dict[str, Any]:
    """Act on the message, then write the reply. Never raises."""
    try:
        outcome = await apply_intent(task_id, message)
    except Exception as exc:
        logger.warning("task_chat_intent_failed", task_id=str(task_id), error=str(exc))
        outcome = {"actions": [], "note": ""}

    rows = await _task_commitments(task_id)
    history_text = "\n".join(
        f"{h.get('role', 'user')}: {str(h.get('content', ''))[:400]}"
        for h in history[-MAX_HISTORY_TURNS:]
    ) or "(this is the first message)"

    text = ""
    if llm is not None:
        try:
            from ..core.types import AgentRole

            result = await llm.generate(
                _CHAT_PROMPT.format(
                    description=str(task_description)[:800],
                    report=str(report)[:4000] or "(no report)",
                    commitments=_fmt_commitments(rows),
                    action_note=outcome["note"],
                    history=history_text,
                    message=str(message)[:2000],
                ),
                AgentRole.PERSONAL_ASSISTANT,
            )
            text = str(result.get("response", "")).strip()
        except Exception as exc:
            logger.warning("task_chat_llm_failed", task_id=str(task_id), error=str(exc))

    if not text:
        # Never leave the user without an answer just because the model is down —
        # the actions already happened and they need to know.
        text = _deterministic_reply(outcome["actions"], rows)

    return {"reply": text, "actions": outcome["actions"], "commitments": [repo.to_dict(c) for c in rows]}


def _deterministic_reply(actions: List[Dict[str, Any]], rows: List[Any]) -> str:
    if actions:
        return _action_note(actions).replace(
            "WHAT YOU JUST DID (describe only these, accurately):\n", ""
        ).strip()
    proposed = [c for c in rows if c.status == CommitmentStatus.PROPOSED.value]
    if proposed:
        return (
            f"{len(proposed)} thing(s) are still waiting on your go-ahead. "
            'Reply "approve" to start the reminders.'
        )
    return "Noted. (I couldn't reach the model for a fuller answer just now.)"
