from __future__ import annotations

import asyncio
import json
import html
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Any, Deque, Dict, List, Optional, Tuple, TYPE_CHECKING

from ..core.config import get_settings
from ..core.logging import get_logger
from ..core.types import (
    AgentBusEvent,
    AgentEventKind,
    AgentEventPriority,
    AgentResult,
    AgentRole,
)
from .base import Agent, Tool

if TYPE_CHECKING:
    from ..llm.router import LLMRouter
    from ..mcp.manager import McpServerManager

logger = get_logger("agents.personal_assistant")

_PRIORITY_META: Dict[AgentEventPriority, Dict[str, Any]] = {
    AgentEventPriority.P0_CRITICAL: {"icon": "🔴", "label": "P0", "sound": False, "pin": True, "max_per_window": None},
    AgentEventPriority.P1_ACTION: {"icon": "🟠", "label": "P1", "sound": False, "pin": False, "max_per_window": 3},
    AgentEventPriority.P2_UPDATE: {"icon": "🟡", "label": "P2", "sound": True, "pin": False, "max_per_window": 12},
    AgentEventPriority.P3_INFO: {"icon": "🔵", "label": "INFO", "sound": True, "pin": False, "max_per_window": 0},
}


class PersonalAssistantAgent(Agent):
    role: AgentRole = AgentRole.PERSONAL_ASSISTANT
    model_profile: str = "groq/llama-3.1-8b-instant"
    tool_allowlist: List[str] = [
        "telegram.*",
        "slack.send_message",
        "slack.post_update",
        "google_workspace.send_email",
    ]
    soul_path: str = "src/souls/personal_assistant.md"

    def __init__(self) -> None:
        super().__init__()
        self.settings = get_settings()
        self._log = logger
        self._window_start = datetime.now(timezone.utc)
        self._window: Dict[AgentEventPriority, int] = {p: 0 for p in AgentEventPriority}
        self._mcp_manager: Optional["McpServerManager"] = None
        self._digest_events: Deque[AgentBusEvent] = deque(maxlen=2000)
        self._sent_pins: List[int] = []
        self._mute_until: Optional[datetime] = None
        self._mute_tiers: Dict[AgentEventPriority, bool] = {}
        self._last_digest_sent: Optional[datetime] = None

    # ── lifecycle hooks (called from AgentEventBus) ───────────────────────

    def attach_mcp(self, manager: "McpServerManager") -> None:
        self._mcp_manager = manager

    async def ingest_event(self, event: AgentBusEvent) -> Dict[str, Any]:
        """Main entry — every event from every agent flows through here.

        Returns a routing decision dict: {routed: telegram|digest|suppressed, message_id?, reason?}.
        """
        self._advance_window_if_needed()
        self._digest_events.append(event)

        if self._is_muted(event.priority):
            self._log.debug("pa_muted", priority=event.priority.value, kind=event.kind.value)
            return {"routed": "digest", "reason": "muted"}

        decision = self._route(event)
        if decision == "alert":
            sent = await self._send_telegram_alert(event)
            self._window[event.priority] = self._window.get(event.priority, 0) + 1
            return {"routed": "telegram", **sent}

        if decision == "digest":
            return {"routed": "digest", "kind": event.kind.value}

        return {"routed": "suppressed", "reason": "rate_limit_or_low_priority"}

    async def send_digest(self, title: Optional[str] = None) -> Dict[str, Any]:
        """Compile the events buffer into a Telegram digest card + send."""
        now = datetime.now(timezone.utc)
        since = self._last_digest_sent or (now - timedelta(hours=24))
        events = [e for e in self._digest_events if e.created_at.replace(tzinfo=timezone.utc) >= since]

        tasks_by_status: Dict[str, List[AgentBusEvent]] = {}
        crystals: List[str] = []
        integrations: List[Dict[str, str]] = []

        for e in events:
            if e.kind in (
                AgentEventKind.TASK_CREATED,
                AgentEventKind.TASK_STARTED,
                AgentEventKind.PIPELINE_STEP,
                AgentEventKind.TASK_COMPLETED,
                AgentEventKind.TASK_FAILED,
                AgentEventKind.TASK_CANCELLED,
            ):
                status = _status_from_event_kind(e.kind)
                tasks_by_status.setdefault(status, []).append(e)
            elif e.kind == AgentEventKind.KNOWLEDGE_CRYSTAL:
                title_c = e.title or e.details.get("summary") or str(e.details)
                crystals.append(title_c[:160])
            elif e.kind in (AgentEventKind.INTEGRATION_DOWN, AgentEventKind.INTEGRATION_DEGRADED):
                integrations.append({"name": e.integration or "unknown", "status": "degraded"})
            elif e.kind == AgentEventKind.MANUAL_NOTIFY and e.integration:
                integrations.append({"name": e.integration, "status": "healthy"})

        completed = tasks_by_status.get("COMPLETED", [])
        running = tasks_by_status.get("RUNNING", [])
        failed = tasks_by_status.get("FAILED", [])
        cancelled = tasks_by_status.get("CANCELLED", [])

        def _task_digest_items(events_sub: List[AgentBusEvent]) -> List[Dict[str, Any]]:
            out: List[Dict[str, Any]] = []
            seen: set = set()
            for e in sorted(events_sub, key=lambda x: x.created_at, reverse=True):
                tid = str(e.task_id) if e.task_id else None
                if tid and tid in seen:
                    continue
                if tid:
                    seen.add(tid)
                out.append({
                    "task_id": tid,
                    "description": (e.details or {}).get("description", e.title or ""),
                    "status": _status_from_event_kind(e.kind),
                    "confidence": float((e.details or {}).get("overall_confidence", 0.0)),
                    "final_report_preview": (e.details or {}).get("final_report_preview") or (e.details or {}).get("summary", ""),
                })
            return out[:15]

        tasks_all = _task_digest_items(completed + running + failed + cancelled)
        # ensure status enum matches our schema
        for t in tasks_all:
            if t["status"] not in ("QUEUED","RUNNING","COMPLETED","FAILED","CANCELLED"):
                t["status"] = "RUNNING"

        payload = {
            "title": title or f"Monster Agent · Digest · {now.strftime('%Y-%m-%d %H:%M UTC')}",
            "tasks": tasks_all,
            "crystals": crystals[:12],
            "integrations": integrations,
        }
        result = await self._call_mcp("telegram.send_digest", payload)
        self._last_digest_sent = now
        if self._digest_events and not tasks_all and not crystals:
            self._log.info("pa_digest_empty")
        return {"routed": "telegram", "digest_events": len(events), "digest": result}

    # ── internal routing + helpers ────────────────────────────────────────

    def _advance_window_if_needed(self) -> None:
        now = datetime.now(timezone.utc)
        if now - self._window_start > timedelta(hours=1):
            self._window_start = now
            for k in list(self._window.keys()):
                self._window[k] = 0

    def _is_muted(self, priority: AgentEventPriority) -> bool:
        if self._mute_tiers.get(priority):
            return True
        if self._mute_until is not None:
            if datetime.now(timezone.utc) < self._mute_until and priority in (
                AgentEventPriority.P2_UPDATE,
                AgentEventPriority.P3_INFO,
            ):
                return True
        return False

    def _route(self, event: AgentBusEvent) -> str:
        if event.priority == AgentEventPriority.P0_CRITICAL:
            return "alert"
        if event.priority == AgentEventPriority.P3_INFO:
            return "digest"

        meta = _PRIORITY_META[event.priority]
        max_w = meta["max_per_window"]
        if max_w is None:
            return "alert"
        cur = self._window.get(event.priority, 0)
        if cur >= max_w:
            return "digest"
        if event.priority == AgentEventPriority.P1_ACTION:
            return "alert"
        if event.priority == AgentEventPriority.P2_UPDATE and event.kind in (
            AgentEventKind.TASK_COMPLETED,
            AgentEventKind.TASK_FAILED,
            AgentEventKind.INTEGRATION_DOWN,
            AgentEventKind.INTEGRATION_DEGRADED,
            AgentEventKind.TASK_CREATED,
            AgentEventKind.KNOWLEDGE_CRYSTAL,
        ):
            return "alert"
        return "digest"

    async def _send_telegram_alert(self, event: AgentBusEvent) -> Dict[str, Any]:
        meta = _PRIORITY_META[event.priority]
        short_id = ""
        if event.task_id:
            short_id = str(event.task_id)[:8]
        desc = (event.details or {}).get("description") or event.summary or ""
        desc_s = html.escape(desc[:120])
        dt = event.created_at.strftime("%Y-%m-%d %H:%M UTC")
        title_e = html.escape(event.title or event.kind.value.replace("_", " ").title())
        summary_e = html.escape(event.summary[:240])
        details_json = html.escape(json.dumps(flat_keys(event.details or {}), default=str)[:600])

        if event.priority in (AgentEventPriority.P0_CRITICAL, AgentEventPriority.P1_ACTION):
            body_lines = [f"<pre>{summary_e}</pre>"]
            if event.task_id:
                status_line = f"<b>Task:</b> <code>{short_id}…</code> — {desc_s}" if desc_s else f"<b>Task ID:</b> <code>{short_id}…</code>"
                body_lines.append(status_line)
            src = event.source_agent_role.value if event.source_agent_role else (event.integration or "system")
            body_lines.append(f"<b>Agent / Source:</b> {html.escape(src)}")
            if event.action_items:
                body_lines.append("<b>Action items:</b>")
                for i, a in enumerate(event.action_items[:5], 1):
                    body_lines.append(f"  {i}. {html.escape(a)}")
            body_lines.append(f"<b>Details:</b> <code>{details_json}</code>")
            full_body = "\n".join(body_lines)

            result = await self._call_mcp("telegram.send_alert", {
                "priority": event.priority.value,
                "title": title_e,
                "body": full_body,
                "action_items": [],
            })
            # pin not necessary — send_alert auto-pins P0 & sets sound per tier
            return {"event_id": str(event.id), "raw": result}

        # P2 short-form
        icon = meta["icon"]
        label = meta["label"]
        status_icon = "✅" if event.kind == AgentEventKind.TASK_COMPLETED else ("⚠️" if event.kind in (AgentEventKind.INTEGRATION_DEGRADED, AgentEventKind.INTEGRATION_DOWN) else "ℹ️")
        where = short_id or (event.integration or "")
        text = f"{icon} <b>{label}</b> {title_e} — {summary_e[:60]} [<code>{where}</code>] · {status_icon}"
        result = await self._call_mcp("telegram.send_message", {
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
            "disable_notification": meta["sound"],
            "pin": meta["pin"],
        })
        return {"event_id": str(event.id), "raw": result}

    async def _call_mcp(self, tool_ref: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Call an MCP tool (dotted form: 'telegram.send_digest').

        Falls back to stub logging if transport isn't started yet or Telegram
        credentials are missing — never lets a notification failure crash the
        pipeline caller.
        """
        if "." not in tool_ref:
            raise ValueError(f"tool_ref must be server.tool: {tool_ref}")
        server_name, tool_name = tool_ref.split(".", 1)
        if self._mcp_manager is None:
            self._log.warning("pa_mcp_no_manager", tool=tool_ref, args_keys=list(arguments.keys()))
            return {"stub": True, "reason": "mcp_manager_not_attached"}
        transport = self._mcp_manager._transports.get(server_name)
        if transport is None:
            self._log.warning("pa_mcp_no_transport", server=server_name, tool=tool_name)
            return {"stub": True, "reason": f"transport_not_started:{server_name}"}
        try:
            return await transport.call(
                "tools/call",
                {"name": tool_name, "arguments": arguments},
            )
        except Exception as exc:
            self._log.warning("pa_mcp_call_failed", tool=tool_ref, error=str(exc))
            return {"stub": True, "error": str(exc)}

    # ── standard agent interface (also supported for manual invocations) ──

    async def invoke(
        self,
        context: Dict[str, Any],
        tools: List[Tool],
        llm: "LLMRouter",
        extra_llm_kwargs: Optional[Dict[str, Any]] = None,
    ) -> AgentResult:
        mode = context.get("mode") or "digest"
        if mode == "digest":
            result = await self.send_digest(context.get("title"))
            output = (
                f"PersonalAssistant delivered digest: events_in_digest={result.get('digest_events', 0)}"
            )
            return AgentResult(
                agent_role=self.role,
                output=output,
                confidence=0.95,
                errors=None,
            )
        if mode == "ingest" and isinstance(context.get("event"), AgentBusEvent):
            routed = await self.ingest_event(context["event"])
            return AgentResult(
                agent_role=self.role,
                output=json.dumps(routed, default=str),
                confidence=0.9,
            )
        return AgentResult(
            agent_role=self.role,
            output="PersonalAssistantAgent ready. Use AgentEventBus.emit() to push events; or invoke(mode='digest').",
            confidence=1.0,
        )

    # ── admin helpers (from /command parsing in future) ───────────────────

    def handle_admin_command(self, text: str) -> Optional[str]:
        t = (text or "").strip()
        if t.lower().startswith("/mute"):
            parts = t.split()
            if len(parts) >= 2:
                arg = parts[1].upper()
                hours = 0
                if arg.endswith("H"):
                    try:
                        hours = int(arg[:-1])
                    except ValueError:
                        hours = 0
                if hours > 0:
                    self._mute_until = datetime.now(timezone.utc) + timedelta(hours=hours)
                    return f"🔕 Muted P2/P3 for {hours}h."
                try:
                    tier = AgentEventPriority(arg)
                    self._mute_tiers[tier] = True
                    return f"🔕 Muted tier {tier.value} until /unmute {tier.value}"
                except ValueError:
                    self._mute_until = datetime.now(timezone.utc) + timedelta(hours=8)
                    return "🔕 Muted P2/P3 for 8h."
            self._mute_until = datetime.now(timezone.utc) + timedelta(hours=8)
            return "🔕 Muted P2/P3 for 8h. Say /unmute to restore."
        if t.lower().startswith("/unmute"):
            parts = t.split()
            if len(parts) >= 2:
                try:
                    tier = AgentEventPriority(parts[1].upper())
                    self._mute_tiers.pop(tier, None)
                    return f"🔔 Unmuted tier {tier.value}"
                except ValueError:
                    pass
            self._mute_until = None
            self._mute_tiers.clear()
            return "🔔 All notifications unmuted."
        if t.lower() == "/digest":
            return "OK — digest send triggered."  # caller actually calls send_digest()
        return None


def _status_from_event_kind(k: AgentEventKind) -> str:
    return {
        AgentEventKind.TASK_CREATED: "QUEUED",
        AgentEventKind.TASK_STARTED: "RUNNING",
        AgentEventKind.PIPELINE_STEP: "RUNNING",
        AgentEventKind.AGENT_STEP_OUTPUT: "RUNNING",
        AgentEventKind.TASK_COMPLETED: "COMPLETED",
        AgentEventKind.TASK_FAILED: "FAILED",
        AgentEventKind.TASK_CANCELLED: "CANCELLED",
    }.get(k, "RUNNING")


def flat_keys(d: Dict[str, Any], prefix: str = "") -> Dict[str, Any]:
    flat: Dict[str, Any] = {}
    for k, v in d.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            flat.update(flat_keys(v, key + "."))
        elif isinstance(v, (list, tuple)) and len(v) <= 8:
            flat[key] = ", ".join(str(x)[:80] for x in v)
        else:
            flat[key] = str(v)[:120]
    return flat
