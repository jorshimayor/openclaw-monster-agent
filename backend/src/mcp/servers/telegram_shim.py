"""Telegram MCP stdio shim — pure Python stdlib (no pip deps).

Replaces the previous node.js shim. Exposes the EXACT same 6 JSON-RPC 2.0 tools
over stdin/stdout so McpStdioTransport works unchanged. Credentials come from
env vars TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_ADMIN_IDS (comma-sep).

Run standalone (for testing):
  TELEGRAM_BOT_TOKEN=xxx TELEGRAM_CHAT_ID=399640868 python telegram_shim.py
Then paste a line of JSON such as:
  {"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05"}}
"""

from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
import ssl
import tempfile
import uuid
from typing import Any, Dict, List, Optional

_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
_default_chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
_admin_ids_raw = os.environ.get("TELEGRAM_ADMIN_IDS", "")
_admin_ids: List[str] = [s.strip() for s in _admin_ids_raw.split(",") if s.strip()]

# Shared SSL context — Telegram uses valid cert, use system CA bundle
_ctx = ssl.create_default_context()


def _tg(method: str, body: Optional[Dict[str, Any]] = None, form_fields: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Call Telegram Bot API. form_fields = [{name, filename, content_bytes, content_type}] for multipart."""
    if not _token:
        return {"ok": False, "stub": True, "error": "TELEGRAM_BOT_TOKEN not set"}
    url = f"https://api.telegram.org/bot{urllib.parse.quote(_token)}/{method}"
    try:
        if form_fields:
            # Multipart/form-data (sendDocument). Build boundary + payload in memory.
            boundary = f"----TgShimFormBoundary{uuid.uuid4().hex}"
            parts: List[bytes] = []
            def add_field(name: str, value: Any, filename: Optional[str] = None, content_type: str = "text/plain", content_bytes: Optional[bytes] = None):
                header = f"--{boundary}\r\n".encode()
                if filename is not None and content_bytes is not None:
                    header += (
                        f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
                    ).encode()
                    header += f"Content-Type: {content_type}\r\n\r\n".encode()
                    parts.append(header + content_bytes + b"\r\n")
                else:
                    header += f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode()
                    parts.append(header + str(value).encode("utf-8") + b"\r\n")
            # First, add JSON body fields (chat_id, caption, parse_mode) as plain form fields
            for k, v in (body or {}).items():
                if v is None:
                    continue
                add_field(k, v)
            for ff in form_fields:
                add_field(
                    name=ff["name"],
                    value=None,
                    filename=ff.get("filename"),
                    content_type=ff.get("content_type", "application/octet-stream"),
                    content_bytes=ff.get("content_bytes", b""),
                )
            parts.append(f"--{boundary}--\r\n".encode())
            payload = b"".join(parts)
            req = urllib.request.Request(
                url, data=payload, method="POST",
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            )
        else:
            data = json.dumps(body or {}).encode("utf-8")
            req = urllib.request.Request(
                url, data=data, method="POST",
                headers={"Content-Type": "application/json", "Accept": "application/json"},
            )
        with urllib.request.urlopen(req, timeout=30, context=_ctx) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                return json.loads(raw)
            except Exception:
                return {"ok": False, "error": f"invalid JSON response: {raw[:200]}"}
    except urllib.error.HTTPError as e:
        try:
            raw = e.read().decode("utf-8", errors="replace")
            try:
                return json.loads(raw)
            except Exception:
                return {"ok": False, "error": f"HTTP {e.code}: {raw[:200]}"}
        except Exception:
            return {"ok": False, "error": f"HTTP {e.code}: {str(e)}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _resolve_chat(args: Dict[str, Any]) -> str:
    if args and args.get("chat_id"):
        return str(args["chat_id"])
    return _default_chat_id


# ── Tool implementations ──────────────────────────────────────────────────────

def tool_send_message(args: Dict[str, Any]) -> Dict[str, Any]:
    chat_id = _resolve_chat(args)
    if not chat_id:
        return {"ok": False, "stub": True, "error": "No TELEGRAM_CHAT_ID set and chat_id not provided"}
    text = args.get("text", "")
    if not text:
        return {"ok": False, "error": "text required"}
    body = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": args.get("parse_mode") or "HTML",
        "disable_web_page_preview": args.get("disable_web_page_preview", True),
        "disable_notification": bool(args.get("disable_notification")),
    }
    r = _tg("sendMessage", body)
    msg_id = None
    if isinstance(r.get("result"), dict):
        msg_id = r["result"].get("message_id")
    if args.get("pin") and r.get("ok") and msg_id is not None:
        _tg("pinChatMessage", {
            "chat_id": chat_id,
            "message_id": msg_id,
            "disable_notification": bool(args.get("disable_notification")),
        })
    return {"ok": bool(r.get("ok")), "chat_id": chat_id, "message_id": msg_id, "raw": r}


def tool_send_alert(args: Dict[str, Any]) -> Dict[str, Any]:
    icons = {"P0_CRITICAL": "🔴 P0", "P1_ACTION": "🟠 P1", "P2_UPDATE": "🟡 P2", "P3_INFO": "🔵 INFO"}
    p = args.get("priority") or "P2_UPDATE"
    icon = icons.get(p, p or "")
    lines: List[str] = []
    title = args.get("title") or "Alert"
    if icon:
        lines.append(f"<b>{icon} {title}</b>")
    else:
        lines.append(f"<b>{title}</b>")
    body = args.get("body")
    if body:
        lines.append("")
        lines.append(body)
    action_items = args.get("action_items") or []
    if action_items:
        lines.append("")
        lines.append("<b>Action items:</b>")
        for i, a in enumerate(action_items, 1):
            lines.append(f"{i}. {a}")
    disable_notification = p in {"P3_INFO", "P2_UPDATE"}
    pin = p == "P0_CRITICAL"
    chat_id = _resolve_chat(args)
    if not chat_id:
        return {"ok": False, "stub": True, "error": "No TELEGRAM_CHAT_ID set and chat_id not provided"}
    r = _tg("sendMessage", {
        "chat_id": chat_id,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
        "disable_notification": disable_notification,
        "text": "\n".join(lines),
    })
    msg_id = None
    if isinstance(r.get("result"), dict):
        msg_id = r["result"].get("message_id")
    if pin and r.get("ok") and msg_id is not None:
        _tg("pinChatMessage", {"chat_id": chat_id, "message_id": msg_id, "disable_notification": False})
    return {"ok": bool(r.get("ok")), "priority": p, "chat_id": chat_id, "message_id": msg_id, "raw": r}


def tool_send_digest(args: Dict[str, Any]) -> Dict[str, Any]:
    chat_id = _resolve_chat(args)
    parts: List[str] = []
    title = args.get("title") or "Monster Agent · Daily Digest"
    parts.append(f"<b>📊 {title}</b>\n")
    status_icons = {"QUEUED": "⏳", "RUNNING": "⚙️", "COMPLETED": "✅", "FAILED": "❌", "CANCELLED": "🚫"}
    tasks = args.get("tasks") or []
    for i, t in enumerate(tasks, 1):
        status = str(t.get("status", ""))
        icon = status_icons.get(status, "•")
        conf = ""
        if isinstance(t.get("confidence"), (int, float)):
            conf = f" · conf {int(round(float(t['confidence']) * 100))}%"
        desc = str(t.get("description", ""))[:120]
        tid = str(t.get("task_id", ""))
        preview = str(t.get("final_report_preview", ""))[:140]
        # Strip HTML tags from preview
        import re
        preview_clean = re.sub(r"<[^>]+>", "", preview)
        row = f"{icon} <b>Task {i}</b> [{status}]{conf}\n   {desc}"
        if tid:
            row += f"\n   <code>{tid[:8]}…</code>"
        if preview_clean:
            row += f"\n   <i>{preview_clean}…</i>"
        parts.append(row)
    crystals = args.get("crystals") or []
    if crystals:
        parts.append("")
        parts.append(f"<b>💎 New knowledge crystals ({len(crystals)}):</b>")
        for c in crystals[:8]:
            parts.append(f"   - {str(c)[:120]}")
    integrations = args.get("integrations") or []
    if integrations:
        parts.append("")
        parts.append("<b>🛠 Integrations:</b>")
        for it in integrations:
            name = str(it.get("name", ""))
            status = str(it.get("status", ""))
            ic = "🟢" if status == "healthy" else "🟡" if status == "degraded" else "🔴"
            parts.append(f"   {ic} {name} — {status}")
    if not chat_id:
        return {"ok": False, "stub": True, "error": "No TELEGRAM_CHAT_ID set and chat_id not provided"}
    r = _tg("sendMessage", {
        "chat_id": chat_id,
        "text": "\n".join(parts),
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
        "disable_notification": True,
    })
    msg_id = None
    if isinstance(r.get("result"), dict):
        msg_id = r["result"].get("message_id")
    return {"ok": bool(r.get("ok")), "chat_id": chat_id, "message_id": msg_id, "tasks": len(tasks), "raw": r}


def tool_send_document(args: Dict[str, Any]) -> Dict[str, Any]:
    chat_id = _resolve_chat(args)
    if not _token or not chat_id:
        return {"ok": False, "stub": True, "error": "Telegram credentials missing"}
    filename_raw = args.get("document_filename") or "report.txt"
    filename = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in filename_raw)
    document_text = str(args.get("document_text") or "")
    # Safe filename to /tmp (used only for our own debugging record; not for upload)
    try:
        with tempfile.NamedTemporaryFile(mode="w", prefix="tgdoc_", suffix=f"_{filename}", delete=False, encoding="utf-8") as f:
            f.write(document_text)
            tmp_path = f.name
    except Exception:
        tmp_path = ""
    form_fields = [
        {
            "name": "document",
            "filename": filename,
            "content_type": "text/plain",
            "content_bytes": document_text.encode("utf-8"),
        }
    ]
    body: Dict[str, Any] = {"chat_id": chat_id}
    if args.get("caption"):
        body["caption"] = args["caption"]
    if args.get("parse_mode"):
        body["parse_mode"] = args["parse_mode"]
    r = _tg("sendDocument", body=body, form_fields=form_fields)
    msg_id = None
    if isinstance(r.get("result"), dict):
        msg_id = r["result"].get("message_id")
    return {"ok": bool(r.get("ok")), "chat_id": chat_id, "message_id": msg_id, "file": tmp_path, "raw": r}


def tool_pin_message(args: Dict[str, Any]) -> Dict[str, Any]:
    chat_id = _resolve_chat(args)
    message_id = args.get("message_id")
    if message_id is None:
        return {"ok": False, "error": "message_id required"}
    r = _tg("pinChatMessage", {
        "chat_id": chat_id,
        "message_id": int(message_id),
        "disable_notification": bool(args.get("disable_notification")),
    })
    return {"ok": bool(r.get("ok")), "chat_id": chat_id, "message_id": message_id, "raw": r}


def tool_get_updates(args: Dict[str, Any]) -> Dict[str, Any]:
    r = _tg("getUpdates", {
        "offset": int(args.get("offset") or 0),
        "limit": int(args.get("limit") or 20),
        "timeout": int(args.get("timeout") or 0),
    })
    result = r.get("result") if isinstance(r.get("result"), list) else []
    return {"ok": bool(r.get("ok")), "count": len(result), "updates": result}


_TOOLS = {
    "send_message": tool_send_message,
    "send_alert": tool_send_alert,
    "send_digest": tool_send_digest,
    "send_document": tool_send_document,
    "pin_message": tool_pin_message,
    "get_updates": tool_get_updates,
}

_TOOL_SCHEMAS = [
    {
        "name": "send_message",
        "description": "Send a text message to a Telegram chat (supports Markdown). Default chat_id = TELEGRAM_CHAT_ID.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "chat_id": {"type": "string", "description": "Override target chat id (numeric or @channelname)"},
                "text": {"type": "string"},
                "parse_mode": {"type": "string", "enum": ["HTML", "MarkdownV2", "Markdown"], "default": "HTML"},
                "disable_web_page_preview": {"type": "boolean", "default": True},
                "disable_notification": {"type": "boolean", "default": False},
                "pin": {"type": "boolean", "default": False, "description": "Pin after sending (P0/P1 alerts)"},
            },
            "required": ["text"],
        },
    },
    {
        "name": "send_alert",
        "description": "Priority alert (P0 P1). Prepends emoji + sends with disable_notification=false, auto-pins P0.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "priority": {"type": "string", "enum": ["P0_CRITICAL", "P1_ACTION", "P2_UPDATE", "P3_INFO"], "default": "P2_UPDATE"},
                "title": {"type": "string"},
                "body": {"type": "string"},
                "action_items": {"type": "array", "items": {"type": "string"}},
                "chat_id": {"type": "string"},
            },
            "required": ["title", "body"],
        },
    },
    {
        "name": "send_digest",
        "description": "Daily or periodic digest of task status, new knowledge crystals, integration health.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "default": "Monster Agent · Daily Digest"},
                "tasks": {"type": "array", "items": {"type": "object"}},
                "crystals": {"type": "array", "items": {"type": "string"}},
                "integrations": {"type": "array", "items": {"type": "object"}},
                "chat_id": {"type": "string"},
            },
            "required": ["tasks"],
        },
    },
    {
        "name": "send_document",
        "description": "Upload a document/report to Telegram. Caption describes it.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "chat_id": {"type": "string"},
                "caption": {"type": "string"},
                "document_filename": {"type": "string"},
                "document_text": {"type": "string"},
                "parse_mode": {"type": "string", "enum": ["HTML", "MarkdownV2", "Markdown"], "default": "HTML"},
            },
            "required": ["document_filename", "document_text"],
        },
    },
    {
        "name": "pin_message",
        "description": "Pin a message by message_id in the chat.",
        "inputSchema": {
            "type": "object",
            "properties": {"chat_id": {"type": "string"}, "message_id": {"type": "integer"}, "disable_notification": {"type": "boolean", "default": False}},
            "required": ["message_id"],
        },
    },
    {
        "name": "get_updates",
        "description": "Read recent Telegram update messages (for command parsing).",
        "inputSchema": {
            "type": "object",
            "properties": {"offset": {"type": "integer"}, "limit": {"type": "integer", "default": 20}, "timeout": {"type": "integer", "default": 5}},
        },
    },
]


# ── JSON-RPC stdio event loop ─────────────────────────────────────────────────

def _send(obj: Dict[str, Any]) -> None:
    try:
        line = json.dumps(obj, ensure_ascii=False, default=str)
    except Exception:
        line = json.dumps({"jsonrpc": "2.0", "error": {"code": -32603, "message": "serialization error"}})
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


def main() -> None:
    # Unbuffer stdout/stderr entirely (defense in depth even if PYTHONUNBUFFERED missing)
    import io
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(line_buffering=True, write_through=True)
        except Exception:
            pass
    if hasattr(sys.stderr, "reconfigure"):
        try:
            sys.stderr.reconfigure(line_buffering=True, write_through=True)
        except Exception:
            pass
    # Emit initialized notification early (same contract as node shim)
    _send({"jsonrpc": "2.0", "method": "notifications/initialized"})
    while True:
        raw = sys.stdin.readline()
        if not raw:
            break
        line = raw.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except Exception:
            continue
        if not isinstance(msg, dict) or not msg.get("method"):
            continue
        msg_id = msg.get("id")
        method = msg["method"]
        params = msg.get("params") or {}
        if method == "initialize":
            if msg_id is None:
                continue
            _send({
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "telegram-py-shim", "version": "1.0.0"},
                },
            })
            continue
        if method == "notifications/initialized":
            continue
        if method == "tools/list":
            if msg_id is None:
                continue
            _send({"jsonrpc": "2.0", "id": msg_id, "result": {"tools": _TOOL_SCHEMAS}})
            continue
        if method == "tools/call":
            if msg_id is None:
                continue
            name = params.get("name")
            arguments = params.get("arguments") or {}
            fn = _TOOLS.get(name)
            if fn is None:
                _send({"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32601, "message": f"Unknown tool: {name}"}})
                continue
            try:
                result = fn(arguments or {})
            except Exception as e:
                _send({"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32000, "message": str(e)}})
                continue
            _send({"jsonrpc": "2.0", "id": msg_id, "result": result})
            continue
        # Unknown method
        if msg_id is not None:
            _send({"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32601, "message": f"Unknown method: {method}"}})


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        # Last-ditch log to stderr (won't go to RPC channel but shows in process logs)
        sys.stderr.write(f"telegram_shim_fatal: {type(e).__name__}: {e}\n")
        sys.stderr.flush()
