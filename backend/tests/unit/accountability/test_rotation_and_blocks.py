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
    # A theme carries either its own tasks or a set of variants that do.
    assert all(
        c.get("tasks") or c.get("variants") for c in r["cycle"]
    ), "a themed day with neither tasks nor variants does nothing"


def test_web3_runs_every_single_day() -> None:
    """It is the stated priority — it must never be crowded out by the cycle."""
    for offset in range(21):
        picked = themes_for(date.fromordinal(date(2026, 9, 10).toordinal() + offset))
        # web3-study resolves to a per-chain theme id ("web3-study-evm"), so
        # match the family rather than the exact name.
        families = {t.theme.split("-")[0] + "-" + t.theme.split("-")[1] for t in picked["daily"]}
        assert families == {"web3-bounty", "web3-study"}


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
    from src.agents.rotation import themes_for

    # Find the interview-prep day rather than hardcoding one: adding a theme
    # shifts every date, and a hardcoded date makes this test brittle.
    start = date(2026, 9, 11)
    day = next(
        date.fromordinal(start.toordinal() + i)
        for i in range(30)
        if themes_for(date.fromordinal(start.toordinal() + i))["cycled"].theme == "interview-prep"
    )
    allowed = active_source_keys(day)
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


# ── reminders are opt-in ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_silent_commitment_is_never_nagged() -> None:
    """Tracked and shown, but it does not interrupt. This is what stops two
    dozen study picks from becoming two dozen reminders."""
    silent = await repo.create(
        title="Tokens & context windows",
        due_at=datetime.now(timezone.utc) - timedelta(hours=3),
        status=CommitmentStatus.OPEN.value,
        remind=False,
    )
    loud = await repo.create(
        title="Work one bounty target for 45 minutes",
        due_at=datetime.now(timezone.utc) - timedelta(hours=1),
        status=CommitmentStatus.OPEN.value,
        remind=True,
    )
    due = await repo.due_for_nag()
    assert [c.id for c in due] == [loud.id]
    assert silent.id not in [c.id for c in due]


@pytest.mark.asyncio
async def test_silence_can_be_lifted_without_recreating_anything() -> None:
    row = await repo.create(
        title="Design [X]. You have 45 minutes.",
        due_at=datetime.now(timezone.utc) - timedelta(hours=2),
        status=CommitmentStatus.OPEN.value,
        remind=False,
    )
    assert await repo.due_for_nag() == []

    await repo.set_remind(row.id, True)
    assert [c.id for c in await repo.due_for_nag()] == [row.id]

    await repo.set_remind(row.id, False)
    assert await repo.due_for_nag() == []


def test_the_bulk_study_sources_are_silent_by_configuration() -> None:
    """The 48-topic tracker and the question bank fill the day view; they are
    not what should be buzzing a phone."""
    from src.agents.study_sync import load_sources

    by_key = {s.key: s for s in load_sources(enabled_only=False)}
    assert by_key["ai-tracker"].remind is False
    assert by_key["sysdesign-interview"].remind is False
    assert by_key["football-calendar"].remind is True
    assert by_key["investing-monthly"].remind is True


def test_every_rotation_theme_reminds() -> None:
    """The themed day plan is the core work — that is the part that chases."""
    from src.agents.rotation import load_rotation

    r = load_rotation()
    assert all(t.get("remind", True) for t in r["daily"] + r["cycle"])


# ── chain variants ───────────────────────────────────────────────────────────


def test_web3_study_visits_every_chain() -> None:
    """Four chains sharing one slot: whichever is listed first would otherwise
    be the only one ever studied."""
    from src.agents.rotation import themes_for

    seen = set()
    for i in range(8):
        picked = themes_for(date.fromordinal(date(2026, 9, 11).toordinal() + i))
        study = next(t for t in picked["daily"] if t.theme.startswith("web3-study"))
        seen.add(study.variant_name)
    assert seen == {"EVM", "Solana", "Cosmos", "Infra"}


def test_a_cycled_theme_advances_its_variant_on_every_appearance() -> None:
    """The regression this guards: an 8-day cycle with 4 variants indexed on the
    raw ordinal shows variant 0 on every appearance, forever, because 8 % 4 == 0.
    """
    from src.agents.rotation import load_rotation, themes_for

    cycle_len = len(load_rotation()["cycle"])
    variants = []
    start = date(2026, 9, 11)
    for i in range(cycle_len * 4):
        picked = themes_for(date.fromordinal(start.toordinal() + i))["cycled"]
        if picked.theme.startswith("chain-interviews"):
            variants.append(picked.variant_name)
    assert len(variants) == 4, f"expected four appearances, got {variants}"
    assert len(set(variants)) == 4, f"the same variant kept coming up: {variants}"


def test_a_theme_without_variants_is_untouched() -> None:
    from src.agents.rotation import Theme

    plain = Theme(theme="video", label="Video", tasks=["Record one short"])
    assert plain.resolve(date(2026, 9, 11)) is plain


def test_every_chain_task_carries_a_resource_link() -> None:
    """A practice task with no pointer means opening a browser and deciding
    where to start, which is the friction this is meant to remove."""
    from src.agents.rotation import load_rotation

    r = load_rotation()
    themed = [t for t in r["daily"] + r["cycle"] if t.get("variants")]
    assert themed, "no variant-based themes configured"
    for theme in themed:
        for variant in theme["variants"]:
            assert variant["tasks"], f"{theme['theme']}/{variant['name']} has no tasks"
            assert any(
                "http" in task for task in variant["tasks"]
            ), f"{theme['theme']}/{variant['name']} has no link to work from"
