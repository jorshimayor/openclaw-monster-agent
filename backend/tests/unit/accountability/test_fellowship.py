"""The fellowship is a schedule, not a rotation. These pin the difference."""

import json
from datetime import date, timedelta

import pytest

from src.agents.fellowship import (
    TOTAL_WEEKS,
    extras_for,
    load_config,
    position,
    summary,
    tasks_for,
)

START = date(2026, 9, 28)  # a Monday


@pytest.fixture
def config():
    cfg = load_config()
    cfg["start_date"] = START.isoformat()
    cfg["path"] = None
    cfg["assignments"] = []
    return cfg


def test_the_shipped_plan_covers_every_week_exactly_once():
    weeks = [w["week"] for w in load_config()["weeks"]]
    assert weeks == list(range(1, TOTAL_WEEKS + 1))


def test_every_week_has_something_to_do():
    for raw in load_config()["weeks"]:
        has_work = raw.get("lab") or raw.get("paths") or raw.get("deliverable")
        assert has_work, f"week {raw['week']} would file nothing"


def test_every_reading_link_is_a_url():
    for raw in load_config()["weeks"]:
        for reading in filter(None, [raw.get("reading")] + [
            p.get("reading") for p in (raw.get("paths") or {}).values()
        ]):
            assert reading["url"].startswith("http"), reading


def test_nothing_is_filed_before_week_one(config):
    assert tasks_for(START - timedelta(days=1), config) == []
    assert not position(START - timedelta(days=1), config).started


def test_nothing_is_filed_after_week_forty_eight(config):
    last = START + timedelta(weeks=TOTAL_WEEKS - 1, days=6)
    assert position(last, config).week == TOTAL_WEEKS
    after = START + timedelta(weeks=TOTAL_WEEKS)
    assert position(after, config).finished
    assert tasks_for(after, config) == []


def test_the_week_does_not_advance_mid_week(config):
    """A week's work stays on the board all week — 20 hours is not a Monday job."""
    weeks = {position(START + timedelta(days=d), config).week for d in range(7)}
    assert weeks == {1}
    assert position(START + timedelta(days=7), config).week == 2


def test_a_mid_week_start_still_counts_as_week_one(config):
    config["start_date"] = "2026-09-30"  # a Wednesday
    assert position(date(2026, 9, 28), config).week == 1
    assert position(date(2026, 10, 4), config).week == 1
    assert position(date(2026, 10, 5), config).week == 2


def test_an_unchosen_path_asks_for_the_decision_instead_of_picking_one(config):
    pos = position(START + timedelta(weeks=16), config)
    assert pos.plan is None
    assert {a.path for a in pos.alternatives} == {"A", "B"}


def test_choosing_a_path_resolves_those_weeks(config):
    config["path"] = "B"
    pos = position(START + timedelta(weeks=16), config)
    assert pos.plan is not None and pos.plan.path == "B"
    assert "multi-hop" in pos.plan.lab


def test_assignments_file_against_their_own_week(config):
    config["assignments"] = [
        {"week": 3, "kind": "book", "title": "Chapters 1-3"},
        {"week": 9, "kind": "assignment", "title": "Not yet"},
    ]
    assert len(extras_for(3, config)) == 1
    assert "BOOK" in extras_for(3, config)[0]
    assert extras_for(4, config) == []


def test_summary_reports_week_one_start_before_the_programme_begins(config, monkeypatch):
    """Not the week today falls in — that one is in the past and reads as wrong."""
    monkeypatch.setattr("src.agents.fellowship.load_config", lambda: config)
    s = summary(START - timedelta(days=3))
    assert s["programme_start"] == START.isoformat()
    assert s["started"] is False


# --- scheduling: what is chased daily, and what is due Sunday ---------------

from src.agents.fellowship import books_for, scheduled_for  # noqa: E402


def sched(week: int, config):
    from datetime import timedelta
    return scheduled_for(START + timedelta(weeks=week - 1), config)


def test_the_anchor_reading_and_lab_are_chased_every_day(config):
    daily = [t for t in sched(1, config) if not t.key]
    assert any("ANCHOR READING" in t.text for t in daily)
    assert any("lab:" in t.text for t in daily)


def test_weekly_work_is_due_sunday_evening(config):
    weekly = {t.key: t for t in sched(1, config) if t.key}
    assert weekly, "nothing weekly was scheduled"
    for task in weekly.values():
        assert (task.day, task.time) == ("sunday", "20:00"), task.text


def test_weekly_work_is_filed_once_not_once_a_day(config):
    """A chapter filed every day would be seven commitments for one chapter."""
    from datetime import timedelta
    keys = [
        {t.key for t in scheduled_for(START + timedelta(days=d), config) if t.key}
        for d in range(7)
    ]
    assert all(k == keys[0] for k in keys)
    assert "w01-book" in keys[0]
    # ...and the next week's keys are different, so it does file again.
    assert "w02-book" in {t.key for t in sched(2, config) if t.key}


def test_the_week_cannot_close_without_an_artifact(config):
    gate = next(t for t in sched(1, config) if t.key.endswith("-artifact"))
    assert "post the artifact" in gate.text
    assert ".ipynb" in gate.text
    assert (gate.day, gate.time) == ("sunday", "20:00")


def test_one_book_chapter_a_week_counted_from_the_week(config):
    assert "ch.1" in books_for(1, config)[0]
    assert "ch.5" in books_for(5, config)[0]


def test_a_book_runs_out_rather_than_looping(config):
    total = len(config["books"][0]["chapters"])
    assert books_for(total, config)
    assert books_for(total + 1, config) == []


def test_a_book_does_not_start_before_its_week(config):
    config["books"][0]["start_week"] = 3
    assert books_for(2, config) == []
    assert "ch.1" in books_for(3, config)[0]
