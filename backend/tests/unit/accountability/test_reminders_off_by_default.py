"""Reminders are off unless someone asks for them.

Deliberately outside the package fixture that switches the engine on: these
assert what actually ships, so they clear the override rather than inherit it.
"""

from datetime import datetime, timedelta, timezone

import pytest

from src.core import commitment_repo as repo
from src.core import config


@pytest.fixture(autouse=True)
def shipped_defaults(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("NAG_ENABLED", raising=False)
    config.get_settings.cache_clear()
    yield
    config.get_settings.cache_clear()


def test_the_engine_ships_switched_off():
    assert config.get_settings().nag_enabled is False


@pytest.mark.asyncio
async def test_nothing_is_ever_due_for_a_reminder():
    await repo.create(
        title="Proxy patterns",
        due_at=datetime.now(timezone.utc) - timedelta(hours=2),
        source="rareskills",
    )
    assert await repo.due_for_nag() == []


@pytest.mark.asyncio
async def test_no_wake_is_booked_for_a_container_that_would_send_nothing():
    """next_nag_at drives the Durable Object alarm. A time here would buy a
    container start whose only outcome is finding the engine switched off."""
    await repo.create(
        title="Proxy patterns",
        due_at=datetime.now(timezone.utc) - timedelta(hours=2),
        source="rareskills",
    )
    assert await repo.next_nag_at() is None


@pytest.mark.asyncio
async def test_a_tick_sends_nothing_and_says_so():
    from src.agents.nagger import NagEngine

    assert (await NagEngine().tick()) == {"enabled": False, "sent": 0}


def test_turning_it_back_on_is_one_environment_variable(monkeypatch):
    """Disabled, not deleted — the decision has to stay reversible."""
    monkeypatch.setenv("NAG_ENABLED", "true")
    config.get_settings.cache_clear()
    assert config.get_settings().nag_enabled is True
