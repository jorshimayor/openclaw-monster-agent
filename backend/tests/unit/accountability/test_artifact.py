"""The gate the whole accountability feature rests on: what counts as proof."""

from __future__ import annotations

import pytest

from src.core.artifact import MIN_TEXT_ARTIFACT_CHARS, classify, find_url


@pytest.mark.parametrize(
    "text",
    [
        "done",
        "done!",
        "DONE",
        "yes done already",
        "ok",
        "did it",
        "yeah finished, sorted",
        "",
        "   ",
        # Filler repeated past the length threshold must still be rejected —
        # otherwise "done done done done…" closes a commitment.
        "done done done done done done done done done done done done",
    ],
)
def test_bare_acknowledgements_are_rejected(text: str) -> None:
    verdict = classify(text=text)
    assert verdict["accepted"] is False
    assert verdict["kind"] is None
    assert "not proof" in verdict["reason"]


@pytest.mark.parametrize(
    "text,expected_url",
    [
        ("https://github.com/me/repo", "https://github.com/me/repo"),
        ("done — https://x.com/status/1", "https://x.com/status/1"),
        ("shipped it: http://localhost:3000/post.", "http://localhost:3000/post"),
    ],
)
def test_links_are_accepted_and_extracted(text: str, expected_url: str) -> None:
    verdict = classify(text=text)
    assert verdict["accepted"] is True
    assert verdict["kind"] == "link"
    assert verdict["url"] == expected_url


def test_substantial_text_is_accepted() -> None:
    text = "I rewrote the README with an architecture-first section and a decisions table"
    assert len(text) >= MIN_TEXT_ARTIFACT_CHARS
    verdict = classify(text=text)
    assert verdict["accepted"] is True
    assert verdict["kind"] == "text"


def test_attachment_is_accepted_even_with_no_text() -> None:
    verdict = classify(text="", file_url="tg-file:ABC123", file_name="report.pdf")
    assert verdict["accepted"] is True
    assert verdict["kind"] == "file"
    assert verdict["url"] == "tg-file:ABC123"


def test_find_url_returns_none_without_a_url() -> None:
    assert find_url("no links in here at all") is None
