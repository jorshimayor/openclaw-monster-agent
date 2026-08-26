"""End-to-end behaviour of the ledger: file → chase → reject → close.

Runs against the repo's in-memory fallback (no DATABASE_URL), which exercises
the same code paths the API and Telegram handlers use.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.agents import telegram_inbox as inbox
from src.agents.commitment_extractor import parse_markdown_plan, resolve_due
from src.core import commitment_repo as repo
from src.models.commitment import CommitmentStatus

PLAN = """# Final Synthesized Report

**Monday, August 24**

- **Evening**: Start drafting the BUILD task (rewriting the chelsea_bot README).
- **Constant**: Publish the model call before the match.

**Thursday, August 27**

- **Evening**: Draft the X post and lead with one surprising number.
"""


@pytest.fixture(autouse=True)
def _clean_store():
    repo._MEM.clear()
    yield
    repo._MEM.clear()


async def _file_one(title: str = "Ship the README", hours_overdue: float = 1.0):
    return await repo.create(
        title=title,
        due_at=datetime.now(timezone.utc) - timedelta(hours=hours_overdue),
        source="task",
    )


@pytest.mark.asyncio
async def test_markdown_plan_becomes_dated_action_items() -> None:
    items = parse_markdown_plan(PLAN)
    assert len(items) == 3
    assert items[0]["day"] == "monday"
    assert items[0]["time_of_day"] == "evening"
    assert items[2]["day"] == "thursday"
    # Headings are not mistaken for action items.
    assert all("August" not in i["title"] for i in items)


@pytest.mark.asyncio
async def test_resolve_due_always_points_forward() -> None:
    now = datetime.now(timezone.utc)
    for day in ("", "today", "tomorrow", "monday", "friday"):
        due = resolve_due(day, "evening")
        assert due > now, f"{day!r} resolved to a due time in the past"


@pytest.mark.asyncio
async def test_overdue_commitment_is_picked_up_for_nagging() -> None:
    row = await _file_one()
    due = await repo.due_for_nag()
    assert [c.id for c in due] == [row.id]


@pytest.mark.asyncio
async def test_nag_interval_suppresses_a_second_reminder_until_it_elapses() -> None:
    row = await _file_one()
    await repo.mark_nagged(row.id, next_interval_sec=1800, escalation=0)
    assert await repo.due_for_nag() == []

    # Simulate the interval elapsing.
    await repo._mutate(
        row.id, last_nagged_at=datetime.now(timezone.utc) - timedelta(seconds=1801)
    )
    assert [c.id for c in await repo.due_for_nag()] == [row.id]


@pytest.mark.asyncio
async def test_snooze_delays_but_never_closes() -> None:
    row = await _file_one()
    await repo.snooze(row.id, minutes=60)
    assert await repo.due_for_nag() == []

    refreshed = await repo.get(row.id)
    assert refreshed.status == CommitmentStatus.OPEN.value  # still owed

    await repo._mutate(row.id, snooze_until=datetime.now(timezone.utc) - timedelta(minutes=1))
    assert [c.id for c in await repo.due_for_nag()] == [row.id]


@pytest.mark.asyncio
async def test_complete_refuses_to_close_without_an_artifact() -> None:
    row = await _file_one()
    assert await repo.complete(row.id, artifact_kind="text") is None
    assert await repo.complete(row.id, artifact_kind="text", artifact_text="   ") is None
    assert (await repo.get(row.id)).status == CommitmentStatus.OPEN.value


@pytest.mark.asyncio
async def test_done_command_rejects_a_bare_claim_then_accepts_a_link() -> None:
    row = await _file_one()
    short = str(row.id)[:8]

    rejected = await inbox._handle_command("/done", short, f"/done {short}", None, None)
    assert "Not accepted" in rejected
    assert (await repo.get(row.id)).status == CommitmentStatus.OPEN.value

    accepted = await inbox._handle_command(
        "/done", f"{short} https://github.com/me/chelsea_bot", "", None, None
    )
    assert "Closed" in accepted
    closed = await repo.get(row.id)
    assert closed.status == CommitmentStatus.DONE.value
    assert closed.artifact_kind == "link"
    assert closed.artifact_url == "https://github.com/me/chelsea_bot"


@pytest.mark.asyncio
async def test_closed_commitment_stops_being_nagged() -> None:
    row = await _file_one()
    await repo.complete(row.id, artifact_kind="link", artifact_url="https://x.com/a/1")
    assert await repo.due_for_nag() == []


@pytest.mark.asyncio
async def test_dropping_records_abandonment_rather_than_completion() -> None:
    row = await _file_one()
    await repo.drop(row.id)
    dropped = await repo.get(row.id)
    assert dropped.status == CommitmentStatus.DROPPED.value
    assert dropped.artifact_kind is None
    assert await repo.due_for_nag() == []


@pytest.mark.asyncio
async def test_bare_artifact_closes_the_only_overdue_item() -> None:
    row = await _file_one()
    reply = await inbox._handle_bare_artifact("https://x.com/me/status/1", None, None)
    assert "Closed" in reply
    assert (await repo.get(row.id)).status == CommitmentStatus.DONE.value


@pytest.mark.asyncio
async def test_bare_artifact_asks_which_one_when_several_are_overdue() -> None:
    a = await _file_one("Ship the README")
    b = await _file_one("Publish the X post")
    reply = await inbox._handle_bare_artifact("https://x.com/me/status/1", None, None)
    assert "Which one" in reply
    for row in (a, b):
        assert str(row.id)[:8] in reply
        assert (await repo.get(row.id)).status == CommitmentStatus.OPEN.value


@pytest.mark.asyncio
async def test_short_id_prefix_resolves_to_the_commitment() -> None:
    row = await _file_one()
    assert (await repo.resolve_ref(str(row.id)[:8])).id == row.id
    assert (await repo.resolve_ref(str(row.id))).id == row.id
    assert await repo.resolve_ref("zzzzzzzz") is None


@pytest.mark.asyncio
async def test_stats_track_open_overdue_and_settled() -> None:
    await _file_one("overdue one", hours_overdue=2)
    future = await repo.create(
        title="not yet due", due_at=datetime.now(timezone.utc) + timedelta(days=1)
    )
    settled = await _file_one("already shipped")
    await repo.complete(settled.id, artifact_kind="link", artifact_url="https://x.com/1")

    stats = await repo.stats()
    assert stats == {"open": 2, "overdue": 1, "done": 1, "dropped": 0, "total": 3}
    assert future is not None
