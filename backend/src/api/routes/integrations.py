"""Integration health, and telling you when it breaks.

The Google credential is the one dependency that takes four tools down with it
and says nothing. This checks it, and on a transition from working to broken
sends one message to your phone with the command that fixes it.

One message, on the transition only. A daily "Google is still dead" is how an
alert becomes something you swipe away.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter

from ...agents.bus import get_event_bus
from ...core.google_health import GoogleHealth, alert_text, check_refresh_token
from ...core.logging import get_logger
from ...core.types import AgentBusEvent, AgentEventKind, AgentEventPriority

logger = get_logger("api.integrations")

router = APIRouter(prefix="/api/integrations", tags=["integrations"])

# Last result, so a daily check only shouts when the answer changes. Process
# memory on purpose: the container restarting and re-alerting once is a far
# smaller problem than a table to migrate.
_last_ok: Optional[bool] = None


@router.get("/google")
async def google_status() -> Dict[str, Any]:
    """Check without notifying. Safe to poll, safe to curl."""
    health = await check_refresh_token()
    return {**health.to_dict(), "headline": health.headline}


@router.post("/google/check")
async def google_check(force_alert: bool = False) -> Dict[str, Any]:
    """Check, and alert if it just broke. Called daily from cron."""
    global _last_ok
    health: GoogleHealth = await check_refresh_token()

    # "unreachable" is a network blip, not a dead credential. Alerting on it
    # would send you re-authorising a token that is perfectly fine.
    credential_failed = not health.ok and health.error != "unreachable"
    transitioned = credential_failed and _last_ok is not False
    should_alert = force_alert or transitioned

    sent = False
    if should_alert and credential_failed:
        sent = await _push(
            title="Google credential is dead",
            message=alert_text(health),
            priority=AgentEventPriority.P1_IMPORTANT,
        )
    elif health.ok and _last_ok is False:
        # Say when it comes back, so a fix is confirmed rather than assumed.
        sent = await _push(
            title="Google credential restored",
            message="Calendar, Sheets, Docs and Gmail are working again.",
            priority=AgentEventPriority.P2_UPDATE,
        )

    if health.error != "unreachable":
        _last_ok = health.ok

    logger.info(
        "google_health_checked", ok=health.ok, error=health.error or None, alerted=sent
    )
    return {**health.to_dict(), "headline": health.headline, "alerted": sent}


async def _push(title: str, message: str, priority) -> bool:
    bus = get_event_bus()
    if getattr(bus, "_pa", None) is None:
        logger.warning("google_alert_undeliverable", reason="no personal assistant attached")
        return False
    try:
        await bus._pa.ingest_event(
            AgentBusEvent(
                kind=AgentEventKind.TASK_COMPLETED,
                priority=priority,
                title=title,
                summary=message[:320],
                details={"description": title, "report": message},
            )
        )
        return True
    except Exception as exc:
        logger.warning("google_alert_failed", error=str(exc))
        return False
