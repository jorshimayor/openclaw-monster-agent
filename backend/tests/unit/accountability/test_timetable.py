"""Turning timetable rows into blocks that can be drawn.

Every case here came from the real sheet.
"""

from src.agents.timetable import add_ends, fix_meridiem, parse_duration, shape


def row(start, label, duration=""):
    return {"start": start, "label": label, "duration": duration, "raw_time": ""}


# --- durations -----------------------------------------------------------

def test_durations_the_sheet_actually_uses():
    assert parse_duration("30 mins") == 30
    assert parse_duration("15 mins") == 15
    assert parse_duration("90 mins") == 90
    assert parse_duration("1 hour") == 60
    assert parse_duration("75 mins") == 75


def test_an_unparsable_duration_is_none_rather_than_zero():
    """Zero would draw a block with no height; None lets the caller infer."""
    assert parse_duration("") is None
    assert parse_duration("a while") is None


# --- the PM that meant AM -------------------------------------------------

def test_a_morning_break_written_as_pm_is_corrected():
    """The sheet says 10:45 PM for a break between a 10:45 end and an 11:00
    start. Row order is the evidence; only AM keeps it."""
    blocks = fix_meridiem([
        row("09:00", "Deep Block 2", "90 mins"),
        row("22:45", "Break", "15 mins"),
        row("11:00", "Study", "1 hour"),
    ])
    assert blocks[1]["start"] == "10:45"
    assert blocks[1]["meridiem_corrected"] is True


def test_a_genuinely_late_block_is_left_alone():
    """Last row, in order — nothing to correct."""
    blocks = fix_meridiem([
        row("19:45", "Wind-down", "45 mins"),
        row("22:45", "Late read", "15 mins"),
    ])
    assert blocks[1]["start"] == "22:45"
    assert "meridiem_corrected" not in blocks[1]


def test_it_does_not_flip_when_flipping_would_not_help():
    blocks = fix_meridiem([row("09:00", "A"), row("08:00", "B"), row("08:30", "C")])
    assert blocks[1]["start"] in ("08:00", "20:00")


# --- ends and overlaps ----------------------------------------------------

def test_every_block_gets_an_end():
    """Without one the page cannot draw a timeline, which was the whole bug."""
    for b in add_ends([row("05:00", "Book Reading", "30 mins")]):
        assert b["end"] == "05:30" and b["minutes"] == 30


def test_two_blocks_at_the_same_time_stop_overlapping():
    """Breakfast and Deep Block 2 are both written 09:00; the durations say
    breakfast is fifteen minutes and the block follows it."""
    out = add_ends([row("09:00", "Breakfast", "15 mins"),
                    row("09:00", "Deep Block 2", "90 mins")])
    assert out[0]["start"] == "09:00" and out[0]["end"] == "09:15"
    assert out[1]["start"] == "09:15" and out[1]["end"] == "10:45"
    assert out[1]["shifted"] is True


def test_a_block_with_no_duration_runs_until_the_next_one():
    out = add_ends([row("09:00", "Mystery"), row("10:00", "Next", "30 mins")])
    assert out[0]["end"] == "10:00"
    assert out[0]["duration_inferred"] is True


def test_blocks_come_back_in_order():
    out = add_ends([row("12:00", "Lunch", "1 hour"), row("05:00", "Read", "30 mins")])
    assert [b["label"] for b in out] == ["Read", "Lunch"]


# --- the whole sheet ------------------------------------------------------

REAL = [
    ("05:00", "Book Reading", "30 mins"), ("05:30", "Morning Tea", "15 mins"),
    ("05:45", "Deep Block 1", "90 mins"), ("07:15", "Stretch", "15 mins"),
    ("07:30", "Bug Bounty", "45 mins"), ("08:15", "Morning Walk", "45 mins"),
    ("09:00", "Breakfast", "15 mins"), ("09:00", "Deep Block 2", "90 mins"),
    ("22:45", "Break", "15 mins"), ("11:00", "Study", "1 hour"),
]


def test_the_real_sheet_produces_a_day_with_no_overlaps():
    out = shape([row(*r) for r in REAL])
    for earlier, later in zip(out, out[1:]):
        assert earlier["end"] <= later["start"], f"{earlier['label']} overruns {later['label']}"


def test_the_real_sheet_has_no_gaps_through_the_morning():
    out = shape([row(*r) for r in REAL])
    for earlier, later in zip(out, out[1:]):
        assert earlier["end"] == later["start"], f"gap after {earlier['label']}"
