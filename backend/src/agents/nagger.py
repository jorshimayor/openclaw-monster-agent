"""The nag engine — the assistant's persistence.

A commitment that is due and not closed gets a reminder, then another, then a
louder one, forever. Nothing here consults the Personal Assistant's rate
limiter or /mute state: those exist to stop *update noise*, and a chase is not
noise. The only thing that stops a nag is an artifact.

Escalation ladder (by how many reminders have already gone unanswered):

    reminders   interval   tier   behaviour
    ---------   --------   ----   -----------------------------------------
    0-1         30 min     P1     plain reminder, sound on
    2-3         20 min     P1     blunter, restates the ask
    4-6         15 min     P0     pinned, counts the misses
    7-11        10 min     P0     pinned, shouts
    12+         10 min     P0     pinned, shouts + mirrors to Slack

`tick()` is idempotent and cheap: it is called both by the in-process loop
(while the container is awake) and by the Cloudflare cron (which wakes it).
"""

from __future__ import annotations

import asyncio
import html
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..core import commitment_repo as repo
from ..core.config import get_settings
from ..core.logging import get_logger
from ..models.commitment import CommitmentDB

logger = get_logger("agents.nagger")

# Rungs in ascending order of misses:
# (min_nag_count, interval_seconds, tier, mirror_to_slack)
_LADDER = [
    (0, 1800, "P1", False),
    (2, 1200, "P1", False),
    (4, 900, "P0", False),
    (7, 600, "P0", False),
    (12, 600, "P0", True),
]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def ladder_for(nag_count: int) -> Dict[str, Any]:
    """Highest rung whose miss-count floor the commitment has reached."""
    rung_idx = 0
    for i, (floor, _, _, _) in enumerate(_LADDER):
        if nag_count >= floor:
            rung_idx = i
    floor, interval, tier, slack = _LADDER[rung_idx]
    return {"interval": interval, "tier": tier, "slack": slack, "escalation": rung_idx}


def _human_overdue(seconds: int) -> str:
    if seconds < 60:
        return "just now"
    mins = seconds // 60
    if mins < 60:
        return f"{mins} min overdue"
    hours = mins // 60
    if hours < 24:
        rem = mins % 60
        return f"{hours}h {rem}m overdue" if rem else f"{hours}h overdue"
    days = hours // 24
    return f"{days}d {hours % 24}h overdue"


def _console_url() -> str:
    return get_settings().public_app_url.rstrip("/")


def compose_nag(c: CommitmentDB, nag_count: int, tier: str) -> str:
    """Telegram HTML. Tone escalates with the miss count — deliberately."""
    short = str(c.id)[:8]
    overdue = _human_overdue(
        max(0, int((_now() - (c.due_at if c.due_at.tzinfo else c.due_at.replace(tzinfo=timezone.utc))).total_seconds()))
    )
    title = html.escape(c.title[:220])
    detail = html.escape((c.detail or "")[:400])

    if nag_count >= 12:
        head = f"🚨 <b>REMINDER #{nag_count + 1} — THIS IS NOT GOING AWAY</b>"
        push = (
            f"You have ignored this {nag_count} times. I will keep sending this every 10 minutes "
            f"until you either ship it or explicitly kill it with <code>/drop {short}</code>."
        )
    elif nag_count >= 7:
        head = f"🚨 <b>REMINDER #{nag_count + 1} — STILL NOT DONE</b>"
        push = f"{nag_count} reminders ignored. Do it now, or drop it honestly."
    elif nag_count >= 4:
        head = f"🔴 <b>Still open — reminder #{nag_count + 1}</b>"
        push = "This has been sitting past its time for a while. What is blocking it?"
    elif nag_count >= 2:
        head = f"🟠 <b>Still waiting on this — reminder #{nag_count + 1}</b>"
        push = "Close it or tell me when. Silence just means I ask again."
    else:
        head = "🟠 <b>This is due now</b>"
        push = "Knock it out and send me the proof."

    lines = [
        head,
        "",
        f"<b>{title}</b>",
    ]
    if detail:
        lines.append(f"<i>{detail}</i>")
    lines += [
        "",
        f"⏰ {overdue}  ·  <code>{short}</code>",
        "",
        "<b>To close it I need an artifact — not just the word 'done':</b>",
        f"  <code>/done {short} &lt;link&gt;</code>   ← a URL to the thing",
        f"  <code>/done {short}</code> + attach a file",
        f"  <code>/done {short} &lt;paste 40+ chars of what you wrote&gt;</code>",
        "",
        f"Other options: <code>/snooze {short} 30</code> · <code>/drop {short}</code>",
        f'<a href="{_console_url()}/commitments">open the console</a>',
    ]
    return "\n".join(lines)


def compose_nag_slack(c: CommitmentDB, nag_count: int) -> str:
    short = str(c.id)[:8]
    overdue = _human_overdue(
        max(0, int((_now() - (c.due_at if c.due_at.tzinfo else c.due_at.replace(tzinfo=timezone.utc))).total_seconds()))
    )
    return (
        f"🚨 *Reminder #{nag_count + 1} — still not done*\n"
        f"*{c.title[:220]}*\n"
        f"{overdue} · `{short}`\n"
        f"Close it with `/done {short} <link>` on Telegram — an artifact is required.\n"
        f"{_console_url()}/commitments"
    )


class NagEngine:
    """Owns the reminder loop. One instance, created in the API lifespan."""

    def __init__(self) -> None:
        self._log = logger
        self._task: Optional[asyncio.Task[None]] = None
        self._started = False
        self._last_tick: Optional[datetime] = None
        self._last_tick_sent = 0

    # ── senders ───────────────────────────────────────────────────────────

    def _pa(self) -> Any:
        from .bus import get_event_bus

        return get_event_bus()._pa

    async def _telegram(self, text: str, pin: bool, silent: bool) -> Dict[str, Any]:
        pa = self._pa()
        if pa is None:
            self._log.warning("nag_no_pa")
            return {"ok": False, "error": "personal assistant not attached"}
        return await pa._call_mcp(
            "telegram.send_message",
            {
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
                "disable_notification": silent,
                "pin": pin,
            },
        )

    async def _slack(self, text: str) -> Dict[str, Any]:
        s = get_settings()
        if not s.slack_bot_token or not s.slack_channel:
            return {"ok": False, "reason": "slack_not_configured"}
        try:
            import httpx

            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.post(
                    "https://slack.com/api/chat.postMessage",
                    headers={"Authorization": f"Bearer {s.slack_bot_token}"},
                    json={"channel": s.slack_channel, "text": text},
                )
                return r.json()
        except Exception as exc:
            self._log.warning("nag_slack_failed", error=str(exc))
            return {"ok": False, "error": str(exc)}

    async def send_message(self, text: str, pin: bool = False, silent: bool = False) -> Dict[str, Any]:
        """Public helper for the Telegram command handlers' replies."""
        return await self._telegram(text, pin=pin, silent=silent)

    # ── the loop ──────────────────────────────────────────────────────────

    async def nag_one(self, c: CommitmentDB) -> Dict[str, Any]:
        rung = ladder_for(c.nag_count or 0)
        text = compose_nag(c, c.nag_count or 0, rung["tier"])
        res = await self._telegram(text, pin=rung["tier"] == "P0", silent=False)
        if rung["slack"]:
            await self._slack(compose_nag_slack(c, c.nag_count or 0))
        await repo.mark_nagged(c.id, rung["interval"], rung["escalation"])
        self._log.info(
            "nag_sent",
            commitment=str(c.id)[:8],
            nag_count=(c.nag_count or 0) + 1,
            tier=rung["tier"],
            next_in_sec=rung["interval"],
        )
        return {"id": str(c.id), "tier": rung["tier"], "sent": bool(res.get("ok")), "raw": res}

    async def tick(self) -> Dict[str, Any]:
        """One reminder round. Safe to call from cron and from the loop."""
        settings = get_settings()
        self._last_tick = _now()
        if not settings.nag_enabled:
            self._last_tick_sent = 0
            return {"enabled": False, "sent": 0}
        try:
            due = await repo.due_for_nag()
        except Exception as exc:
            self._log.warning("nag_tick_query_failed", error=str(exc))
            return {"enabled": True, "sent": 0, "error": str(exc)}
        results: List[Dict[str, Any]] = []
        for c in due:
            try:
                results.append(await self.nag_one(c))
            except Exception as exc:
                self._log.warning("nag_send_failed", commitment=str(c.id)[:8], error=str(exc))
        self._last_tick_sent = len(results)
        return {
            "enabled": True,
            "checked": len(due),
            "sent": len(results),
            "results": results,
            "at": self._last_tick.isoformat(),
        }

    async def _run(self) -> None:
        settings = get_settings()
        interval = max(60, settings.nag_tick_seconds)
        self._log.info("nag_loop_start", interval_sec=interval)
        while True:
            try:
                await asyncio.sleep(interval)
                await self.tick()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                self._log.warning("nag_loop_iteration_failed", error=str(exc))

    def start(self, loop: Optional[asyncio.AbstractEventLoop] = None) -> None:
        if self._started:
            return
        loop = loop or asyncio.get_event_loop()
        self._task = loop.create_task(self._run())
        self._started = True

    async def stop(self) -> None:
        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._started = False

    def state(self) -> Dict[str, Any]:
        return {
            "started": self._started,
            "worker_alive": self._task is not None and not self._task.done(),
            "last_tick": self._last_tick.isoformat() if self._last_tick else None,
            "last_tick_sent": self._last_tick_sent,
        }


_engine: Optional[NagEngine] = None


def get_nag_engine() -> NagEngine:
    global _engine
    if _engine is None:
        _engine = NagEngine()
    return _engine
