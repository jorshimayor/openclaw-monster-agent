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


def test_it_files_before_the_rest_of_the_morning():
    """It is meant to open the day, so it has to be due before web3-bounty."""
    from src.agents.rotation import load_rotation

    daily = load_rotation()["daily"]
    by_theme = {t["theme"]: t for t in daily}
    assert by_theme["rareskills"]["due_time"] < by_theme["web3-bounty"]["due_time"]
    assert daily[0]["theme"] == "rareskills"


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
