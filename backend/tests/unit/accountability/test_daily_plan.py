"""Pairing what to study with the block to study it in."""

from datetime import date

import asyncio

from src.agents.daily_plan import attach as _attach, split_resource
from src.agents.rotation import runs_on


def attach(*a, **kw):
    """attach is async now — the day route awaits an ordered track rather than
    letting rotation hand it to a thread with its own event loop."""
    return asyncio.run(_attach(*a, **kw))


def block(start, end, label):
    return {"start": start, "end": end, "label": label, "minutes": 60}


def theme(label, block_label="", due="09:00", tasks=(), base="t"):
    return {"label": label, "theme": base, "base": base, "block": block_label,
            "due_time": due, "tasks": list(tasks)}


# --- the resource behind a task -------------------------------------------

def test_a_task_is_split_into_the_instruction_and_its_link():
    out = split_resource("One chapter, typed out — https://move-book.com/")
    assert out["text"] == "One chapter, typed out"
    assert out["url"] == "https://move-book.com/"


def test_a_task_with_no_link_keeps_all_its_words():
    out = split_resource("Explain from memory why the fix works")
    assert out["url"] is None
    assert out["text"] == "Explain from memory why the fix works"


def test_trailing_punctuation_is_not_part_of_the_url():
    assert split_resource("see https://x.dev/a).")["url"] == "https://x.dev/a"


# --- which block a theme lands in -----------------------------------------

BLOCKS = [
    ("05:00", "05:30", "Book Reading"),
    ("05:30", "05:45", "Morning Tea"),
    ("05:45", "07:15", "90 min Deep Block 1"),
    ("09:00", "09:15", "Breakfast"),
    ("09:15", "10:45", "90 min Deep Block 2"),
]


def fresh():
    return [block(*b) for b in BLOCKS]


def test_a_theme_goes_in_the_block_it_names():
    blocks = attach(
        date(2026, 10, 28), fresh(),
        themes={"daily": [theme("RareSkills", "90 min Deep Block 1", tasks=["Proxy patterns — https://rareskills.io/proxy-patterns"])], "cycled": None},
        fellowship={},
    )
    deep_one = next(b for b in blocks if "Deep Block 1" in b["label"])
    assert [p["label"] for p in deep_one["plan"]] == ["RareSkills"]
    assert deep_one["plan"][0]["items"][0]["url"] == "https://rareskills.io/proxy-patterns"


def test_the_label_wins_over_the_clock():
    """Pairing on due_time alone put RareSkills in Morning Tea."""
    blocks = attach(
        date(2026, 10, 28), fresh(),
        themes={"daily": [theme("RareSkills", "90 min Deep Block 1", due="05:30")], "cycled": None},
        fellowship={},
    )
    assert next(b for b in blocks if b["label"] == "Morning Tea")["plan"] == []
    assert next(b for b in blocks if "Deep Block 1" in b["label"])["plan"]


def test_a_theme_with_no_block_falls_back_to_its_due_time():
    """A renamed row in the sheet must not make work vanish."""
    blocks = attach(
        date(2026, 10, 28), fresh(),
        themes={"daily": [theme("Something", "", due="09:30")], "cycled": None},
        fellowship={},
    )
    assert next(b for b in blocks if "Deep Block 2" in b["label"])["plan"]


def test_blocks_with_nothing_scheduled_get_an_empty_plan_not_a_missing_one():
    blocks = attach(date(2026, 10, 28), fresh(), themes={"daily": [], "cycled": None}, fellowship={})
    assert all(b["plan"] == [] for b in blocks)


def test_two_strands_can_share_one_block():
    blocks = attach(
        date(2026, 10, 28), fresh(),
        themes={
            "daily": [theme("Web3 study", "90 min Deep Block 2", base="a")],
            "cycled": theme("Web2 / systems", "90 min Deep Block 2", base="b"),
        },
        fellowship={},
    )
    deep_two = next(b for b in blocks if "Deep Block 2" in b["label"])
    assert [p["label"] for p in deep_two["plan"]] == ["Web3 study", "Web2 / systems"]


def test_the_weeks_paper_goes_on_the_fellowship_block():
    """`reading` is {title, cite, url}; stringifying it printed a Python dict.

    It lands on whichever block the rotation gives the fellowship — it used to
    be hardcoded to "book reading", which went wrong the morning that half
    hour became political reading."""
    blocks = attach(
        date(2026, 10, 28), fresh(),
        themes={"daily": [{**theme("Flow fellowship", "Book Reading"),
                           "base": "flow-fellowship", "theme": "flow-fellowship"}],
                "cycled": None},
        fellowship={"enabled": True, "started": True, "week": 6,
                    "reading": {"title": "Toolformer", "cite": "Schick et al., 2023",
                                "url": "https://arxiv.org/abs/2302.04761"}},
    )
    plan = next(b for b in blocks if b["label"] == "Book Reading")["plan"]
    entry = next(p for p in plan if p["kind"] == "fellowship")
    assert entry["items"][0]["text"] == "Toolformer (Schick et al., 2023)"
    assert entry["items"][0]["url"] == "https://arxiv.org/abs/2302.04761"
    assert "{" not in entry["items"][0]["text"]


def test_nothing_is_filed_before_the_fellowship_starts():
    blocks = attach(
        date(2026, 10, 28), fresh(),
        themes={"daily": [{**theme("Flow fellowship", "Book Reading"),
                           "base": "flow-fellowship", "theme": "flow-fellowship"}],
                "cycled": None},
        fellowship={"enabled": True, "started": False, "week": 0, "reading": {"title": "x"}},
    )
    # The theme itself still gives the block a strand; what must not appear is
    # anything derived from a programme that has not begun.
    kinds = [p["kind"] for b in blocks for p in b["plan"]]
    assert "fellowship" not in kinds and "weekly" not in kinds, kinds


# --- the weekly cadence ----------------------------------------------------

def test_a_theme_with_no_days_runs_every_day():
    """The two priorities carry no `days` and must not be gated."""
    for n in range(7):
        assert runs_on({}, date(2026, 11, 2 + n))


def test_a_theme_runs_only_on_the_days_it_names():
    monday, tuesday = date(2026, 11, 2), date(2026, 11, 3)
    assert runs_on({"days": ["monday", "wednesday", "friday"]}, monday)
    assert not runs_on({"days": ["monday", "wednesday", "friday"]}, tuesday)


def test_weekday_names_are_accepted_short_or_long_and_any_case():
    monday = date(2026, 11, 2)
    assert runs_on({"days": ["Mon"]}, monday)
    assert runs_on({"days": ["MONDAY"]}, monday)


# --- a hook that came back empty ------------------------------------------

def test_a_hooked_theme_that_loaded_nothing_says_so():
    """RareSkills is filled from a cursor in Postgres. When that store is
    unreachable the theme arrives with no tasks, and a bare heading would make
    an unscheduled block and a broken one look identical."""
    blocks = attach(
        date(2026, 10, 28), fresh(),
        themes={"daily": [{**theme("RareSkills", "90 min Deep Block 1"),
                           "plan": "track:no-such-track", "tasks": []}], "cycled": None},
        fellowship={},
    )
    entry = next(b for b in blocks if "Deep Block 1" in b["label"])["plan"][0]
    assert entry["unavailable"] is True
    assert "could not" in entry["items"][0]["text"].lower()


def test_a_theme_with_no_hook_and_no_tasks_is_just_empty():
    """Only a hook can fail. A theme that simply has nothing today is not a
    fault and must not be dressed up as one."""
    blocks = attach(
        date(2026, 10, 28), fresh(),
        themes={"daily": [theme("Quiet", "90 min Deep Block 1")], "cycled": None},
        fellowship={},
    )
    entry = next(b for b in blocks if "Deep Block 1" in b["label"])["plan"][0]
    assert "unavailable" not in entry
    assert entry["items"] == []


def test_a_hook_that_did_load_is_untouched():
    blocks = attach(
        date(2026, 10, 28), fresh(),
        themes={"daily": [{**theme("RareSkills", "90 min Deep Block 1",
                                   tasks=["Proxy patterns — https://rareskills.io/x"]),
                           "plan": "track:rareskills"}], "cycled": None},
        fellowship={},
    )
    entry = next(b for b in blocks if "Deep Block 1" in b["label"])["plan"][0]
    assert "unavailable" not in entry
    assert entry["items"][0]["url"] == "https://rareskills.io/x"


def test_attaching_twice_does_not_double_the_plan():
    """Blocks that already carry a plan must be re-planned, not appended to."""
    args = dict(
        themes={"daily": [theme("RareSkills", "90 min Deep Block 1",
                                tasks=["Proxy patterns — https://x.dev"])], "cycled": None},
        fellowship={},
    )
    blocks = attach(date(2026, 10, 28), fresh(), **args)
    blocks = attach(date(2026, 10, 28), blocks, **args)
    deep_one = next(b for b in blocks if "Deep Block 1" in b["label"])
    assert len(deep_one["plan"]) == 1
    assert len(deep_one["plan"][0]["items"]) == 1


def test_a_track_plan_is_awaited_rather_than_threaded():
    """rotation._expand_track hands the work to a thread with its own event
    loop. The database engine belongs to the request's loop, so that query
    raises and the theme arrives empty — which rendered "could not load" on a
    block while /api/study/track answered the same question fine. This route
    is async and awaits instead."""
    blocks = attach(
        date(2026, 10, 28), fresh(),
        themes={"daily": [{**theme("RareSkills", "90 min Deep Block 1"),
                           "plan": "track:rareskills", "tasks": []}], "cycled": None},
        fellowship={},
    )
    entry = next(b for b in blocks if "Deep Block 1" in b["label"])["plan"][0]
    assert "unavailable" not in entry, entry
    assert entry["items"], "the track resolved to nothing"
    assert "RareSkills" in entry["items"][0]["text"]


def test_tasks_already_present_are_not_replaced_by_the_track():
    """Only an empty hook is backfilled; a theme that already carries its
    tasks must be left exactly as the rotation resolved it."""
    blocks = attach(
        date(2026, 10, 28), fresh(),
        themes={"daily": [{**theme("RareSkills", "90 min Deep Block 1",
                                   tasks=["Already resolved — https://x.dev"]),
                           "plan": "track:rareskills"}], "cycled": None},
        fellowship={},
    )
    entry = next(b for b in blocks if "Deep Block 1" in b["label"])["plan"][0]
    assert [i["text"] for i in entry["items"]] == ["Already resolved"]
