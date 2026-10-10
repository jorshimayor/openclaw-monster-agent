"""Is the Google refresh token still alive?

One token backs calendar, Sheets, Docs and Gmail. When it dies they all die
together and nothing says so — the timetable sync simply stops filing, which
looks like a quiet week rather than a broken credential. That went unnoticed
for three weeks once.

The check is the cheapest possible proof: exchange the refresh token for an
access token. If Google hands one back, the credential works; if it does not,
Google says why in a way worth repeating verbatim.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

import httpx

from .config import get_settings
from .logging import get_logger

logger = get_logger("core.google_health")

TOKEN_URL = "https://oauth2.googleapis.com/token"

# Must match _GOOGLE_SCOPES in mcp/servers/google_workspace.py. A token minted
# without one of these fails only when that tool is first used, which is a long
# way from the cause.
REQUIRED_SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
]

FIX_COMMAND = "python3 scripts/google-auth.py"


@dataclass
class GoogleHealth:
    ok: bool
    configured: bool
    error: str = ""
    detail: str = ""
    scopes: List[str] = field(default_factory=list)
    missing_scopes: List[str] = field(default_factory=list)
    checked_at: str = ""

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "configured": self.configured,
            "error": self.error,
            "detail": self.detail,
            "scopes": self.scopes,
            "missing_scopes": self.missing_scopes,
            "checked_at": self.checked_at,
        }

    @property
    def headline(self) -> str:
        if not self.configured:
            return "Google is not configured — no client id, secret or refresh token."
        if self.ok and self.missing_scopes:
            return (
                f"Google works, but {len(self.missing_scopes)} scope(s) are missing. "
                "Those tools will fail when first used."
            )
        if self.ok:
            return "Google credential is healthy."
        return f"Google credential is DEAD: {self.error or 'unknown error'}"


async def check_refresh_token(timeout: float = 20.0) -> GoogleHealth:
    """Exchange the refresh token. Never raises, never logs the token."""
    now = datetime.now(timezone.utc).isoformat()
    s = get_settings()
    client_id = s.google_workspace_client_id
    client_secret = s.google_workspace_client_secret
    refresh = s.google_workspace_refresh_token

    if not (client_id and client_secret and refresh):
        return GoogleHealth(
            ok=False, configured=False, error="not_configured",
            detail="GOOGLE_WORKSPACE_CLIENT_ID / _SECRET / _REFRESH_TOKEN are not all set.",
            checked_at=now,
        )

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(TOKEN_URL, data={
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh,
                "grant_type": "refresh_token",
            })
            payload = response.json()
    except Exception as exc:
        # A network failure is not a dead credential, and must not be reported
        # as one — otherwise a flaky minute sends you re-authorising for nothing.
        return GoogleHealth(
            ok=False, configured=True, error="unreachable",
            detail=f"{type(exc).__name__}: {exc}", checked_at=now,
        )

    if "access_token" not in payload:
        return GoogleHealth(
            ok=False, configured=True,
            error=str(payload.get("error") or f"http_{response.status_code}"),
            detail=str(payload.get("error_description") or "")[:300],
            checked_at=now,
        )

    granted = str(payload.get("scope", "")).split()
    return GoogleHealth(
        ok=True, configured=True, scopes=granted,
        missing_scopes=[s for s in REQUIRED_SCOPES if s not in granted],
        checked_at=now,
    )


def alert_text(health: GoogleHealth) -> str:
    """What gets sent to a phone. Short, and says what to do."""
    lines = [health.headline]
    if health.detail:
        lines.append(health.detail)
    if health.missing_scopes:
        lines.append("Missing: " + ", ".join(s.rsplit("/", 1)[-1] for s in health.missing_scopes))
    if not health.ok:
        lines += [
            "",
            "Down with it: calendar, Sheets sync, Docs, Gmail.",
            f"Fix: {FIX_COMMAND}",
        ]
    return "\n".join(lines)
