"""The escalation ladder — reminders get closer together and louder, and the
schedule never stops on its own."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.agents.nagger import compose_nag, ladder_for
from src.models.commitment import CommitmentDB


def _commitment(nag_count: int = 0, hours_overdue: int = 2) -> CommitmentDB:
    return CommitmentDB(
        title="Rewrite the chelsea_bot README for a hiring manager",
        detail=None,
        status="open",
        due_at=datetime.now(timezone.utc) - timedelta(hours=hours_overdue),
        nag_count=nag_count,
    )


def test_intervals_shrink_monotonically_as_reminders_are_ignored() -> None:
    intervals = [ladder_for(n)["interval"] for n in range(0, 20)]
    assert all(b <= a for a, b in zip(intervals, intervals[1:])), intervals
    assert intervals[0] == 1800
    assert intervals[-1] == 600


def test_ladder_never_disables_itself() -> None:
    """No miss count produces a zero/negative interval — the chase is endless
    by design; only an artifact ends it."""
    for n in (0, 5, 50, 5000):
        assert ladder_for(n)["interval"] >= 600


def test_tier_escalates_to_p0_and_finally_reaches_slack() -> None:
    assert ladder_for(0)["tier"] == "P1"
    assert ladder_for(3)["tier"] == "P1"
    assert ladder_for(4)["tier"] == "P0"
    assert ladder_for(11)["slack"] is False
    assert ladder_for(12)["slack"] is True


def test_escalation_index_is_non_decreasing() -> None:
    levels = [ladder_for(n)["escalation"] for n in range(0, 20)]
    assert levels == sorted(levels)
    assert levels[0] == 0
    assert levels[-1] == len({0, 2, 4, 7, 12}) - 1


@pytest.mark.parametrize("nag_count", [0, 2, 5, 9, 15])
def test_every_reminder_states_the_artifact_requirement(nag_count: int) -> None:
    text = compose_nag(_commitment(nag_count=nag_count), nag_count, "P1")
    assert "/done" in text
    assert "artifact" in text.lower()
    assert "/drop" in text
    assert f"reminder #{nag_count + 1}".lower() in text.lower() or nag_count < 2


def test_reminder_reports_how_overdue_the_commitment_is() -> None:
    text = compose_nag(_commitment(nag_count=1, hours_overdue=5), 1, "P1")
    assert "5h overdue" in text
