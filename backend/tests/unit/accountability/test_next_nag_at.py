"""When the container next needs to exist.

The mirror of due_for_nag. Getting it wrong either wedges the reminder chain
(too late) or reintroduces the poll it replaces (too early).
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from src.core import commitment_repo as repo

NOW = datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)


def row(**kw):
    base = dict(
        status="open", remind=True, due_at=NOW - timedelta(minutes=5),
        snooze_until=None, last_nagged_at=None, nag_interval_sec=1800,
    )
    base.update(kw)
    return SimpleNamespace(**base)


@pytest.fixture
def rows(monkeypatch):
    held: list = []

    async def fake_list_all(status=None, limit=500):
        return [r for r in held if status is None or r.status == status]

    monkeypatch.setattr(repo, "list_all", fake_list_all)
    return held


@pytest.mark.asyncio
async def test_nothing_pending_means_do_not_wake_at_all(rows):
    """The case the old ten-minute cron could not express, and most of the day."""
    assert await repo.next_nag_at(NOW) is None


@pytest.mark.asyncio
async def test_an_overdue_commitment_wakes_immediately(rows):
    rows.append(row())
    assert await repo.next_nag_at(NOW) == NOW


@pytest.mark.asyncio
async def test_a_future_commitment_wakes_when_it_comes_due(rows):
    due = NOW + timedelta(hours=3)
    rows.append(row(due_at=due))
    assert await repo.next_nag_at(NOW) == due


@pytest.mark.asyncio
async def test_a_recent_nag_pushes_the_wake_out_by_one_interval(rows):
    last = NOW - timedelta(minutes=10)
    rows.append(row(last_nagged_at=last, nag_interval_sec=1800))
    assert await repo.next_nag_at(NOW) == last + timedelta(seconds=1800)


@pytest.mark.asyncio
async def test_a_snooze_is_respected(rows):
    until = NOW + timedelta(hours=2)
    rows.append(row(snooze_until=until))
    assert await repo.next_nag_at(NOW) == until


@pytest.mark.asyncio
async def test_a_silent_commitment_never_causes_a_wake(rows):
    """remind=False is tracked and shown, but must never cost a container start."""
    rows.append(row(remind=False))
    assert await repo.next_nag_at(NOW) is None


@pytest.mark.asyncio
async def test_the_earliest_of_many_wins(rows):
    rows.append(row(due_at=NOW + timedelta(hours=5)))
    rows.append(row(due_at=NOW + timedelta(hours=1)))
    rows.append(row(due_at=NOW + timedelta(hours=9)))
    assert await repo.next_nag_at(NOW) == NOW + timedelta(hours=1)


@pytest.mark.asyncio
async def test_a_row_with_no_due_date_is_ignored_rather_than_crashing(rows):
    rows.append(row(due_at=None))
    assert await repo.next_nag_at(NOW) is None
