"""The shelf: a catalogue, so its job is to be complete and never to crash."""

import json

import pytest

from src.agents import library


@pytest.fixture
def shelf_from(tmp_path, monkeypatch):
    def build(payload):
        path = tmp_path / "library.json"
        path.write_text(json.dumps(payload))
        monkeypatch.setenv("LIBRARY_PATH", str(path))
        return library.shelf()

    return build


def section(items):
    return {
        "enabled": True,
        "prices_verified": "2026-10-28",
        "sections": [
            {"key": "courses", "label": "Courses", "blurb": "b",
             "groups": [{"key": "g", "label": "G", "items": items}]}
        ],
    }


def test_a_complete_item_survives_with_its_price_and_note(shelf_from):
    out = shelf_from(section([
        {"title": "Cyfrin Updraft", "url": "https://updraft.cyfrin.io/",
         "price": "Free", "note": "do it with Foundry open"}
    ]))
    item = out["sections"][0]["groups"][0]["items"][0]
    assert item["title"] == "Cyfrin Updraft"
    assert item["price"] == "Free"
    assert item["note"] == "do it with Foundry open"
    assert out["total"] == 1


def test_an_item_with_no_url_is_dropped_rather_than_rendered_empty(shelf_from):
    """A catalogue with holes in it stops being trusted."""
    out = shelf_from(section([
        {"title": "Half written"},
        {"title": "Real", "url": "https://x.dev"},
    ]))
    assert [i["title"] for i in out["sections"][0]["groups"][0]["items"]] == ["Real"]
    assert out["total"] == 1


def test_an_empty_group_does_not_leave_an_empty_card(shelf_from):
    out = shelf_from(section([{"title": "no url"}]))
    assert out["sections"] == []
    assert out["total"] == 0


def test_blank_price_and_note_become_null_not_empty_strings(shelf_from):
    out = shelf_from(section([{"title": "T", "url": "https://x.dev", "price": "  "}]))
    item = out["sections"][0]["groups"][0]["items"][0]
    assert item["price"] is None and item["note"] is None


def test_counts_are_per_section_and_total(shelf_from):
    out = shelf_from({
        "enabled": True,
        "sections": [
            {"key": "a", "label": "A", "groups": [
                {"key": "g1", "label": "G1", "items": [
                    {"title": "1", "url": "https://a"}, {"title": "2", "url": "https://b"}]},
                {"key": "g2", "label": "G2", "items": [{"title": "3", "url": "https://c"}]},
            ]},
        ],
    })
    assert out["sections"][0]["count"] == 3
    assert out["total"] == 3


def test_a_missing_file_is_an_empty_shelf_not_an_exception(tmp_path, monkeypatch):
    monkeypatch.setenv("LIBRARY_PATH", str(tmp_path / "nope.json"))
    assert library.shelf() == {"enabled": False, "sections": [], "total": 0}


def test_broken_json_is_an_empty_shelf_not_an_exception(tmp_path, monkeypatch):
    path = tmp_path / "library.json"
    path.write_text("{ not json")
    monkeypatch.setenv("LIBRARY_PATH", str(path))
    assert library.shelf()["sections"] == []


# --- the shipped file ------------------------------------------------------

def test_the_real_shelf_loads_and_every_item_is_complete():
    out = library.shelf()
    assert out["enabled"] and out["total"] > 20
    for s in out["sections"]:
        for g in s["groups"]:
            for item in g["items"]:
                assert item["title"] and item["url"].startswith("http"), item


def test_the_sections_the_page_expects_are_all_present():
    keys = {s["key"] for s in library.shelf()["sections"]}
    assert {"certifications", "courses", "articles", "newsletters", "videos"} <= keys


def test_every_certification_carries_a_price_and_an_official_link():
    """A certification without a price is the thing this page exists to fix."""
    certs = next(s for s in library.shelf()["sections"] if s["key"] == "certifications")
    for group in certs["groups"]:
        for item in group["items"]:
            assert item["price"], f"{item['title']} has no price"
            assert item["note"], f"{item['title']} has no note"


def test_the_architect_track_covers_the_three_clouds():
    certs = next(s for s in library.shelf()["sections"] if s["key"] == "certifications")
    group = next(g for g in certs["groups"] if g["key"] == "solutions-architect")
    titles = " ".join(i["title"] for i in group["items"]).lower()
    for cloud in ("aws", "azure", "google"):
        assert cloud in titles
