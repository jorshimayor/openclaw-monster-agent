"""These tests exercise the repos against their in-memory store.

Production refuses that fallback when DATABASE_URL is set — silently keeping
commitments in process memory is what produced reminders that nagged until the
container restarted and then vanished. The tests opt in explicitly rather than
inheriting the exemption, so the production guard stays honest.
"""

from __future__ import annotations

import pytest

from src.core import commitment_repo as repo


# Stashed before the override so a test can still reach the real guard.
REAL_MEMORY_FALLBACK_ALLOWED = repo.memory_fallback_allowed


@pytest.fixture(autouse=True)
def allow_memory_store(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(repo, "memory_fallback_allowed", lambda: True)
    repo._MEM.clear()
    yield
    repo._MEM.clear()
