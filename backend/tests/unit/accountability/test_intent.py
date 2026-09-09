"""Routing: a reminder must not run an eleven-step research pipeline.

"Remind me to pick Ibrahim up at 1:30pm" went through complexity assessment,
team assembly, prompt-injection strategy and verifier criteria — minutes of
model time to produce one row in a table, and a report full of machinery.
"""

from __future__ import annotations

import pytest

from src.agents.intent import Intent, classify, classify_fast


@pytest.mark.parametrize(
    "text",
    [
        "Remind me to pick Ibrahim up at Penthoush estate by 1:30 pm WAT",
        "remind me to call the bank tomorrow",
        "Don't forget to renew the domain",
        "dont forget the gym bag",
        "ping me at 6pm about the standup",
        "nudge me about the README on Friday",
        "Set a reminder for the MPC announcement",
        "todo: pay the electricity bill",
    ],
)
def test_reminders_are_recognised(text: str) -> None:
    assert classify_fast(text).kind == Intent.REMINDER


@pytest.mark.parametrize(
    "text",
    [
        "Research the stats I should post about Chelsea match vs Fulham tomorrow",
        "Write a scannable market research digest for a reader in Lagos",
        "Audit this Solidity contract for reentrancy",
        "Can you distill this routine from my excel sheet into a weekly schedule?",
        "Compare Kafka and SQS for our ingestion pipeline",
        "Draft a LinkedIn post about the fieldtilt launch",
    ],
)
def test_real_work_still_goes_to_the_pipeline(text: str) -> None:
    assert classify_fast(text).kind == Intent.WORK


def test_a_reminder_wrapping_a_work_verb_is_still_a_reminder() -> None:
    """"Remind me to research X" is a reminder about research, not research."""
    assert classify_fast("Remind me to research zk rollups at 5pm").kind == Intent.REMINDER


def test_a_question_about_research_is_not_a_reminder_or_a_question() -> None:
    """"How should I research X?" asks for actual work — the work verb wins
    over the question shape, because the cheap path would answer it badly."""
    assert classify_fast("How should I research zk proofs?").kind == Intent.WORK


@pytest.mark.parametrize(
    "text",
    ["What is on my plate today?", "when is the README due?", "am i behind on anything?"],
)
def test_short_direct_questions_take_the_cheap_path(text: str) -> None:
    assert classify_fast(text).kind == Intent.QUESTION


@pytest.mark.parametrize(
    "text",
    ["sync my schedule sheet", "refresh my routine spreadsheet", "re-sync the timetable"],
)
def test_schedule_sync_is_recognised(text: str) -> None:
    assert classify_fast(text).kind == Intent.SCHEDULE


def test_a_long_brief_is_work_even_without_a_work_verb() -> None:
    assert classify_fast("x " * 200).kind == Intent.WORK


def test_ambiguous_input_defers_to_the_model() -> None:
    assert classify_fast("ping") is None


class FakeLLM:
    def __init__(self, word): self.word = word
    async def generate(self, *a, **k): return {"response": self.word}


class DeadLLM:
    async def generate(self, *a, **k): raise RuntimeError("down")


@pytest.mark.asyncio
async def test_the_model_resolves_what_patterns_cannot() -> None:
    result = await classify("ping", llm=FakeLLM("question"))
    assert result.kind == Intent.QUESTION
    assert result.by_llm is True


@pytest.mark.asyncio
async def test_ambiguity_defaults_to_work_not_to_the_cheap_path() -> None:
    """Routing real research down the reminder path is the expensive mistake."""
    assert (await classify("ping", llm=DeadLLM())).kind == Intent.WORK
    assert (await classify("ping", llm=None)).kind == Intent.WORK
    assert (await classify("ping", llm=FakeLLM("banana"))).kind == Intent.WORK


@pytest.mark.asyncio
async def test_clear_cases_never_reach_the_model() -> None:
    class Exploding:
        async def generate(self, *a, **k):
            raise AssertionError("the model should not have been called")

    assert (await classify("remind me to stretch", llm=Exploding())).kind == Intent.REMINDER
