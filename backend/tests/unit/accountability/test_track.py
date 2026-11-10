"""An ordered track advances when you finish something, not when a day passes."""

import pytest

from src.agents import track as track_mod
from src.agents.track import Track, TrackItem, get_track, load_tracks


def test_the_shipped_track_starts_where_he_actually_is():
    t = get_track("rareskills")
    assert t is not None
    assert t.start_at == "proxy-patterns"
    assert t.items[0].key == "proxy-patterns", "the current item must be first"


def test_zk_is_last_because_that_is_the_instruction():
    t = get_track("rareskills")
    assert t.items[-1].key == "zk-book"


def test_every_item_has_a_link_and_a_reason():
    for t in load_tracks():
        for item in t.items:
            assert item.url.startswith("https://"), item.title
            assert item.note, f"{item.title} has no reason to be here"


def test_item_keys_are_unique_so_the_cursor_is_unambiguous():
    for t in load_tracks():
        keys = [i.key for i in t.items]
        assert len(keys) == len(set(keys)), keys


def test_rareskills_opens_the_working_day():
    """The sheet's own Core Rule: Deep Block 1 always prioritises RareSkills.

    Asserted on due times rather than list position. Morning reading is filed
    earlier — it is half an hour of political books before the day starts, not
    work competing with the priorities — so being first in the list stopped
    meaning anything."""
    from src.agents.rotation import load_rotation

    daily = load_rotation()["daily"]
    by_theme = {t["theme"]: t for t in daily}
    work = {k: v for k, v in by_theme.items() if k != "political-reading"}
    earliest = min(work.values(), key=lambda t: t["due_time"])
    assert earliest["theme"] == "rareskills", earliest["theme"]
    assert by_theme["rareskills"]["due_time"] < by_theme["web3-bounty"]["due_time"]
    assert by_theme["political-reading"]["due_time"] < by_theme["rareskills"]["due_time"]


@pytest.mark.asyncio
async def test_one_item_is_filed_at_a_time(monkeypatch):
    """Sixteen commitments is a reading list you archive."""
    monkeypatch.setattr(track_mod, "is_db_available", lambda: False)
    lines = await track_mod.tasks_for("rareskills")
    assert len(lines) == 1
    assert "Proxy patterns" in lines[0]
    assert "1/16" in lines[0]


@pytest.mark.asyncio
async def test_the_line_says_what_is_next(monkeypatch):
    monkeypatch.setattr(track_mod, "is_db_available", lambda: False)
    line = (await track_mod.tasks_for("rareskills"))[0]
    assert "next:" in line


@pytest.mark.asyncio
async def test_an_unknown_track_files_nothing_rather_than_guessing(monkeypatch):
    monkeypatch.setattr(track_mod, "is_db_available", lambda: False)
    assert await track_mod.tasks_for("not-a-track") == []


@pytest.mark.asyncio
async def test_a_cursor_pointing_at_a_removed_item_falls_back_to_the_start(monkeypatch):
    """Renaming an item must not silently restart the whole track."""
    fake = Track(key="t", label="T", due_time="06:00", start_at="b",
                 items=[TrackItem("a", "A", "https://x", "n"),
                        TrackItem("b", "B", "https://x", "n")])
    monkeypatch.setattr(track_mod, "get_track", lambda k: fake)

    class _Row:
        cursor_key = "deleted-item"
        finished_at = None

    async def fake_state(_t):
        return _Row()

    monkeypatch.setattr(track_mod, "_state", fake_state)
    state = await track_mod.current("t")
    assert state["item"]["key"] == "b", "should fall back to the configured start"


def test_a_track_and_its_rotation_entry_agree_on_the_time():
    """Two answers to "when is this due" is how you end up trusting the wrong
    one: the rotation decides when it is filed, the track's own due_time is
    what /api/study/track reports back."""
    from src.agents.rotation import load_rotation
    from src.agents.study_sync import _config_path
    import json

    config = json.loads(_config_path().read_text())
    daily = load_rotation()["daily"]
    for track in config.get("tracks", []):
        entry = next(
            (t for t in daily if t.get("plan") == f"track:{track['key']}"), None
        )
        assert entry is not None, f"{track['key']} has no rotation entry"
        assert track["due_time"] == entry["due_time"], (
            f"{track['key']}: track says {track['due_time']}, "
            f"rotation says {entry['due_time']}"
        )
