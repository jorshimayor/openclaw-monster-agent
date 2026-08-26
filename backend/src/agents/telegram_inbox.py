"""Inbound Telegram — the half that makes this a conversation.

Two entry points, both landing in `handle_update()`:
  • webhook  — Telegram POSTs to /api/telegram/webhook (preferred: instant,
    and it wakes a sleeping container).
  • drain    — /api/telegram/drain long-polls getUpdates through the MCP shim.
    Runs on the same cron as the nag tick, so replies still get picked up with
    no webhook configured.

Commands:
  /todo /list            open commitments, most overdue first
  /done <id> <artifact>  close one — REQUIRES a link, a file, or real text
  /snooze <id> [mins]    delay the next reminder (never clears the row)
  /drop <id>             give up on it, on the record
  /add <text>            file a new commitment (append "| tomorrow evening")
  /nag                   force a reminder round now
  /status                counts
  /help

A bare message carrying an artifact (a link, a file, or a paragraph) while
exactly one commitment is overdue is treated as closing that one — replying
"here: <link>" to a nag should just work.
"""

from __future__ import annotations

import html
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set

from ..core import commitment_repo as repo
from ..core.artifact import classify
from ..core.config import get_settings
from ..core.logging import get_logger
from ..models.commitment import CommitmentStatus
from .commitment_extractor import resolve_due
from .nagger import get_nag_engine

logger = get_logger("agents.telegram_inbox")

# Bounded replay guard — getUpdates can hand back the same update twice if an
# offset commit is lost across a container sleep.
_SEEN: Set[int] = set()
_SEEN_MAX = 2000
_LAST_UPDATE_ID = 0

_HELP = """<b>What I can do</b>

<code>/todo</code> — what you still owe
<code>/done &lt;id&gt; &lt;link or text&gt;</code> — close one (artifact required)
<code>/snooze &lt;id&gt; 30</code> — push the next reminder back
<code>/drop &lt;id&gt;</code> — give up on it, on the record
<code>/add walk the dog | tomorrow morning</code> — new commitment
<code>/nag</code> — remind me right now
<code>/status</code> — counts
<code>/mute 4h</code> / <code>/unmute</code> — silence status updates
  (reminders for open commitments ignore mute, by design)

You can also just reply to a reminder with the link or the file. If exactly one
thing is overdue, I'll close that one."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _remember(update_id: int) -> bool:
    """True if this update is new. Keeps the seen-set from growing forever."""
    global _LAST_UPDATE_ID
    if update_id in _SEEN:
        return False
    _SEEN.add(update_id)
    if len(_SEEN) > _SEEN_MAX:
        for old in sorted(_SEEN)[: _SEEN_MAX // 2]:
            _SEEN.discard(old)
    _LAST_UPDATE_ID = max(_LAST_UPDATE_ID, update_id)
    return True


def last_update_id() -> int:
    return _LAST_UPDATE_ID


def _authorized(sender_id: str, chat_id: str) -> bool:
    """Admin ids gate the bot. With none configured, fall back to the single
    configured chat so an unlocked bot still isn't open to strangers."""
    s = get_settings()
    admins = {str(a) for a in s.telegram_admin_ids}
    if admins:
        return str(sender_id) in admins
    return bool(s.telegram_chat_id) and str(chat_id) == str(s.telegram_chat_id)


def _fmt_overdue(seconds: int) -> str:
    if seconds <= 0:
        return "due now"
    mins = seconds // 60
    if mins < 60:
        return f"{mins}m over"
    hours = mins // 60
    if hours < 24:
        return f"{hours}h over"
    return f"{hours // 24}d over"


async def _render_open_list() -> str:
    rows = await repo.list_all(status=CommitmentStatus.OPEN.value, limit=50)
    if not rows:
        return "✅ <b>Nothing open.</b> You're clear."
    now = _now()
    rows.sort(key=lambda r: _aware(r.due_at) or now)
    lines = [f"<b>📋 {len(rows)} open</b>", ""]
    for r in rows:
        due = _aware(r.due_at) or now
        overdue_sec = int((now - due).total_seconds())
        mark = "🔴" if overdue_sec > 0 else "⏳"
        when = (
            _fmt_overdue(overdue_sec)
            if overdue_sec > 0
            else f"due {due.isoformat(timespec='minutes')}"
        )
        nagged = f" · {r.nag_count} reminders" if (r.nag_count or 0) else ""
        lines.append(
            f"{mark} <code>{str(r.id)[:8]}</code> — {html.escape(r.title[:110])}\n"
            f"     <i>{when}{nagged}</i>"
        )
    lines += ["", "Close one: <code>/done &lt;id&gt; &lt;link&gt;</code>"]
    return "\n".join(lines)


def _closing_confirmation(row: Any, kind: str) -> str:
    return (
        f"✅ <b>Closed.</b> {html.escape(row.title[:160])}\n"
        f"Artifact recorded ({kind}). That took {row.nag_count or 0} reminder(s)."
    )


async def _close_with_artifact(row: Any, text: str, file_url: Optional[str], file_name: Optional[str]) -> str:
    verdict = classify(text=text, file_url=file_url, file_name=file_name)
    if not verdict["accepted"]:
        return (
            f"🚫 <b>Not accepted.</b>\n\n{html.escape(verdict['reason'])}\n\n"
            f"Still open: <code>{str(row.id)[:8]}</code> — {html.escape(row.title[:120])}"
        )
    updated = await repo.complete(
        row.id,
        artifact_kind=verdict["kind"],
        artifact_url=verdict["url"] or file_url,
        artifact_text=verdict["text"],
    )
    if updated is None:
        return "⚠️ Couldn't save that — try again in a moment."
    return _closing_confirmation(updated, verdict["kind"])


def _parse_add(rest: str) -> Dict[str, str]:
    """`/add do the thing | tuesday evening` → title + day/time hint."""
    title, _, when = rest.partition("|")
    when = when.strip().lower()
    day, tod = "", ""
    for token in re.split(r"[\s,]+", when):
        if token in ("today", "tomorrow", "tonight"):
            day = token
        elif token in (
            "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
            "mon", "tue", "wed", "thu", "fri", "sat", "sun",
        ):
            day = token
        elif token in ("morning", "afternoon", "evening", "night", "noon", "midday"):
            tod = token
    return {"title": title.strip(), "day": day, "time_of_day": tod}


async def _handle_command(cmd: str, rest: str, text: str, file_url: Optional[str], file_name: Optional[str]) -> str:
    if cmd in ("/todo", "/list", "/commitments", "/open"):
        return await _render_open_list()

    if cmd in ("/help", "/start"):
        return _HELP

    if cmd == "/status":
        st = await repo.stats()
        engine = get_nag_engine().state()
        return (
            f"<b>📊 Status</b>\n"
            f"open: <b>{st['open']}</b> · overdue: <b>{st['overdue']}</b>\n"
            f"done: {st['done']} · dropped: {st['dropped']}\n"
            f"nag loop: {'running' if engine['worker_alive'] else 'idle (cron-driven)'}\n"
            f"last check: {engine['last_tick'] or 'not yet'}"
        )

    if cmd == "/nag":
        result = await get_nag_engine().tick()
        if result.get("sent"):
            return ""  # the reminders themselves are the reply
        return "Nothing is due right now. <code>/todo</code> to see what's queued."

    if cmd == "/add":
        parsed = _parse_add(rest)
        if not parsed["title"]:
            return "Usage: <code>/add rewrite the README | tomorrow evening</code>"
        due = resolve_due(parsed["day"], parsed["time_of_day"])
        row = await repo.create(
            title=parsed["title"], due_at=due, source="telegram"
        )
        if row is None:
            return "⚠️ Couldn't save that."
        return (
            f"📌 <b>Filed.</b> <code>{str(row.id)[:8]}</code>\n"
            f"{html.escape(row.title[:160])}\n"
            f"<i>I'll start chasing you at {due.isoformat(timespec='minutes')} UTC.</i>"
        )

    if cmd in ("/done", "/did", "/complete", "/shipped"):
        parts = rest.split(None, 1)
        ref = parts[0] if parts else ""
        artifact_text = parts[1] if len(parts) > 1 else ""
        row = await repo.resolve_ref(ref) if ref else None
        if row is None:
            # No id given (or a bad one) — if the id slot was actually the start
            # of the artifact, treat the whole thing as a bare artifact reply.
            return await _handle_bare_artifact(rest or text, file_url, file_name)
        if row.status != CommitmentStatus.OPEN.value:
            return f"That one is already <b>{row.status}</b>. <code>/todo</code> for what's left."
        return await _close_with_artifact(row, artifact_text, file_url, file_name)

    if cmd == "/snooze":
        parts = rest.split()
        ref = parts[0] if parts else ""
        minutes = 30
        if len(parts) > 1:
            try:
                minutes = int(re.sub(r"[^0-9]", "", parts[1]) or 30)
            except ValueError:
                minutes = 30
        row = await repo.resolve_ref(ref)
        if row is None:
            return "Which one? <code>/snooze &lt;id&gt; 30</code> — <code>/todo</code> for ids."
        updated = await repo.snooze(row.id, minutes)
        until = _aware(updated.snooze_until) if updated else None
        return (
            f"😴 Quiet on <code>{str(row.id)[:8]}</code> until "
            f"{until.isoformat(timespec='minutes') if until else '?'} UTC. "
            f"Then I'm back."
        )

    if cmd in ("/drop", "/cancel", "/kill"):
        ref = rest.split()[0] if rest.split() else ""
        row = await repo.resolve_ref(ref)
        if row is None:
            return "Which one? <code>/drop &lt;id&gt;</code> — <code>/todo</code> for ids."
        await repo.drop(row.id)
        return (
            f"🗑 Dropped <code>{str(row.id)[:8]}</code> — {html.escape(row.title[:120])}\n"
            f"<i>Not done. Abandoned after {row.nag_count or 0} reminders. Noted.</i>"
        )

    if cmd in ("/mute", "/unmute", "/digest"):
        from .bus import get_event_bus

        pa = get_event_bus()._pa
        if pa is None:
            return "Notification agent isn't attached right now."
        reply = pa.handle_admin_command(text)
        if cmd == "/digest":
            await pa.send_digest()
            return "📊 Digest sent."
        note = "\n<i>Reminders for open commitments still come through.</i>" if cmd == "/mute" else ""
        return (reply or "OK.") + note

    return ""


async def _handle_bare_artifact(text: str, file_url: Optional[str], file_name: Optional[str]) -> str:
    """A reply with no command. If it carries an artifact and exactly one thing
    is overdue, close that one; otherwise ask which."""
    verdict = classify(text=text, file_url=file_url, file_name=file_name)
    if not verdict["accepted"]:
        return ""  # not an artifact and not a command — stay quiet

    now = _now()
    open_rows = await repo.list_all(status=CommitmentStatus.OPEN.value, limit=50)
    overdue = [r for r in open_rows if (_aware(r.due_at) or now) <= now]
    candidates = overdue or open_rows

    if not candidates:
        return "Nothing is open, so I don't know what that closes. <code>/todo</code>"

    if len(candidates) == 1:
        return await _close_with_artifact(candidates[0], text, file_url, file_name)

    candidates.sort(key=lambda r: _aware(r.due_at) or now)
    lines = ["Which one does that close?", ""]
    for r in candidates[:8]:
        lines.append(f"  <code>/done {str(r.id)[:8]}</code> — {html.escape(r.title[:90])}")
    lines.append("")
    lines.append("<i>Re-send the link with the id and I'll file it.</i>")
    return "\n".join(lines)


async def handle_update(update: Dict[str, Any]) -> Dict[str, Any]:
    """Process one Telegram update. Returns a routing summary; the reply (if
    any) has already been sent."""
    update_id = int(update.get("update_id") or 0)
    if update_id and not _remember(update_id):
        return {"skipped": "duplicate", "update_id": update_id}

    message = update.get("message") or update.get("edited_message") or update.get("channel_post")
    if not isinstance(message, dict):
        return {"skipped": "no_message", "update_id": update_id}

    chat_id = str((message.get("chat") or {}).get("id", ""))
    sender_id = str((message.get("from") or {}).get("id", ""))
    if not _authorized(sender_id, chat_id):
        logger.warning("telegram_unauthorized", sender=sender_id, chat=chat_id)
        return {"skipped": "unauthorized", "sender": sender_id}

    text = str(message.get("text") or message.get("caption") or "").strip()

    file_url: Optional[str] = None
    file_name: Optional[str] = None
    doc = message.get("document")
    if isinstance(doc, dict) and doc.get("file_id"):
        # Store the file_id, not a download URL — a Telegram file URL embeds
        # the bot token and must never be persisted.
        file_url = f"tg-file:{doc['file_id']}"
        file_name = str(doc.get("file_name") or "document")
    elif isinstance(message.get("photo"), list) and message["photo"]:
        largest = message["photo"][-1]
        file_url = f"tg-file:{largest.get('file_id')}"
        file_name = "photo.jpg"

    if not text and not file_url:
        return {"skipped": "empty", "update_id": update_id}

    reply = ""
    if text.startswith("/"):
        raw_cmd, _, rest = text.partition(" ")
        cmd = raw_cmd.split("@", 1)[0].lower()  # /done@MyBot in groups
        reply = await _handle_command(cmd, rest.strip(), text, file_url, file_name)
    else:
        reply = await _handle_bare_artifact(text, file_url, file_name)

    if reply:
        await get_nag_engine().send_message(reply)
    return {"handled": True, "update_id": update_id, "replied": bool(reply)}


async def drain_updates(limit: int = 40) -> Dict[str, Any]:
    """Pull pending updates through the MCP shim (no-webhook fallback)."""
    from .bus import get_event_bus

    pa = get_event_bus()._pa
    if pa is None:
        return {"ok": False, "error": "personal assistant not attached"}
    offset = _LAST_UPDATE_ID + 1 if _LAST_UPDATE_ID else 0
    raw = await pa._call_mcp("telegram.get_updates", {"offset": offset, "limit": limit, "timeout": 0})
    updates: List[Dict[str, Any]] = raw.get("updates") or []
    handled = []
    for u in updates:
        try:
            handled.append(await handle_update(u))
        except Exception as exc:
            logger.warning("telegram_update_failed", error=str(exc))
    return {"ok": True, "fetched": len(updates), "handled": len(handled), "offset_used": offset}
