"""The watchdog for the credential that takes four tools down with it."""

import pytest

from src.core.google_health import GoogleHealth, REQUIRED_SCOPES, alert_text


def healthy(**kw):
    return GoogleHealth(ok=True, configured=True, scopes=list(REQUIRED_SCOPES), **kw)


def test_a_healthy_credential_reads_as_healthy():
    assert "healthy" in healthy().headline.lower()


def test_a_dead_credential_says_dead_and_repeats_google_verbatim():
    h = GoogleHealth(ok=False, configured=True, error="invalid_grant",
                     detail="Token has been expired or revoked.")
    assert "DEAD" in h.headline
    text = alert_text(h)
    assert "invalid_grant" in text
    assert "Token has been expired or revoked." in text


def test_the_alert_names_what_is_down_and_how_to_fix_it():
    h = GoogleHealth(ok=False, configured=True, error="invalid_grant")
    text = alert_text(h)
    for expected in ("calendar", "Sheets", "Docs", "Gmail", "scripts/google-auth.py"):
        assert expected in text, expected


def test_unconfigured_is_distinct_from_broken():
    """Nothing to fix is not the same as something to fix."""
    h = GoogleHealth(ok=False, configured=False, error="not_configured")
    assert "not configured" in h.headline.lower()
    assert "DEAD" not in h.headline


def test_a_working_token_missing_a_scope_is_flagged_rather_than_passed():
    """Those tools fail only when first used, a long way from the cause."""
    h = GoogleHealth(ok=True, configured=True,
                     scopes=REQUIRED_SCOPES[:-1],
                     missing_scopes=[REQUIRED_SCOPES[-1]])
    assert "missing" in h.headline.lower()
    assert "gmail.readonly" in alert_text(h)


def test_a_healthy_alert_does_not_tell_you_to_re_authorise():
    assert "scripts/google-auth.py" not in alert_text(healthy())


@pytest.mark.asyncio
async def test_a_network_failure_is_not_reported_as_a_dead_credential(monkeypatch):
    """Otherwise a flaky minute sends you re-authorising a working token."""
    import src.core.google_health as mod

    class Boom:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, *a, **k): raise OSError("connection reset")

    monkeypatch.setattr(mod.httpx, "AsyncClient", lambda **k: Boom())
    monkeypatch.setattr(mod, "get_settings", lambda: type("S", (), {
        "google_workspace_client_id": "x", "google_workspace_client_secret": "y",
        "google_workspace_refresh_token": "z"})())

    health = await mod.check_refresh_token()
    assert health.ok is False
    assert health.error == "unreachable"   # the route must not alert on this
