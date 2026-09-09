"""Study sheets → a finite daily ask.

Fixtures mirror the real sheets: a title block above the header, a "Wk" column
that is a week *number* sitting next to the date, and repeated header bands.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.agents.study_sync import (
    StudySource,
    StudySync,
    find_study_header,
    load_sources,
    map_study_columns,
    parse_week_start,
    resolve_week_column,
)
from src.core import commitment_repo as repo
from src.models.commitment import CommitmentStatus

TRACKER_VALUES = [
    ["Applied AI Engineering & FDE"],
    ["Goal", "Build production-ready LLM systems"],
    ["Core principle", "Architecture, trade-offs"],
    [],
    ["Category", "Skill / Topic", "What to Learn", "Priority", "Depth", "Why It Matters", "Practice", "Status"],
    ["LLM Fundamentals", "Tokens & context windows", "Tokenization, limits", "Must", "Deep", "Prevents overflow", "Build a guard", ""],
    ["LLM Fundamentals", "Sampling parameters", "Temperature, top_p", "Should", "Working", "Output control", "Sweep them", ""],
    ["RAG", "Chunking strategies", "Fixed vs semantic", "Must", "Deep", "Retrieval quality", "Compare three", ""],
    ["Ops", "Cost tracking", "Token accounting", "Could", "Aware", "Budget", "Dashboard", "done"],
]

FOOTBALL_VALUES = [
    ["SEASON CALENDAR 2026/27"],
    ["Work the BUILD column. Everything else is optional."],
    [],
    ["Wk", "Week starting", "Phase", "What's happening", "BUILD (the only mandatory column)", "Post on X", "Long-form", "Outreach action"],
    ["1", "17 Aug 2026", "Pre-season", "Community Shield", "Audit chelsea_bot honestly", "Introduce yourself", "Blog", "Follow 30 people"],
    ["2", "24 Aug 2026", "Pre-season", "Matchday 1", "Rewrite the chelsea_bot README", "Share the writeup", "LinkedIn", "Ask 3 people"],
    ["3", "31 Aug 2026", "Build the base", "Deadline day", "Start the free-data package", "Deadline chart", "-", "Post the scope"],
]


class FakeSync(StudySync):
    def __init__(self, values):
        super().__init__()
        self.values = values

    async def read(self, source):
        idx, header = find_study_header(self.values)
        return idx, header, self.values[idx + 1 :], None


def _source(**kw) -> StudySource:
    base = {
        "key": "t", "name": "Tracker", "sheet_id": "sheet-1",
        "range": "Roadmap!A1:J60", "kind": "backlog", "daily_count": 2,
        "due_time": "11:00", "priority_order": ["must", "should", "could"],
    }
    base.update(kw)
    return StudySource.from_dict(base)


# ── shape detection ──────────────────────────────────────────────────────────


def test_header_is_found_below_the_title_block() -> None:
    idx, header = find_study_header(TRACKER_VALUES)
    assert idx == 4
    cols = map_study_columns(header)
    assert header[cols["title"]] == "Skill / Topic"
    assert "status" in cols and "priority" in cols


def test_a_question_bank_maps_question_as_the_title() -> None:
    values = [
        ["INTERVIEW QUESTION BANK"], ["Let's Code"], [],
        ["Category", "Question", "What they are really testing", "Level"],
        ["Process", "Design [X]. You have 45 minutes.", "Structure", "Core"],
    ]
    idx, header = find_study_header(values)
    assert idx == 3
    assert header[map_study_columns(header)["title"]] == "Question"


def test_the_date_column_beats_the_week_number_column() -> None:
    """Name matching picks "Wk"; every date then fails to parse and the
    calendar looks empty. The data decides, not the label."""
    idx, header = find_study_header(FOOTBALL_VALUES)
    rows = FOOTBALL_VALUES[idx + 1 :]
    named = map_study_columns(header).get("week")
    assert header[named] == "Wk"
    resolved = resolve_week_column(header, rows, named)
    assert header[resolved] == "Week starting"


@pytest.mark.parametrize(
    "text,expected",
    [("17 Aug 2026", "2026-08-17"), ("2026-09-07", "2026-09-07"), ("not a date", None)],
)
def test_week_dates_parse(text: str, expected) -> None:
    got = parse_week_start(text)
    assert (got.strftime("%Y-%m-%d") if got else None) == expected


# ── backlog picking ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_backlog_picks_must_before_should() -> None:
    items, err = await FakeSync(TRACKER_VALUES).pick_backlog(_source())
    assert err is None
    assert [i["title"] for i in items] == ["Tokens & context windows", "Chunking strategies"]


@pytest.mark.asyncio
async def test_rows_already_marked_done_in_the_sheet_are_skipped() -> None:
    items, _ = await FakeSync(TRACKER_VALUES).pick_backlog(_source(daily_count=10))
    assert "Cost tracking" not in [i["title"] for i in items]


@pytest.mark.asyncio
async def test_the_same_row_is_never_handed_to_you_twice() -> None:
    """The ledger is the progress record for sheets with no Status column —
    a row already filed does not come round again tomorrow, in any status."""
    sync = FakeSync(TRACKER_VALUES)
    source = _source(daily_count=1)

    first = await sync.sync_source(source)
    assert first["filed"] == 1
    filed_title = first["commitments"][0]["title"]

    second_items, _ = await sync.pick_backlog(source)
    assert filed_title not in [i["title"] for i in second_items]


@pytest.mark.asyncio
async def test_a_dropped_item_does_not_come_back() -> None:
    sync = FakeSync(TRACKER_VALUES)
    result = await sync.sync_source(_source(daily_count=1))
    row = await repo.get(__import__("uuid").UUID(result["commitments"][0]["id"]))
    await repo.drop(row.id)

    items, _ = await sync.pick_backlog(_source(daily_count=1))
    assert row.title not in [i["title"] for i in items]


@pytest.mark.asyncio
async def test_items_arrive_proposed_and_due_at_the_configured_time() -> None:
    result = await FakeSync(TRACKER_VALUES).sync_source(_source(daily_count=1))
    rows = await repo.list_all()
    assert rows[0].status == CommitmentStatus.PROPOSED.value
    assert result["filed"] == 1


@pytest.mark.asyncio
async def test_a_missing_topic_column_is_reported_not_guessed() -> None:
    items, err = await FakeSync([["Notes"], ["just prose"]]).pick_backlog(_source())
    assert items == []
    assert "no topic/question column" in err


# ── weekly picking ───────────────────────────────────────────────────────────


def _weekly_source(**kw) -> StudySource:
    base = {
        "key": "f", "name": "Football", "sheet_id": "sheet-2",
        "range": "Calendar!A1:H60", "kind": "weekly",
        "item_columns": ["BUILD"], "due_time": "19:00",
    }
    base.update(kw)
    return StudySource.from_dict(base)


@pytest.mark.asyncio
async def test_weekly_picks_the_row_covering_today() -> None:
    sync = FakeSync(FOOTBALL_VALUES)
    items, err = await sync.pick_weekly(
        _weekly_source(), today=datetime(2026, 8, 27, tzinfo=timezone.utc)
    )
    assert err is None
    assert [i["title"] for i in items] == ["Rewrite the chelsea_bot README"]


@pytest.mark.asyncio
async def test_weekly_takes_the_latest_week_that_has_started() -> None:
    sync = FakeSync(FOOTBALL_VALUES)
    items, _ = await sync.pick_weekly(
        _weekly_source(), today=datetime(2026, 9, 3, tzinfo=timezone.utc)
    )
    assert [i["title"] for i in items] == ["Start the free-data package"]


@pytest.mark.asyncio
async def test_only_the_mandatory_column_is_emitted() -> None:
    sync = FakeSync(FOOTBALL_VALUES)
    items, _ = await sync.pick_weekly(
        _weekly_source(), today=datetime(2026, 8, 20, tzinfo=timezone.utc)
    )
    titles = [i["title"] for i in items]
    assert titles == ["Audit chelsea_bot honestly"]
    assert "Introduce yourself" not in titles  # optional columns stay optional


@pytest.mark.asyncio
async def test_a_future_only_calendar_says_so() -> None:
    sync = FakeSync(FOOTBALL_VALUES)
    items, err = await sync.pick_weekly(
        _weekly_source(), today=datetime(2026, 1, 1, tzinfo=timezone.utc)
    )
    assert items == []
    assert "on or before today" in err


# ── config ───────────────────────────────────────────────────────────────────


def test_the_shipped_config_parses_and_has_enabled_sources() -> None:
    sources = load_sources(enabled_only=False)
    assert sources, "config/study_sources.json produced no sources"
    assert all(s.sheet_id for s in sources)
    assert any(s.enabled for s in sources)
    assert {s.kind for s in sources} <= {"backlog", "weekly", "routine"}


def test_every_source_key_is_unique() -> None:
    keys = [s.key for s in load_sources(enabled_only=False)]
    assert len(keys) == len(set(keys))


# ── routine: a checklist that comes round every period ───────────────────────

ROUTINE_VALUES = [
    ["THE ROUTINE"],
    ["Thirty minutes a month is enough"],
    [],
    ["#", "Do this", "Why", "Done"],
    ["1", "Make the contribution", "The one thing that determines the outcome", ""],
    ["2", "Update the Price now column", "Five minutes", "done"],
    ["3", "Read the two verdicts", "Direct the new contribution", ""],
]


def _routine_source(**kw) -> StudySource:
    base = {
        "key": "inv", "name": "Investing routine", "sheet_id": "sheet-3",
        "range": "Monthly Routine!A1:H24", "kind": "routine",
        "cadence": "monthly", "due_time": "17:00",
    }
    base.update(kw)
    return StudySource.from_dict(base)


@pytest.mark.parametrize(
    "cadence,expected",
    [("monthly", "2026-09"), ("quarterly", "2026-Q3"), ("weekly", "2026-W37"), ("daily", "2026-09-09")],
)
def test_period_stamps(cadence: str, expected: str) -> None:
    from src.agents.study_sync import period_stamp

    assert period_stamp(cadence, datetime(2026, 9, 9, tzinfo=timezone.utc)) == expected


@pytest.mark.asyncio
async def test_a_routine_hands_over_the_whole_checklist() -> None:
    items, err = await FakeSync(ROUTINE_VALUES).pick_routine(_routine_source())
    assert err is None
    assert [i["title"] for i in items] == [
        "Make the contribution",
        "Update the Price now column",
        "Read the two verdicts",
    ]


@pytest.mark.asyncio
async def test_a_ticked_box_in_the_sheet_is_ignored_for_routines() -> None:
    """Tick boxes are not period-scoped — a step ticked in August is still
    ticked in September, so the sheet cannot be the record here."""
    items, _ = await FakeSync(ROUTINE_VALUES).pick_routine(_routine_source())
    assert "Update the Price now column" in [i["title"] for i in items]


@pytest.mark.asyncio
async def test_the_routine_does_not_repeat_within_the_same_period() -> None:
    sync = FakeSync(ROUTINE_VALUES)
    source = _routine_source()
    first = await sync.sync_source(source)
    assert first["filed"] == 3

    again, _ = await sync.pick_routine(source)
    assert again == []


@pytest.mark.asyncio
async def test_the_routine_comes_back_next_month() -> None:
    sync = FakeSync(ROUTINE_VALUES)
    source = _routine_source()
    await sync.pick_routine(source, now=datetime(2026, 9, 9, tzinfo=timezone.utc))
    await sync.sync_source(source)

    next_month, _ = await sync.pick_routine(
        source, now=datetime(2026, 10, 2, tzinfo=timezone.utc)
    )
    assert len(next_month) == 3
    assert all(i["period"] == "2026-10" for i in next_month)
