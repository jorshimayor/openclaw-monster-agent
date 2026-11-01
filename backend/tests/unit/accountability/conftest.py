"""These tests exercise the repos against their in-memory store.

Production refuses that fallback when DATABASE_URL is set — silently keeping
commitments in process memory is what produced reminders that nagged until the
container restarted and then vanished. The tests opt in explicitly rather than
inheriting the exemption, so the production guard stays honest.
"""

from __future__ import annotations

import pytest

from src.core import commitment_repo as repo
from src.core import config


# Stashed before the override so a test can still reach the real guard.
REAL_MEMORY_FALLBACK_ALLOWED = repo.memory_fallback_allowed


@pytest.fixture(autouse=True)
def allow_memory_store(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(repo, "memory_fallback_allowed", lambda: True)
    repo._MEM.clear()
    yield
    repo._MEM.clear()


@pytest.fixture(autouse=True)
def nagging_enabled(monkeypatch: pytest.MonkeyPatch):
    """Reminders ship switched off; these tests are about the engine itself.

    The engine is disabled rather than deleted, so it still has to work when
    someone turns it back on — which is only true if something exercises it.
    The shipped default is pinned separately, in test_reminders_off_by_default.
    """
    monkeypatch.setenv("NAG_ENABLED", "true")
    config.get_settings.cache_clear()
    yield
    config.get_settings.cache_clear()
