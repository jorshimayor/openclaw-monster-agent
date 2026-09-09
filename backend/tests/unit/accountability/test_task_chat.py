"""The task thread: brief, approve, discuss, close.

The rule under test throughout: the assistant must never *say* it did something
it did not do. Intent is applied first and the reply is constrained to the
actions that actually happened.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from src.agents.task_chat import apply_intent, compose_brief, reply
from src.core import commitment_repo as repo
from src.models.commitment import CommitmentStatus

TASK = uuid4()


@pytest.fixture(autouse=True)
def _clean():
    repo._MEM.clear()
    yield
    repo._MEM.clear()


async def _propose(title="Rewrite the chelsea_bot README", hours=3):
    return await repo.create(
        title=title,
        due_at=datetime.now(timezone.utc) + timedelta(hours=hours),
        task_id=TASK,
        status=CommitmentStatus.PROPOSED.value,
    )


@pytest.mark.asyncio
async def test_brief_says_nothing_is_chasing_you_yet() -> None:
    rows = [await _propose(), await _propose("Publish the X post")]
    brief = compose_brief("Prep my week", rows)
    assert "Nothing starts chasing you until you say go" in brief
    assert "Rewrite the chelsea_bot README" in brief
    assert "Publish the X post" in brief


@pytest.mark.asyncio
async def test_brief_for_a_task_with_no_actions_does_not_invent_any() -> None:
    brief = compose_brief("ping", [])
    assert "haven't put anything on your hook" in brief


@pytest.mark.asyncio
async def test_approve_flips_proposed_to_open() -> None:
    row = await _propose()
    out = await apply_intent(TASK, "approve")
    assert [a["type"] for a in out["actions"]] == ["approved"]
    assert (await repo.get(row.id)).status == CommitmentStatus.OPEN.value


@pytest.mark.asyncio
async def test_approving_one_by_id_leaves_the_others_proposed() -> None:
    a = await _propose("First thing")
    b = await _propose("Second thing")
    await apply_intent(TASK, f"approve {str(a.id)[:8]}")
    assert (await repo.get(a.id)).status == CommitmentStatus.OPEN.value
    assert (await repo.get(b.id)).status == CommitmentStatus.PROPOSED.value


@pytest.mark.asyncio
async def test_reject_drops_instead_of_approving() -> None:
    row = await _propose()
    out = await apply_intent(TASK, "drop that, not doing it")
    assert [a["type"] for a in out["actions"]] == ["dropped"]
    assert (await repo.get(row.id)).status == CommitmentStatus.DROPPED.value


@pytest.mark.asyncio
async def test_reschedule_moves_the_due_time() -> None:
    row = await _propose()
    before = (await repo.get(row.id)).due_at
    out = await apply_intent(TASK, "push the README to friday evening")
    assert [a["type"] for a in out["actions"]] == ["rescheduled"]
    assert (await repo.get(row.id)).due_at != before


@pytest.mark.asyncio
async def test_an_artifact_closes_the_single_open_item() -> None:
    row = await _propose()
    await repo.approve(row.id)
    out = await apply_intent(TASK, "done: https://github.com/me/chelsea_bot")
    assert [a["type"] for a in out["actions"]] == ["closed"]
    closed = await repo.get(row.id)
    assert closed.status == CommitmentStatus.DONE.value
    assert closed.artifact_url == "https://github.com/me/chelsea_bot"


@pytest.mark.asyncio
async def test_an_ambiguous_artifact_closes_nothing_and_asks() -> None:
    a = await _propose("First thing")
    b = await _propose("Second thing")
    await repo.approve(a.id)
    await repo.approve(b.id)
    out = await apply_intent(TASK, "here it is https://example.com/x")
    assert [x["type"] for x in out["actions"]] == ["ambiguous_artifact"]
    for row in (a, b):
        assert (await repo.get(row.id)).status == CommitmentStatus.OPEN.value


@pytest.mark.asyncio
async def test_a_bare_question_changes_nothing() -> None:
    row = await _propose()
    out = await apply_intent(TASK, "why did you schedule that one for the evening?")
    assert out["actions"] == []
    assert (await repo.get(row.id)).status == CommitmentStatus.PROPOSED.value


@pytest.mark.asyncio
async def test_the_model_is_told_only_what_actually_happened() -> None:
    """The guard against a confident lie: the note handed to the model lists
    real actions, and an empty action list produces no note at all."""
    await _propose()
    approved = await apply_intent(TASK, "approve")
    assert "Approved" in approved["note"]

    question = await apply_intent(TASK, "what time is that again?")
    assert question["note"] == ""


class FakeLLM:
    def __init__(self, text): self.text, self.prompts = text, []
    async def generate(self, prompt, role, **kw):
        self.prompts.append(prompt)
        return {"response": self.text}


class DeadLLM:
    async def generate(self, *a, **k): raise RuntimeError("down")


@pytest.mark.asyncio
async def test_reply_reports_the_action_even_when_the_model_is_down() -> None:
    row = await _propose()
    out = await reply(TASK, "approve", "Prep my week", "report", [], llm=DeadLLM())
    assert (await repo.get(row.id)).status == CommitmentStatus.OPEN.value
    assert "Approved" in out["reply"]  # the user still learns what changed


@pytest.mark.asyncio
async def test_reply_prompt_carries_the_action_note_and_bans_machinery() -> None:
    await _propose()
    llm = FakeLLM("Done — reminders are on.")
    await reply(TASK, "approve", "Prep my week", "the report", [], llm=llm)
    prompt = llm.prompts[0]
    assert "WHAT YOU JUST DID" in prompt
    assert "Never mention agents, pipelines" in prompt
