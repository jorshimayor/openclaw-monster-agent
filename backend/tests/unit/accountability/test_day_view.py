"""The day view: template blocks as the day's shape, commitments on top."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from src.api.routes.day import parse_hhmm, to_utc, _local_bounds
from src.core import commitment_repo as repo
from src.models.commitment import CommitmentStatus


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("5:45AM - 7:15AM", "05:45"),   # a range gives its start
        ("5:00 AM", "05:00"),
        ("11:00 AM - 12:00 PM", "11:00"),
        ("1:00 PM - 2:15PM", "13:00"),
        ("4:00:00 PM - 5:00PM", "16:00"),
        ("14:30", "14:30"),
        ("12:00 PM", "12:00"),
        ("12:00 AM", "00:00"),
        ("", None),
        ("lunchtime", None),
    ],
)
def test_sheet_times_parse(raw: str, expected) -> None:
    """These are the literal strings in the timetable sheet."""
    assert parse_hhmm(raw) == expected


def test_local_times_convert_to_utc_at_the_configured_offset() -> None:
    utc = to_utc(date(2026, 9, 10), "13:30")
    assert utc.tzinfo is timezone.utc
    # WAT is UTC+1, so 13:30 local is 12:30Z.
    assert (utc.hour, utc.minute) == (12, 30)


def test_day_bounds_bracket_the_local_day_not_the_utc_one() -> None:
    start, end = _local_bounds(date(2026, 9, 10))
    assert end - start == timedelta(days=1)
    # Local midnight on the 10th is 23:00Z on the 9th at UTC+1.
    assert (start.day, start.hour) == (9, 23)


@pytest.mark.asyncio
async def test_only_items_due_on_that_local_day_are_returned() -> None:
    """An item at 00:30 local belongs to that day even though it is the
    previous day in UTC — bracketing on UTC dates would misfile it."""
    day = date(2026, 9, 10)
    start, end = _local_bounds(day)

    inside = await repo.create(
        title="Early item", due_at=start + timedelta(minutes=30),
        status=CommitmentStatus.OPEN.value,
    )
    late = await repo.create(
        title="Late item", due_at=end - timedelta(minutes=30),
        status=CommitmentStatus.OPEN.value,
    )
    outside = await repo.create(
        title="Tomorrow", due_at=end + timedelta(hours=1),
        status=CommitmentStatus.OPEN.value,
    )

    def _in_day(row):
        due = row.due_at if row.due_at.tzinfo else row.due_at.replace(tzinfo=timezone.utc)
        return start <= due < end

    rows = await repo.list_all(limit=100)
    titles = {r.title for r in rows if _in_day(r)}
    assert titles == {"Early item", "Late item"}
    assert outside.title not in titles


@pytest.mark.asyncio
async def test_moving_an_item_changes_only_its_time() -> None:
    row = await repo.create(
        title="Ship the README",
        due_at=to_utc(date(2026, 9, 10), "11:00"),
        status=CommitmentStatus.OPEN.value,
    )
    before = await repo.get(row.id)
    assert before.nag_count == 0

    moved = await repo.reschedule(row.id, to_utc(date(2026, 9, 10), "19:00"))
    assert moved.due_at == to_utc(date(2026, 9, 10), "19:00")
    assert moved.title == "Ship the README"
    assert moved.status == CommitmentStatus.OPEN.value


@pytest.mark.asyncio
async def test_rescheduling_clears_a_snooze() -> None:
    """Dragging something to a new time is an explicit decision about when it
    happens; a stale snooze would silently suppress the new slot."""
    row = await repo.create(
        title="Gym", due_at=to_utc(date(2026, 9, 10), "07:00"),
        status=CommitmentStatus.OPEN.value,
    )
    await repo.snooze(row.id, minutes=120)
    assert (await repo.get(row.id)).snooze_until is not None

    await repo.reschedule(row.id, to_utc(date(2026, 9, 10), "18:00"))
    assert (await repo.get(row.id)).snooze_until is None
