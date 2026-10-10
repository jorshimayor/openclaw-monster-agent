"""The doctor has to be able to say "ill".

It could not. `ok` was set unconditionally after the sample call, so a probe
that caught an exception still recorded as healthy, and a server nobody had
probed reported the same "down" as one that was genuinely broken. A revoked
Google token sat behind that for weeks.
"""

from datetime import datetime, timedelta, timezone

import pytest

from src.mcp.manager import PROBE_STALE_AFTER_SEC, McpServerManager


class _Manager(McpServerManager):
    """Only the status logic, with no servers or subprocesses."""

    def __init__(self):  # noqa: D107 - deliberately skips the real __init__
        self._probe_results = {}
        self._processes = {}

        class _Registry:
            @staticmethod
            def list_all_tools():
                return {}

        self.registry = _Registry()


def record(manager, name, ok, age_sec=0):
    when = datetime.now(timezone.utc) - timedelta(seconds=age_sec)
    manager._probe_results[name] = {"ok": ok, "timestamp": when.isoformat()}


def status_of(manager, name):
    return next(s.status for s in manager.get_server_statuses() if s.name == name)


@pytest.fixture
def manager():
    return _Manager()


def test_never_probed_says_so_rather_than_claiming_down(manager):
    """'down' for something nobody looked at is a lie that reads like news."""
    assert status_of(manager, "google_workspace") == "unprobed"


def test_a_passing_probe_is_healthy(manager):
    record(manager, "google_workspace", ok=True)
    assert status_of(manager, "google_workspace") == "healthy"


def test_a_failing_probe_is_down(manager):
    record(manager, "google_workspace", ok=False)
    assert status_of(manager, "google_workspace") == "down"


def test_an_old_pass_stops_counting_as_evidence(manager):
    record(manager, "google_workspace", ok=True, age_sec=PROBE_STALE_AFTER_SEC + 60)
    assert status_of(manager, "google_workspace") == "stale"


def test_a_fresh_pass_is_still_healthy_just_inside_the_window(manager):
    record(manager, "google_workspace", ok=True, age_sec=PROBE_STALE_AFTER_SEC - 60)
    assert status_of(manager, "google_workspace") == "healthy"


def test_a_failing_probe_stays_down_even_when_the_process_is_alive(manager):
    """A running process is not a working integration — the token can be dead."""
    class _Proc:
        returncode = None

    manager._processes["google_workspace"] = _Proc()
    record(manager, "google_workspace", ok=False)
    assert status_of(manager, "google_workspace") == "down"


def test_every_configured_server_is_reported(manager):
    names = {s.name for s in manager.get_server_statuses()}
    assert "google_workspace" in names and len(names) >= 5
