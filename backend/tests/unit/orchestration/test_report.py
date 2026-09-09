"""The final report must read like an answer, not like a pipeline transcript.

Regression cover for the report that reached the user as seven sections of
machinery — Task Complexity Assessment, Team Assembly, Prompt Injection
Strategy, Verifier Criteria — and no actual answer.
"""

from __future__ import annotations

import pytest

from src.core.types import AgentResult, AgentRole
from src.orchestration.report import (
    compose_fallback_report,
    strip_scaffolding_sections,
    write_user_report,
)

PLANNER_OUTPUT = """# 1. Task Complexity Assessment
- **Scope**: 1 x reminder (pick-up at a specific location and time).
- **Estimated effort**: < 5 min (human + agent).

# 2. Pattern Match
- **Pattern**: `WorkflowPattern.GENERIC` - a single-step, low-risk automation.

# 3. Experience Recall (Hypothetical)
| # | Past Task | Lesson Learned |
|---|-----------|----------------|
| 1 | "Schedule a meeting" | Confirm the time zone. |

# 4. Team Assembly (waves of agents + tools)

| Wave | Agent | Tool |
|------|-------|------|
| 1 | **CalendarAgent** | `create_event()` |

# 5. Prompt Injection Strategy
- **CalendarAgent Prompt**

# 7. Verifier Criteria
- Event title matches `"Pick up Ibrahim"`.
"""

REAL_ANSWER = """## What I found

The naira held steady against the dollar this week.

- CBN held rates at the last MPC meeting
- Equities were broadly flat
"""


class FakeLLM:
    def __init__(self, response: str):
        self.response = response
        self.calls = []

    async def generate(self, prompt, agent_role, **kwargs):
        self.calls.append(prompt)
        return {"response": self.response}


class BrokenLLM:
    async def generate(self, *a, **k):
        raise RuntimeError("provider down")


@pytest.mark.parametrize(
    "heading",
    [
        "# 1. Task Complexity Assessment",
        "# Pattern Match",
        "## Team Assembly (waves of agents + tools)",
        "# 5. Prompt Injection Strategy",
        "# 7. Verifier Criteria",
        "## Output from ORCHESTRATOR (confidence 0.88)",
        "### Quality Gate",
        "## Post-Task Reflection",
        "# 8. P6 Quality Gate Thresholds",
        "## Rework Policy",
        "# Final Synthesized Report",
    ],
)
def test_scaffolding_headings_are_stripped(heading: str) -> None:
    # The real section is a SIBLING of the scaffolding one. A heading nested
    # under a dropped section is genuinely part of it and goes with it — that
    # is covered by test_nested_subsections_go_with_their_parent.
    level = heading.split(" ", 1)[0]
    md = f"{heading}\nsome machinery here\n\n{level} Real Section\nthe actual answer\n"
    out = strip_scaffolding_sections(md)
    assert "some machinery here" not in out
    assert "the actual answer" in out
    assert "Real Section" in out


def test_stripping_removes_a_whole_section_not_just_its_heading() -> None:
    out = strip_scaffolding_sections(PLANNER_OUTPUT)
    for leaked in ("CalendarAgent", "WorkflowPattern", "Estimated effort", "Wave", "Verifier"):
        assert leaked not in out, f"{leaked!r} survived"


def test_nested_subsections_go_with_their_parent() -> None:
    md = """# Team Assembly
## Wave 1
machinery
### details
more machinery

# Findings
the answer
"""
    out = strip_scaffolding_sections(md)
    assert "machinery" not in out
    assert "the answer" in out


def test_real_content_is_left_alone() -> None:
    assert strip_scaffolding_sections(REAL_ANSWER).strip() == REAL_ANSWER.strip()


@pytest.mark.parametrize(
    "heading",
    [
        "## What I found",
        "## Summary",
        "## Reflections on the naira",
        "## Weekly Plan",
        "**Monday, August 24**",
        "## Key risks for the quarter",
        "## Verification steps you should run",
    ],
)
def test_legitimate_headings_are_not_mistaken_for_machinery(heading: str) -> None:
    """The loose matcher must not eat real prose. "Reflections on the naira"
    and "Key risks" read like scaffolding to a careless regex."""
    md = f"{heading}\nreal content the user wants\n"
    assert "real content the user wants" in strip_scaffolding_sections(md)


def test_bookkeeping_lines_are_dropped_outside_sections() -> None:
    md = "The naira held steady.\n\n**Overall confidence**: 0.88\n- **Risk**: minimal\n\nMore answer.\n"
    out = strip_scaffolding_sections(md)
    assert "confidence" not in out.lower()
    assert "Risk" not in out
    assert "The naira held steady." in out
    assert "More answer." in out


def test_code_fences_are_preserved_verbatim() -> None:
    md = "Here is the snippet:\n\n```python\n# Task Complexity Assessment\nx = 1\n```\n"
    out = strip_scaffolding_sections(md)
    assert "x = 1" in out
    assert "```python" in out


@pytest.mark.asyncio
async def test_llm_writes_the_report_and_never_sees_a_scaffolding_ban_violation() -> None:
    llm = FakeLLM("Reminder set. I'll nudge you at 1:30 pm to pick Ibrahim up at Penthoush Estate.")
    outputs = [AgentResult(agent_role=AgentRole.ORCHESTRATOR, output=PLANNER_OUTPUT, confidence=0.88)]
    report, by_llm = await write_user_report("Remind me to pick Ibrahim up", outputs, llm=llm)

    assert by_llm is True
    assert "Ibrahim" in report
    assert "Team Assembly" not in report
    # When every output is scaffolding, the raw text is still handed over so the
    # model can salvage the answer from it — the ban in the prompt is what keeps
    # the machinery out of the reply.
    assert "NEVER MENTION" in llm.calls[0]


@pytest.mark.asyncio
async def test_fallback_is_used_when_the_llm_fails() -> None:
    outputs = [AgentResult(agent_role=AgentRole.CONTENT_WEB2, output=REAL_ANSWER, confidence=0.9)]
    report, by_llm = await write_user_report("Weekly digest", outputs, llm=BrokenLLM())
    assert by_llm is False
    assert "The naira held steady" in report


@pytest.mark.asyncio
async def test_a_too_short_llm_reply_falls_back_rather_than_blanking() -> None:
    outputs = [AgentResult(agent_role=AgentRole.CONTENT_WEB2, output=REAL_ANSWER, confidence=0.9)]
    report, by_llm = await write_user_report("Weekly digest", outputs, llm=FakeLLM("ok"))
    assert by_llm is False
    assert "The naira held steady" in report


@pytest.mark.asyncio
async def test_planner_only_output_does_not_produce_a_machinery_report() -> None:
    """The exact incident: the only approved output was the orchestrator's plan."""
    outputs = [AgentResult(agent_role=AgentRole.ORCHESTRATOR, output=PLANNER_OUTPUT, confidence=0.88)]
    report, _ = await write_user_report("Remind me to pick Ibrahim up", outputs, llm=None)
    for machinery in ("Task Complexity", "Team Assembly", "CalendarAgent", "Verifier", "Wave"):
        assert machinery not in report


def test_fallback_report_has_no_debug_headers() -> None:
    outputs = [
        AgentResult(agent_role=AgentRole.CONTENT_WEB2, output="First finding.", confidence=0.8),
        AgentResult(agent_role=AgentRole.CONTENT_WEB3, output="Second finding.", confidence=0.9),
    ]
    report = compose_fallback_report("Research request", outputs)
    assert "First finding." in report and "Second finding." in report
    for machinery in ("Output from", "confidence", "CONTENT_WEB2", "Final Synthesized Report"):
        assert machinery not in report


def test_mostly_machinery_says_so_instead_of_presenting_scraps() -> None:
    """No regex turns a plan into an answer. When almost everything is stripped,
    the fallback must admit it rather than dress up the remnants."""
    outputs = [AgentResult(agent_role=AgentRole.ORCHESTRATOR, output=PLANNER_OUTPUT, confidence=0.88)]
    report = compose_fallback_report("Remind me to pick Ibrahim up", outputs)
    assert "couldn't put together a clean summary" in report
    assert "Remind me to pick Ibrahim up" in report
    for machinery in ("Team Assembly", "CalendarAgent", "Verifier", "Wave"):
        assert machinery not in report


def test_genuine_content_is_still_presented_in_full() -> None:
    """The substance guard must not swallow a real answer that happens to
    contain one scaffolding-ish line."""
    body = REAL_ANSWER + "\n\nMore detail follows, at length, so the surviving " * 6
    outputs = [AgentResult(agent_role=AgentRole.CONTENT_WEB2, output=body, confidence=0.9)]
    report = compose_fallback_report("Weekly digest", outputs)
    assert "The naira held steady" in report
    assert "couldn't put together" not in report


def test_empty_outputs_produce_an_honest_message_not_an_empty_report() -> None:
    report = compose_fallback_report("Research request", [])
    assert "Research request" in report
    assert len(report) > 40
