"""Sleep, and refusing to lose data quietly."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.agents import nagger
from src.agents.nagger import in_quiet_hours, quiet_until
from src.core import commitment_repo as repo
from src.core.commitment_repo import StorageUnavailable
from src.models.commitment import CommitmentStatus


def _utc_for_local(hour: int, minute: int = 30, offset: int = 1) -> datetime:
    """A UTC instant whose local wall clock is `hour:minute`."""
    return datetime(2026, 8, 27, hour, minute, tzinfo=timezone.utc) - timedelta(hours=offset)


# ── quiet hours ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize("hour", [22, 23, 0, 3, 5, 6])
def test_asleep_between_ten_and_seven(hour: int) -> None:
    assert in_quiet_hours(_utc_for_local(hour)) is True


@pytest.mark.parametrize("hour", [7, 8, 12, 17, 20, 21])
def test_awake_outside_the_window(hour: int) -> None:
    assert in_quiet_hours(_utc_for_local(hour)) is False


def test_the_window_wraps_midnight() -> None:
    """22:00→07:00 is two ranges, not one comparison. A naive
    `start <= hour < end` is false for every hour of this window."""
    assert in_quiet_hours(_utc_for_local(23)) is True
    assert in_quiet_hours(_utc_for_local(1)) is True
    assert in_quiet_hours(_utc_for_local(12)) is False


def test_quiet_until_points_at_the_next_seven_am() -> None:
    resume = quiet_until(_utc_for_local(23))
    assert resume is not None
    local_resume = resume + timedelta(hours=1)
    assert (local_resume.hour, local_resume.minute) == (7, 0)
    assert resume > _utc_for_local(23)


def test_quiet_until_is_none_while_awake() -> None:
    assert quiet_until(_utc_for_local(12)) is None


def test_disabling_quiet_hours_turns_it_off(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.core.config import get_settings

    s = get_settings()
    monkeypatch.setattr(s, "quiet_hours_enabled", False)
    assert in_quiet_hours(_utc_for_local(3)) is False


@pytest.mark.asyncio
async def test_a_tick_at_night_sends_nothing_and_does_not_advance_the_ladder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The important half: a suppressed reminder must not count as a reminder,
    or the ladder climbs all night and 7am opens with "REMINDER #40"."""
    row = await repo.create(
        title="Ship the README",
        due_at=datetime.now(timezone.utc) - timedelta(hours=2),
        status=CommitmentStatus.OPEN.value,
    )
    monkeypatch.setattr(nagger, "in_quiet_hours", lambda now=None: True)
    monkeypatch.setattr(nagger, "quiet_until", lambda now=None: datetime.now(timezone.utc))

    sent = []
    engine = nagger.NagEngine()
    monkeypatch.setattr(engine, "_telegram", lambda *a, **k: sent.append(a) or {"ok": True})

    result = await engine.tick()
    assert result["quiet_hours"] is True
    assert result["sent"] == 0
    assert result["deferred"] == 1
    assert sent == []

    after = await repo.get(row.id)
    assert after.nag_count == 0
    assert after.last_nagged_at is None


@pytest.mark.asyncio
async def test_the_deferred_reminder_fires_once_the_window_ends(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await repo.create(
        title="Ship the README",
        due_at=datetime.now(timezone.utc) - timedelta(hours=2),
        status=CommitmentStatus.OPEN.value,
    )
    monkeypatch.setattr(nagger, "in_quiet_hours", lambda now=None: False)

    engine = nagger.NagEngine()
    calls = []

    async def _fake_telegram(text, pin, silent):
        calls.append(text)
        return {"ok": True}

    monkeypatch.setattr(engine, "_telegram", _fake_telegram)
    result = await engine.tick()
    assert result["sent"] == 1
    assert calls and "Ship the README" in calls[0]


@pytest.mark.asyncio
async def test_poke_me_now_ignores_quiet_hours(monkeypatch: pytest.MonkeyPatch) -> None:
    """Quiet hours stop the schedule, not an explicit request."""
    row = await repo.create(
        title="Ship the README",
        due_at=datetime.now(timezone.utc),
        status=CommitmentStatus.OPEN.value,
    )
    monkeypatch.setattr(nagger, "in_quiet_hours", lambda now=None: True)

    engine = nagger.NagEngine()
    calls = []

    async def _fake_telegram(text, pin, silent):
        calls.append(text)
        return {"ok": True}

    monkeypatch.setattr(engine, "_telegram", _fake_telegram)
    await engine.nag_one(await repo.get(row.id))
    assert len(calls) == 1


# ── storage guard ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_writing_is_refused_when_the_database_is_configured_but_down(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The bug this prevents: a commitment written to process memory nagged the
    user until the container restarted, then vanished with no trace."""
    monkeypatch.setattr(repo, "memory_fallback_allowed", lambda: False)
    monkeypatch.setattr(repo, "is_db_available", lambda: False)

    with pytest.raises(StorageUnavailable) as err:
        await repo.create(title="Would vanish on restart", due_at=datetime.now(timezone.utc))
    assert "DATABASE_URL is configured" in str(err.value)


@pytest.mark.asyncio
async def test_updates_are_refused_too(monkeypatch: pytest.MonkeyPatch) -> None:
    row = await repo.create(title="Ship it", due_at=datetime.now(timezone.utc))
    monkeypatch.setattr(repo, "memory_fallback_allowed", lambda: False)
    monkeypatch.setattr(repo, "is_db_available", lambda: False)
    with pytest.raises(StorageUnavailable):
        await repo._mutate(row.id, title="changed")


@pytest.mark.asyncio
async def test_local_dev_with_no_database_still_works(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(repo, "memory_fallback_allowed", lambda: True)
    monkeypatch.setattr(repo, "is_db_available", lambda: False)
    row = await repo.create(title="Local only", due_at=datetime.now(timezone.utc))
    assert row is not None
    assert (await repo.get(row.id)).title == "Local only"


def test_fallback_is_allowed_only_when_no_database_is_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.core.config import get_settings

    from .conftest import REAL_MEMORY_FALLBACK_ALLOWED as real

    settings = get_settings()
    monkeypatch.setattr(settings, "database_url", "postgresql://host/db")
    assert real() is False

    monkeypatch.setattr(settings, "database_url", "")
    assert real() is True
