"""Google Sheet ⇄ ledger reconciliation."""

from __future__ import annotations

import pytest

from src.agents.schedule_sync import (
    ScheduleSync,
    _column_letter,
    map_columns,
    parse_row_key,
    row_key,
)
from src.core import commitment_repo as repo
from src.models.commitment import CommitmentStatus

SHEET = "sheet-abc"


@pytest.fixture(autouse=True)
def _clean_store():
    repo._MEM.clear()
    yield
    repo._MEM.clear()


class FakeSync(ScheduleSync):
    """Drives the real reconciliation logic over an in-memory sheet."""

    def __init__(self, header, rows):
        super().__init__()
        self.header = header
        self.rows = [list(r) for r in rows]
        self.writes = []

    async def read_rows(self, sheet_id, sheet_range):
        return self.header, self.rows, None

    async def _call(self, tool, args):
        if tool == "google_workspace.write_sheet":
            self.writes.append((args["range"], args["values"][0][0]))
            return {"updated_cells": 1}
        return {}


def test_column_matching_is_forgiving_about_header_wording() -> None:
    cols = map_columns(["Day", "Time (WAT)", "What", "Status", "Proof", "Notes"])
    assert cols["day"] == 0
    assert cols["time"] == 1
    assert cols["task"] == 2
    assert cols["status"] == 3
    assert cols["artifact"] == 4


def test_unknown_columns_are_ignored_not_fatal() -> None:
    cols = map_columns(["Task", "Priority", "Assignee"])
    assert cols == {"task": 0}


def test_row_key_round_trips() -> None:
    assert parse_row_key(f"some notes {row_key(SHEET, 7)}") == (SHEET, 7, None)
    assert parse_row_key(f"{row_key(SHEET, 7, 4)}") == (SHEET, 7, 4)
    assert parse_row_key("no key here") is None


@pytest.mark.parametrize("idx,letter", [(0, "A"), (3, "D"), (25, "Z"), (26, "AA"), (27, "AB")])
def test_column_letters(idx: int, letter: str) -> None:
    assert _column_letter(idx) == letter


@pytest.mark.asyncio
async def test_rows_become_commitments() -> None:
    s = FakeSync(
        ["Day", "Time", "Task", "Status", "Artifact"],
        [
            ["Monday", "19:00", "Rewrite the bot README", "", ""],
            ["Tuesday", "07:30", "Gym session", "", ""],
        ],
    )
    result = await s.sync(sheet_id=SHEET)
    assert result["ok"] is True
    assert result["filed"] == 2
    titles = {c.title for c in await repo.list_all()}
    assert titles == {"Rewrite the bot README", "Gym session"}


@pytest.mark.asyncio
async def test_resync_updates_instead_of_duplicating() -> None:
    s = FakeSync(["Day", "Time", "Task", "Status", "Artifact"],
                 [["Monday", "19:00", "Rewrite the bot README", "", ""]])
    await s.sync(sheet_id=SHEET)
    await s.sync(sheet_id=SHEET)
    assert len(await repo.list_all()) == 1


@pytest.mark.asyncio
async def test_editing_the_sheet_edits_the_commitment() -> None:
    s = FakeSync(["Day", "Time", "Task", "Status", "Artifact"],
                 [["Monday", "19:00", "Rewrite the bot README", "", ""]])
    await s.sync(sheet_id=SHEET)
    s.rows[0][2] = "Rewrite the bot README for a hiring manager"
    await s.sync(sheet_id=SHEET)
    rows = await repo.list_all()
    assert len(rows) == 1
    assert rows[0].title == "Rewrite the bot README for a hiring manager"


@pytest.mark.asyncio
async def test_ticking_the_sheet_closes_the_commitment() -> None:
    s = FakeSync(["Day", "Time", "Task", "Status", "Artifact"],
                 [["Monday", "19:00", "Rewrite the bot README", "", ""]])
    await s.sync(sheet_id=SHEET)
    s.rows[0][3] = "done"
    s.rows[0][4] = "https://github.com/me/repo"
    await s.sync(sheet_id=SHEET)
    row = (await repo.list_all())[0]
    assert row.status == CommitmentStatus.DONE.value
    assert row.artifact_url == "https://github.com/me/repo"


@pytest.mark.asyncio
async def test_rows_already_done_are_not_filed_as_new_work() -> None:
    s = FakeSync(["Day", "Time", "Task", "Status", "Artifact"],
                 [["Monday", "19:00", "Already shipped", "done", "https://x.com/1"]])
    result = await s.sync(sheet_id=SHEET)
    assert result["filed"] == 0
    assert await repo.list_all() == []


@pytest.mark.asyncio
async def test_closing_on_telegram_writes_back_into_the_sheet() -> None:
    s = FakeSync(["Day", "Time", "Task", "Status", "Artifact"],
                 [["Monday", "19:00", "Rewrite the bot README", "", ""]])
    await s.sync(sheet_id=SHEET)
    row = (await repo.list_all())[0]
    await repo.complete(row.id, artifact_kind="link", artifact_url="https://github.com/me/repo")

    result = await s.sync(sheet_id=SHEET)
    assert result["written_back"] == 2
    assert ("D2", "done") in s.writes
    assert ("E2", "https://github.com/me/repo") in s.writes


@pytest.mark.asyncio
async def test_missing_task_column_is_reported_not_guessed() -> None:
    s = FakeSync(["Priority", "Assignee"], [["high", "me"]])
    result = await s.sync(sheet_id=SHEET)
    assert result["ok"] is False
    assert "task column" in result["error"]


@pytest.mark.asyncio
async def test_sheet_without_status_column_is_read_only() -> None:
    s = FakeSync(["Day", "Time", "Task"], [["Monday", "19:00", "Rewrite the README"]])
    result = await s.sync(sheet_id=SHEET)
    assert result["ok"] is True
    assert result["filed"] == 1
    assert result["written_back"] == 0
    assert "read-only" in result["write_back_error"]


@pytest.mark.asyncio
async def test_blank_rows_are_skipped() -> None:
    s = FakeSync(["Day", "Time", "Task", "Status"],
                 [["Monday", "19:00", "Real task", ""], ["", "", "", ""], []])
    result = await s.sync(sheet_id=SHEET)
    assert result["filed"] == 1
    assert result["skipped"] == 2


# ── matrix layout: days across the top, time slots down the side ─────────────

MATRIX_HEADER = ["", "DURATION", "TIME", "SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"]
MATRIX_ROWS = [
    ["", "30 mins", "5:00 AM", "Book Reading"] + ["Book Reading"] * 6,
    ["", "90 mins", "5:45AM - 7:15AM"] + ["90 min Deep Block 1"] * 7,
    ["", "45 mins", "7:30AM - 8:15AM"] + ["Daily Bug Bounty Session"] * 7,
    ["", "", "", "", "", "", "", "", "", ""],
]


def test_matrix_layout_is_detected_from_the_header() -> None:
    from src.agents.schedule_sync import detect_day_columns

    cols = detect_day_columns(MATRIX_HEADER)
    assert cols == {
        3: "sunday", 4: "monday", 5: "tuesday", 6: "wednesday",
        7: "thursday", 8: "friday", 9: "saturday",
    }
    assert detect_day_columns(["Day", "Time", "Task"]) == {}


def test_matrix_start_time_is_taken_from_a_range() -> None:
    from src.agents.schedule_sync import flatten_matrix, map_columns, detect_day_columns

    entries = flatten_matrix(
        MATRIX_HEADER, MATRIX_ROWS, detect_day_columns(MATRIX_HEADER), map_columns(MATRIX_HEADER)
    )
    deep = [e for e in entries if e["title"] == "90 min Deep Block 1"]
    assert deep and all(e["time"] == "5:45AM" for e in deep)


@pytest.mark.asyncio
async def test_matrix_sync_files_only_the_requested_day() -> None:
    """A daily template repeats across seven columns. Filing the whole grid
    would put 150+ items a week on the hook."""
    s = FakeSync(MATRIX_HEADER, MATRIX_ROWS)
    result = await s.sync(sheet_id=SHEET, days=["monday"])
    assert result["layout"] == "matrix"
    assert result["filed"] == 3  # three non-blank slots for Monday
    titles = {c.title for c in await repo.list_all()}
    assert titles == {"Book Reading", "90 min Deep Block 1", "Daily Bug Bounty Session"}


@pytest.mark.asyncio
async def test_matrix_resync_of_the_same_day_does_not_duplicate() -> None:
    s = FakeSync(MATRIX_HEADER, MATRIX_ROWS)
    await s.sync(sheet_id=SHEET, days=["monday"])
    await s.sync(sheet_id=SHEET, days=["monday"])
    assert len(await repo.list_all()) == 3


@pytest.mark.asyncio
async def test_the_same_slot_on_two_days_is_two_commitments() -> None:
    """Row 2 column MON and row 2 column TUE are different commitments — the
    row key has to carry the column or they collapse into one."""
    s = FakeSync(MATRIX_HEADER, MATRIX_ROWS)
    await s.sync(sheet_id=SHEET, days=["monday"])
    await s.sync(sheet_id=SHEET, days=["tuesday"])
    assert len(await repo.list_all()) == 6


@pytest.mark.asyncio
async def test_matrix_entries_arrive_proposed_not_open() -> None:
    s = FakeSync(MATRIX_HEADER, MATRIX_ROWS)
    await s.sync(sheet_id=SHEET, days=["monday"])
    assert all(c.status == CommitmentStatus.PROPOSED.value for c in await repo.list_all())


@pytest.mark.asyncio
async def test_matrix_reports_that_write_back_does_not_apply() -> None:
    s = FakeSync(MATRIX_HEADER, MATRIX_ROWS)
    result = await s.sync(sheet_id=SHEET, days=["monday"])
    assert result["written_back"] == 0
    assert "matrix" in result["write_back_error"]
    assert s.writes == []


# ── header detection: real sheets don't start with the header ────────────────

TITLED_SHEET = [
    ["", "Daily Schedule Template"],
    [],
    ["", "DURATION", "TIME", "SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"],
    ["", "30 mins", "5:00 AM"] + ["Book Reading"] * 7,
    ["", "90 mins", "5:45AM - 7:15AM"] + ["90 min Deep Block 1"] * 7,
]


def test_the_header_is_found_below_a_title_row() -> None:
    """Assuming row 1 is the header made a working timetable report zero
    columns and zero day columns."""
    from src.agents.schedule_sync import detect_day_columns, find_header, map_columns

    idx, header = find_header(TITLED_SHEET)
    assert idx == 2
    assert map_columns(header)["time"] == 2
    assert len(detect_day_columns(header)) == 7


def test_a_sheet_that_starts_with_its_header_still_works() -> None:
    from src.agents.schedule_sync import find_header

    idx, header = find_header([["Day", "Time", "Task"], ["Monday", "19:00", "Ship it"]])
    assert idx == 0
    assert header == ["Day", "Time", "Task"]


def test_day_columns_outscore_a_row_of_prose() -> None:
    from src.agents.schedule_sync import score_header

    assert score_header(["", "DURATION", "TIME", "SUN", "MON"]) > score_header(
        ["", "Daily Schedule Template"]
    )


def test_no_recognisable_header_falls_back_to_the_first_row() -> None:
    from src.agents.schedule_sync import find_header

    idx, header = find_header([["alpha", "beta"], ["1", "2"]])
    assert idx == 0
    assert header == ["alpha", "beta"]


@pytest.mark.asyncio
async def test_row_numbers_stay_true_to_the_spreadsheet() -> None:
    """The row key must point at the real sheet row, or a re-sync of a titled
    sheet writes back to the wrong line."""

    class TitledSync(FakeSync):
        async def read_rows(self, sheet_id, sheet_range):
            from src.agents.schedule_sync import find_header

            idx, header = find_header(TITLED_SHEET)
            self._header_offset = idx
            return header, TITLED_SHEET[idx + 1 :], None

    s = TitledSync([], [])
    await s.sync(sheet_id=SHEET, days=["monday"])
    rows = await repo.list_all()
    assert len(rows) == 2
    # Header is sheet row 3, so the first data row is sheet row 4.
    keys = sorted(parse_row_key(r.detail)[1] for r in rows)
    assert keys == [4, 5]
