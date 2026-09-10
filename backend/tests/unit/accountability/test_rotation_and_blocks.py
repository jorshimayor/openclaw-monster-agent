"""Rotation, block ticking, and the reminder cap."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from src.agents import nagger
from src.agents.rotation import active_source_keys, cycle_index, load_rotation, themes_for
from src.core import commitment_repo as repo
from src.core import day_block_repo
from src.models.commitment import CommitmentStatus


# ── rotation ─────────────────────────────────────────────────────────────────


def test_the_shipped_rotation_is_valid() -> None:
    r = load_rotation()
    assert r["enabled"] is True
    assert r["daily"], "web3 should run daily"
    assert len(r["cycle"]) >= 5
    keys = [c["theme"] for c in r["cycle"]] + [c["theme"] for c in r["daily"]]
    assert len(keys) == len(set(keys)), "duplicate theme keys"
    assert all(c.get("tasks") for c in r["cycle"]), "a themed day with no tasks does nothing"


def test_web3_runs_every_single_day() -> None:
    """It is the stated priority — it must never be crowded out by the cycle."""
    for offset in range(21):
        picked = themes_for(date.fromordinal(date(2026, 9, 10).toordinal() + offset))
        assert {t.theme for t in picked["daily"]} == {"web3-bounty", "web3-study"}


def test_the_cycle_visits_every_theme_before_repeating() -> None:
    cycle = load_rotation()["cycle"]
    seen = [
        themes_for(date.fromordinal(date(2026, 9, 10).toordinal() + i))["cycled"].theme
        for i in range(len(cycle))
    ]
    assert len(set(seen)) == len(cycle), f"a theme was skipped or repeated: {seen}"


def test_consecutive_days_never_repeat_a_theme() -> None:
    days = [date.fromordinal(date(2026, 12, 28).toordinal() + i) for i in range(10)]
    picked = [themes_for(d)["cycled"].theme for d in days]
    assert all(a != b for a, b in zip(picked, picked[1:])), picked


def test_the_cycle_does_not_stumble_over_new_year() -> None:
    """Day-of-year would repeat or skip a theme every January; ordinals don't."""
    dec31 = themes_for(date(2026, 12, 31))["cycled"].theme
    jan01 = themes_for(date(2027, 1, 1))["cycled"].theme
    assert dec31 != jan01


def test_cycle_index_is_stable_and_wraps() -> None:
    assert cycle_index(date(2026, 9, 10), 7) == cycle_index(date(2026, 9, 17), 7)
    assert 0 <= cycle_index(date(2026, 9, 10), 7) < 7
    assert cycle_index(date(2026, 9, 10), 0) == 0  # no cycle configured


def test_only_todays_themed_sources_are_allowed() -> None:
    allowed = active_source_keys(date(2026, 9, 11))  # interview prep day
    assert allowed is not None
    assert "ai-tracker" in allowed
    assert "football-calendar" not in allowed


def test_upcoming_shows_what_is_coming() -> None:
    picked = themes_for(date(2026, 9, 10))
    assert len(picked["upcoming"]) >= 3
    assert picked["upcoming"][0]["theme"] != picked["cycled"].label


# ── ticking a timetable block ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_block_can_be_ticked_for_one_day_only() -> None:
    """The template cell is shared by all seven weekdays, so completion has to
    live outside the sheet or Thursday's tick would mark every day."""
    day_block_repo._MEM.clear()
    thu, fri = date(2026, 9, 10), date(2026, 9, 11)

    await day_block_repo.set_done(thu, "05:45", "90 min Deep Block 1", True)
    assert await day_block_repo.done_slots(thu) == [
        {"slot": "05:45", "label": "90 min Deep Block 1"}
    ]
    assert await day_block_repo.done_slots(fri) == []


@pytest.mark.asyncio
async def test_ticking_is_idempotent_and_reversible() -> None:
    day_block_repo._MEM.clear()
    day = date(2026, 9, 10)
    for _ in range(3):
        await day_block_repo.set_done(day, "07:30", "Daily Bug Bounty Session", True)
    assert len(await day_block_repo.done_slots(day)) == 1

    await day_block_repo.set_done(day, "07:30", "Daily Bug Bounty Session", False)
    assert await day_block_repo.done_slots(day) == []


# ── the reminder cap ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_full_day_does_not_produce_a_wall_of_reminders(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Twenty approved items used to mean twenty reminders every ten minutes,
    which trains you to ignore all of them."""
    now = datetime.now(timezone.utc)
    for i in range(20):
        await repo.create(
            title=f"Item {i}",
            due_at=now - timedelta(hours=i + 1),
            status=CommitmentStatus.OPEN.value,
        )

    monkeypatch.setattr(nagger, "in_quiet_hours", lambda now=None: False)
    engine = nagger.NagEngine()
    sent = []

    async def _fake(text, pin, silent):
        sent.append(text)
        return {"ok": True}

    monkeypatch.setattr(engine, "_telegram", _fake)
    result = await engine.tick()

    assert result["checked"] == 20
    assert result["sent"] == 2, "the per-round cap was not applied"
    assert result["held_back"] == 18
    assert len(sent) == 2
    # The longest-ignored come first.
    assert "Item 19" in sent[0]
    # And the queue is never silently hidden.
    assert "18 more due" in sent[0]


@pytest.mark.asyncio
async def test_held_back_items_keep_their_place_in_the_ladder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Being held back is not the same as being reminded: nag_count must not
    move, or an item would escalate without ever being sent."""
    now = datetime.now(timezone.utc)
    rows = []
    for i in range(5):
        rows.append(
            await repo.create(
                title=f"Item {i}",
                due_at=now - timedelta(hours=i + 1),
                status=CommitmentStatus.OPEN.value,
            )
        )
    monkeypatch.setattr(nagger, "in_quiet_hours", lambda now=None: False)
    engine = nagger.NagEngine()
    async def _fake(text, pin, silent):
        return {"ok": True}

    monkeypatch.setattr(engine, "_telegram", _fake)
    await engine.tick()

    counts = []
    for r in rows:
        counts.append((await repo.get(r.id)).nag_count)
    counts.sort()
    assert counts == [0, 0, 0, 1, 1]
