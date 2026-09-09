"""Regression tests for the extraction failure that filed ten junk commitments.

A one-line reminder ("pick Ibrahim up at 1:30 pm") produced ten rows scraped
from the pipeline's own scaffolding — "Estimated effort: < 5 min", "CalendarAgent
Prompt", "Start time is 2026-08-26 13:30 WAT" — all due at the wrong time.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.agents.commitment_extractor import (
    clean_items,
    extract_items,
    looks_like_scaffolding,
    parse_clock,
    parse_markdown_plan,
    resolve_due,
    single_item_from_request,
)

# The exact report shape that caused the incident.
SCAFFOLDING_REPORT = """# Final Synthesized Report

**Task**: Remind me to pick Ibrahim up at Penthoush estate by 1:30 pm WAT

# 1. Task Complexity Assessment
- **Scope**: 1 x reminder (pick-up at a specific location and time).
- **Dependencies**: None beyond a calendar/notification service.
- **Risk**: Minimal - only time-zone mis-calculation or event not created.
- **Estimated effort**: < 5 min (human + agent).

# 2. Pattern Match
- **Pattern**: `WorkflowPattern.GENERIC` - a single-step, low-risk automation.
- **Justification**: The task is a straightforward event creation.

# 4. Team Assembly (waves of agents + tools)

| Wave | Agent | Tool | Purpose | Owner |
|------|-------|------|---------|-------|
| 1 | **CalendarAgent** | `create_event()` | Create the event. | ORCHESTRATOR |

# 5. Prompt Injection Strategy
- **CalendarAgent Prompt**
  ```json
  {"title": "Pick up Ibrahim", "start_time": "2026-08-26T13:30:00+01:00"}
  ```
- **VerificationAgent Prompt**

# 7. Verifier Criteria
- Event title matches `"Pick up Ibrahim"`.
- Start time is `2026-08-26 13:30 WAT`.
"""

JUNK_TITLES = [
    "Scope: 1 x reminder (pick-up at a specific location and time).",
    "Dependencies: None beyond a calendar/notification service.",
    "Risk: Minimal - only time-zone mis-calculation or event not created.",
    "Estimated effort: < 5 min (human + agent).",
    "Pattern: WorkflowPattern.GENERIC - a single-step, low-risk automation.",
    "Justification: The task is a straightforward event creation.",
    "CalendarAgent Prompt",
    "VerificationAgent Prompt",
    'Event title matches "Pick up Ibrahim".',
    "Start time is 2026-08-26 13:30 WAT.",
    "Wave 1: send create_event",
    '{"title": "Pick up Ibrahim"}',
]


@pytest.mark.parametrize("title", JUNK_TITLES)
def test_pipeline_scaffolding_is_rejected(title: str) -> None:
    assert looks_like_scaffolding(title) is True, title


@pytest.mark.parametrize(
    "title",
    [
        "Rewrite the chelsea_bot README for a hiring manager",
        "Publish the X post and lead with one surprising number",
        "Pick Ibrahim up at Penthoush estate",
        "Ask three people for feedback on the writeup",
    ],
)
def test_real_action_items_survive(title: str) -> None:
    assert looks_like_scaffolding(title) is False, title


def test_markdown_fallback_refuses_reports_without_day_headings() -> None:
    """The core fix: no weekday headings means this is not a day-by-day plan,
    so the bullet scraper must not run at all."""
    assert parse_markdown_plan(SCAFFOLDING_REPORT) == []


def test_markdown_fallback_still_handles_a_real_weekly_plan() -> None:
    plan = """**Monday, August 24**

- **Evening**: Start drafting the BUILD task.

**Thursday, August 27**

- **Evening**: Draft the X post.
"""
    items = parse_markdown_plan(plan)
    assert [i["day"] for i in items] == ["monday", "thursday"]
    assert all(i["time_of_day"] == "evening" for i in items)


@pytest.mark.asyncio
async def test_the_original_request_yields_exactly_one_commitment() -> None:
    """End to end, with no LLM — the fallback chain must not regress to ten."""
    items = await extract_items(
        "Remind me to pick Ibrahim up at Penthoush estate by 1:30 pm WAT",
        SCAFFOLDING_REPORT,
        llm=None,
    )
    assert len(items) == 1
    assert "Ibrahim" in items[0]["title"]
    assert items[0]["at_time"] == "13:30"
    assert not looks_like_scaffolding(items[0]["title"])


@pytest.mark.parametrize(
    "text,expected",
    [
        ("by 1:30 pm WAT", "13:30"),
        ("at 9am", "09:00"),
        ("13:30", "13:30"),
        ("12:15 am", "00:15"),
        ("12:15 pm", "12:15"),
        ("by 5", None),          # too ambiguous to guess
        ("half past four", None),
        ("", None),
    ],
)
def test_clock_parsing(text: str, expected) -> None:
    assert parse_clock(text) == expected


def test_explicit_clock_time_is_honoured_not_defaulted_to_evening() -> None:
    """All ten junk rows landed at 18:00 UTC because clock times were ignored."""
    now_local = datetime(2026, 8, 26, 10, 0, tzinfo=timezone.utc)
    due = resolve_due("today", "", "13:30", now_local=now_local)
    assert (due.hour, due.minute) == (12, 30)  # 13:30 WAT (UTC+1)


def test_a_missed_explicit_time_stays_today_so_it_nags_immediately() -> None:
    now_local = datetime(2026, 8, 26, 18, 0, tzinfo=timezone.utc)
    due = resolve_due("today", "", "13:30", now_local=now_local)
    assert due.day == 26  # not rolled to tomorrow


def test_fuzzy_slot_with_no_clock_time_still_rolls_forward() -> None:
    now_local = datetime(2026, 8, 26, 22, 0, tzinfo=timezone.utc)
    due = resolve_due("today", "evening", "", now_local=now_local)
    assert due > (now_local - timedelta(hours=1))


def test_clean_items_dedupes_and_caps() -> None:
    raw = [{"title": f"Do the thing number {i}"} for i in range(20)]
    raw += [{"title": "Do the thing number 0"}]  # duplicate
    out = clean_items(raw, max_items=10)
    assert len(out) == 10
    assert len({i["title"] for i in out}) == 10


def test_single_item_from_request_reads_a_plain_reminder() -> None:
    items = single_item_from_request("Remind me to pick Ibrahim up at Penthoush estate by 1:30 pm WAT")
    assert len(items) == 1
    assert items[0]["at_time"] == "13:30"
    assert items[0]["day"] == "today"
    assert "1:30" not in items[0]["title"]  # time phrase stripped from the title


def test_single_item_ignores_things_that_are_not_reminders() -> None:
    assert single_item_from_request("Research the Solana memecoin market for Q3") == []


# ── the request is not a to-do item ──────────────────────────────────────────

DIGEST_REQUEST = (
    "Weekly market research digest: write a scannable digest for a reader in Lagos "
    "covering global markets, Nigerian markets, crypto, and three things to watch next week"
)


@pytest.mark.parametrize(
    "title",
    [
        "Write a scannable market research digest for Lagos readers",
        "Cover global markets, Nigerian markets with FX pointers, crypto, and three things to watch",
        "Write the weekly market research digest",
    ],
)
def test_the_task_itself_is_never_filed_as_a_user_commitment(title: str) -> None:
    """This produced 83 pinned reminders chasing the user to do the assistant's
    own job. The report IS the deliverable; it is not homework."""
    from src.agents.commitment_extractor import restates_the_request

    assert restates_the_request(title, DIGEST_REQUEST) is True


@pytest.mark.parametrize(
    "title",
    [
        "Check ngxgroup.com for the current NGX figures",
        "Post the digest to your X account on Monday",
        "Ask three people for feedback on the writeup",
    ],
)
def test_genuine_follow_up_actions_survive(title: str) -> None:
    from src.agents.commitment_extractor import restates_the_request

    assert restates_the_request(title, DIGEST_REQUEST) is False


def test_clean_items_drops_restatements_when_given_the_description() -> None:
    from src.agents.commitment_extractor import clean_items

    items = [
        {"title": "Write a scannable market research digest for Lagos readers"},
        {"title": "Check ngxgroup.com for the current NGX figures"},
    ]
    kept = clean_items(items, max_items=10, description=DIGEST_REQUEST)
    assert [i["title"] for i in kept] == ["Check ngxgroup.com for the current NGX figures"]
