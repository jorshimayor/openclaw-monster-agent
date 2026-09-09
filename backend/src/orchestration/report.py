"""Composing the report the user actually reads.

The pipeline's final report used to be a debug dump — a header, an overall
confidence score, then each agent's raw output under "## Output from
ORCHESTRATOR (confidence 0.88)". For a planner agent that raw output is its
*plan*: Task Complexity Assessment, Team Assembly tables, Prompt Injection
Strategy, Verifier Criteria. So asking for a reminder returned seven sections of
machinery and no answer.

Diagnostics did not need to live in the report — the console renders every
agent's output with its confidence in its own panel, and the step events carry
the rest. So this module writes the answer and nothing else:

  1. `write_user_report()` asks the LLM for the user-facing answer, with a prompt
     that bans pipeline vocabulary outright.
  2. `strip_scaffolding_sections()` removes planner sections wherever they appear
     — belt and braces, since a weak model will happily echo its own scratch work.
  3. `compose_fallback_report()` produces something readable when there is no LLM,
     instead of the old dump.
"""

from __future__ import annotations

import re
from typing import Any, List, Optional, Tuple

from ..core.logging import get_logger

logger = get_logger("orchestration.report")

MIN_USABLE_REPORT_CHARS = 40

# Headings that mean "the pipeline talking about itself".
#
# Two tiers. STRONG phrases are distinctive enough to match anywhere in the
# heading, so "# 8. P6 Quality Gate Thresholds" and "## Rework Policy (retries)"
# are caught alongside a bare "Quality Gate". EXACT phrases are generic words
# that would produce false positives if matched loosely, so they must be
# essentially the whole heading.
_STRONG_HEADINGS = [
    r"task\s+complexity",
    r"complexity\s+(check|assessment)",
    r"pattern\s+match",
    r"experience\s+recall",
    r"team\s+assembly",
    r"prompt\s+injection",
    r"parallel\s+execution",
    r"execution\s+plan",
    r"verifier\s+criteria",
    r"verification\s+(criteria|plan)",
    r"quality\s+gate",
    r"rework\s+(policy|plan)",
    r"fix\s*(&|and)?\s*revalidat\w*",
    r"post[\s-]*task\s+reflection",
    r"final\s+synthesi[sz]ed\s+report",
    r"synthesis\s+(notes?|plan|target)",
    r"knowledge\s+capture",
    r"reflection\s*/\s*knowledge",
    r"output\s+from\s+\w+",
    r"confidence\s+ratings?",
    r"agent\s+(team|roster|outputs?)",
]
_EXACT_HEADINGS = [
    r"verifier",
    r"verification",
    r"wave\s*\d*",
    r"step\s*\d+\b.*",
]

_STRONG_RE = re.compile(r"(?:" + "|".join(_STRONG_HEADINGS) + r")", re.I)
_EXACT_RE = re.compile(
    r"^\s*(?:[a-z]?\d+[.):]?\s*)*(?:"
    + "|".join(_EXACT_HEADINGS)
    + r")\s*(?:[(\[{][^\n]*)?\s*[:.]?\s*$",
    re.I,
)


def _is_scaffolding_heading(text: str) -> bool:
    return bool(_STRONG_RE.search(text) or _EXACT_RE.match(text))


# Whole lines that are pipeline bookkeeping even outside a scaffolding section.
_NOISE_LINE_RE = re.compile(
    r"^\s*[-*]?\s*\**\s*(overall\s+confidence|confidence|approved\s+outputs?|"
    r"quality\s+rating|estimated\s+effort|scope|dependencies|risk|pattern|"
    r"justification|owner|model|latency|tokens?)\**\s*[:：]",
    re.I,
)

# Prose that names the machinery by its actors — "ORCHESTRATOR will dispatch the
# CalendarAgent", "VerificationAgent will confirm the event". Heading-level
# stripping can't reach these because they live in ordinary body text.
_ACTOR_LINE_RE = re.compile(
    r"\b([A-Z][a-zA-Z]*Agent|ORCHESTRATOR|CONTENT_WEB[23]|SECURITY|KNOWLEDGE|"
    r"EDITOR|STUDY|FOOTBALL|PERSONAL_ASSISTANT)\b"
)

_HEADING_RE = re.compile(r"^\s*(#{1,6})\s+(.*)$")


def _heading_text(raw: str) -> str:
    return re.sub(r"\*\*|`|__", "", raw).strip().strip(":.")


def strip_scaffolding_sections(markdown: str) -> str:
    """Drop planner sections and bookkeeping lines, keep everything else.

    A dropped heading takes its whole section with it — everything up to the
    next heading at the same or a shallower level.
    """
    lines = str(markdown or "").splitlines()
    out: List[str] = []
    skip_until_level: Optional[int] = None
    in_fence = False

    for line in lines:
        if line.strip().startswith("```"):
            in_fence = not in_fence
            if skip_until_level is None:
                out.append(line)
            continue
        if in_fence:
            if skip_until_level is None:
                out.append(line)
            continue

        heading = _HEADING_RE.match(line)
        if heading:
            level = len(heading.group(1))
            text = _heading_text(heading.group(2))
            if skip_until_level is not None and level > skip_until_level:
                continue  # still inside the dropped section
            skip_until_level = None
            if _is_scaffolding_heading(text):
                skip_until_level = level
                continue
            out.append(line)
            continue

        if skip_until_level is not None:
            continue
        if _NOISE_LINE_RE.match(line) or _ACTOR_LINE_RE.search(line):
            continue
        out.append(line)

    return _prune_empty_sections("\n".join(out))


def _prune_empty_sections(markdown: str) -> str:
    """Drop headings whose body was entirely stripped away.

    Without this, removing a section's content leaves a bare "## Summary"
    hanging over nothing.
    """
    lines = markdown.splitlines()
    keep = [True] * len(lines)
    for i, line in enumerate(lines):
        heading = _HEADING_RE.match(line)
        if not heading:
            continue
        level = len(heading.group(1))
        has_body = False
        for j in range(i + 1, len(lines)):
            nxt = _HEADING_RE.match(lines[j])
            if nxt and len(nxt.group(1)) <= level:
                break
            if lines[j].strip():
                has_body = True
                break
        if not has_body:
            keep[i] = False
    cleaned = "\n".join(l for l, k in zip(lines, keep) if k)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    # A separator with nothing left on either side is just a stray rule.
    cleaned = re.sub(r"^\s*-{3,}\s*$\n?", "", cleaned, flags=re.M)
    return cleaned.strip()


_SYNTHESIS_PROMPT = """Write the reply the user reads. You are their assistant reporting back.

THEIR REQUEST:
{description}

WHAT THE WORK PRODUCED (internal — never quote or describe this machinery):
{material}

HOW TO WRITE IT:
- Open with the answer or the result. No preamble, no restating the request.
- Write to the person who asked. Plain, direct, warm enough to read as a human wrote it.
- Length follows the request. A reminder or a small action gets two or three lines.
  A research or writing request gets the full piece.
- Markdown only where it earns its place: `##` headings when there are genuinely
  several sections, bullets for real lists. A short answer needs neither.
- If an action was set up, say what will happen and when, in the user's own terms
  (their local time, their words for the thing).
- Use only what is in the material above. Never invent a fact, a number, or a link.

NEVER MENTION: agents, waves, steps, pipelines, orchestration, synthesis,
confidence scores, quality gates, verifiers, prompts, models, tools, or how the
work was organised. No "Task Complexity Assessment", no "Team Assembly", no
"Output from X". The user does not know or care that any of that exists.

Write only the reply itself:"""


def _output_texts(approved_outputs: List[Any]) -> List[str]:
    texts: List[str] = []
    for out in approved_outputs:
        text = getattr(out, "output", "") or ""
        if not isinstance(text, str):
            text = str(text)
        if text.strip():
            texts.append(text.strip())
    return texts


def _material_from_outputs(approved_outputs: List[Any]) -> str:
    """Raw material for the synthesis prompt.

    Scaffolding is stripped first so the model isn't tempted to reproduce it.
    But when an output is scaffolding *all the way down* — which is what happens
    when the only agent that ran was the planner — stripping leaves nothing, and
    an empty prompt would waste the one chance to salvage an answer. In that case
    hand over the raw text and rely on the prompt's ban to keep the machinery out
    of the reply.
    """
    texts = _output_texts(approved_outputs)
    stripped = [t for t in (strip_scaffolding_sections(t) for t in texts) if t.strip()]
    chunks = stripped or texts
    return "\n\n---\n\n".join(chunks)[:9000]


# Below this share of the original surviving the strip, what's left is almost
# certainly scraps of a plan rather than an answer.
_SUBSTANCE_RATIO = 0.35


def compose_fallback_report(task_description: str, approved_outputs: List[Any]) -> str:
    """Readable report for when no LLM is available.

    Presents the work instead of dumping it: no confidence headers, no
    "Output from ORCHESTRATOR", no machinery.

    There is a limit to what sanitising can do. When an agent's whole output was
    a plan, stripping the machinery leaves scraps of a plan — and no regex will
    turn that into an answer. So if most of the text disappeared, say so plainly
    rather than presenting the remnants as a report. Honest beats tidy; the LLM
    path is what produces a real answer, and this only runs when it is down.
    """
    texts = _output_texts(approved_outputs)
    original_chars = sum(len(t) for t in texts)
    cleaned = [t for t in (strip_scaffolding_sections(x) for x in texts) if t.strip()]
    kept_chars = sum(len(t) for t in cleaned)

    mostly_machinery = (
        original_chars > 0 and (kept_chars / original_chars) < _SUBSTANCE_RATIO
    )

    if not cleaned or mostly_machinery:
        logger.info(
            "synthesis_fallback_no_substance",
            original_chars=original_chars,
            kept_chars=kept_chars,
        )
        return (
            f"I worked on: {task_description or 'your request'}\n\n"
            "I couldn't put together a clean summary this time — what came back "
            "was mostly working notes rather than an answer. The full detail is "
            "on the task page."
        )
    if len(cleaned) == 1:
        return cleaned[0]
    return "\n\n".join(cleaned)


async def write_user_report(
    task_description: str,
    approved_outputs: List[Any],
    llm: Any = None,
) -> Tuple[str, bool]:
    """(report, written_by_llm). Never raises — always returns something."""
    material = _material_from_outputs(approved_outputs)

    if llm is not None and material.strip():
        try:
            from ..core.types import AgentRole

            result = await llm.generate(
                _SYNTHESIS_PROMPT.format(
                    description=str(task_description or "(not provided)")[:1500],
                    material=material,
                ),
                AgentRole.PERSONAL_ASSISTANT,
            )
            report = strip_scaffolding_sections(str(result.get("response", "")).strip())
            # A model that returns a stub or refuses shouldn't blank the report.
            if len(report) >= MIN_USABLE_REPORT_CHARS:
                return report, True
            logger.info("synthesis_llm_too_short", chars=len(report))
        except Exception as exc:
            logger.warning("synthesis_llm_failed", error=str(exc))

    return compose_fallback_report(task_description, approved_outputs), False
