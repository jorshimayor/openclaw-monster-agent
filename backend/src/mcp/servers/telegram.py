from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Dict, List, Tuple

from ...core.logging import get_logger
from ..registry import Tool

logger = get_logger("mcp.servers.telegram")

_TELEGRAM_SHIM_CODE = r"""
/* Telegram MCP shim (stdlib-only, zero deps)
 * Exposes 6 tools: send_message, send_document, pin_message, unpin_message,
 * get_updates, format_digest.
 * All methods post JSON to https://api.telegram.org/bot<token>/<method>
 */
const env = process.env;
const token = env.TELEGRAM_BOT_TOKEN || "";
const defaultChatId = env.TELEGRAM_CHAT_ID || "";
const adminIds = (env.TELEGRAM_ADMIN_IDS || "").split(",").map(s => s.trim()).filter(Boolean);

const { spawnSync } = require("child_process");

function sendStdio(msg) { process.stdout.write(JSON.stringify(msg) + "\n"); }

let nextId = 1;
const pending = new Map();

async function tg(method, body) {
  if (!token) return { ok: false, stub: true, error: "TELEGRAM_BOT_TOKEN not set" };
  const url = `https://api.telegram.org/bot${encodeURIComponent(token)}/${method}`;
  try {
    const resp = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", "Accept": "application/json" },
      body: JSON.stringify(body || {}),
    });
    const data = await resp.json();
    return data;
  } catch (err) {
    return { ok: false, error: String(err && err.message || err) };
  }
}

function resolveChat(args) {
  if (args && args.chat_id) return String(args.chat_id);
  return defaultChatId;
}

function respond(id, result) {
  sendStdio({ jsonrpc: "2.0", id, result });
}
function respondErr(id, code, msg) {
  sendStdio({ jsonrpc: "2.0", id, error: { code, message: msg } });
}

const TOOLS = [
  {
    name: "send_message",
    description: "Send a text message to a Telegram chat (supports Markdown). Default chat_id = TELEGRAM_CHAT_ID.",
    inputSchema: {
      type: "object",
      properties: {
        chat_id: { type: "string", description: "Override target chat id (numeric or @channelname)" },
        text: { type: "string" },
        parse_mode: { type: "string", enum: ["HTML", "MarkdownV2", "Markdown"], default: "HTML" },
        disable_web_page_preview: { type: "boolean", default: true },
        disable_notification: { type: "boolean", default: false },
        pin: { type: "boolean", default: false, description: "Pin after sending (P0/P1 alerts)" },
      },
      required: ["text"],
    },
  },
  {
    name: "send_alert",
    description: "Priority alert (P0 P1). Prepends emoji + sends with disable_notification=false, auto-pins P0.",
    inputSchema: {
      type: "object",
      properties: {
        priority: { type: "string", enum: ["P0_CRITICAL", "P1_ACTION", "P2_UPDATE", "P3_INFO"], default: "P2_UPDATE" },
        title: { type: "string" },
        body: { type: "string" },
        action_items: { type: "array", items: { type: "string" } },
        chat_id: { type: "string" },
      },
      required: ["title", "body"],
    },
  },
  {
    name: "send_digest",
    description: "Daily or periodic digest of task status, new knowledge crystals, integration health.",
    inputSchema: {
      type: "object",
      properties: {
        title: { type: "string", default: "Monster Agent · Daily Digest" },
        tasks: {
          type: "array",
          items: {
            type: "object",
            properties: {
              task_id: { type: "string" },
              description: { type: "string" },
              status: { type: "string", enum: ["QUEUED","RUNNING","COMPLETED","FAILED","CANCELLED"] },
              confidence: { type: "number" },
              final_report_preview: { type: "string" },
            },
          },
        },
        crystals: { type: "array", items: { type: "string" } },
        integrations: { type: "array", items: { type: "object", properties: { name: { type: "string" }, status: { type: "string" } } } },
        chat_id: { type: "string" },
      },
      required: ["tasks"],
    },
  },
  {
    name: "send_document",
    description: "Upload a document/report to Telegram. Caption describes it.",
    inputSchema: {
      type: "object",
      properties: {
        chat_id: { type: "string" },
        caption: { type: "string" },
        document_filename: { type: "string", description: "Write this filename to /tmp then upload — pass contents in document_text" },
        document_text: { type: "string", description: "Plain text / markdown contents of the file" },
        parse_mode: { type: "string", enum: ["HTML", "MarkdownV2", "Markdown"], default: "HTML" },
      },
      required: ["document_filename", "document_text"],
    },
  },
  {
    name: "pin_message",
    description: "Pin a message by message_id in the chat.",
    inputSchema: {
      type: "object",
      properties: { chat_id: { type: "string" }, message_id: { type: "integer" }, disable_notification: { type: "boolean", default: false } },
      required: ["message_id"],
    },
  },
  {
    name: "get_updates",
    description: "Read recent Telegram update messages (for command parsing).",
    inputSchema: {
      type: "object",
      properties: { offset: { type: "integer" }, limit: { type: "integer", default: 20 }, timeout: { type: "integer", default: 5 } },
    },
  },
];

const METHODS = {
  initialize({ id, params }) {
    respond(id, {
      protocolVersion: "2024-11-05",
      capabilities: { tools: {} },
      serverInfo: { name: "telegram-shim", version: "1.0.0" },
    });
  },
  "tools/list"({ id }) {
    respond(id, { tools: TOOLS.map(t => ({ name: t.name, description: t.description, inputSchema: t.inputSchema })) });
  },
  async "tools/call"({ id, params }) {
    const name = params.name;
    const args = params.arguments || {};
    try {
      if (name === "send_message") {
        const chat_id = resolveChat(args);
        if (!chat_id) { respond(id, { ok: false, stub: true, error: "No TELEGRAM_CHAT_ID set and chat_id not provided" }); return; }
        const body = {
          chat_id,
          text: args.text,
          parse_mode: args.parse_mode || "HTML",
          disable_web_page_preview: args.disable_web_page_preview !== false,
          disable_notification: !!args.disable_notification,
        };
        const r = await tg("sendMessage", body);
        if (args.pin && r && r.ok && r.result && r.result.message_id) {
          await tg("pinChatMessage", { chat_id, message_id: r.result.message_id, disable_notification: !!args.disable_notification });
        }
        respond(id, { ok: !!r.ok, chat_id, message_id: r && r.result && r.result.message_id, raw: r });
        return;
      }
      if (name === "send_alert") {
        const icons = { P0_CRITICAL: "🔴 P0", P1_ACTION: "🟠 P1", P2_UPDATE: "🟡 P2", P3_INFO: "🔵 INFO" };
        const p = args.priority || "P2_UPDATE";
        const lines = [];
        lines.push(`<b>${icons[p] || ""} ${args.title || "Alert"}</b>`);
        if (args.body) lines.push("\n" + args.body);
        if (args.action_items && args.action_items.length) {
          lines.push("\n<b>Action items:</b>");
          args.action_items.forEach((a, i) => lines.push(`${i + 1}. ${a}`));
        }
        const disable_notification = p === "P3_INFO" || p === "P2_UPDATE";
        const pin = p === "P0_CRITICAL";
        const chat_id = resolveChat(args);
        const r = await tg("sendMessage", {
          chat_id, parse_mode: "HTML",
          disable_web_page_preview: true,
          disable_notification,
          text: lines.join("\n"),
        });
        if (pin && r && r.ok && r.result && r.result.message_id) {
          await tg("pinChatMessage", { chat_id, message_id: r.result.message_id, disable_notification: false });
        }
        respond(id, { ok: !!r.ok, priority: p, chat_id, message_id: r && r.result && r.result.message_id, raw: r });
        return;
      }
      if (name === "send_digest") {
        const chat_id = resolveChat(args);
        const parts = [];
        parts.push(`<b>📊 ${args.title || "Monster Agent · Daily Digest"}</b>\n`);
        (args.tasks || []).forEach((t, i) => {
          const statusIcon = { QUEUED: "⏳", RUNNING: "⚙️", COMPLETED: "✅", FAILED: "❌", CANCELLED: "🚫" }[t.status] || "•";
          const conf = typeof t.confidence === "number" ? ` · conf ${Math.round(t.confidence * 100)}%` : "";
          parts.push(`${statusIcon} <b>Task ${i + 1}</b> [${t.status}]${conf}\n   ${(t.description || "").slice(0, 120)}${t.task_id ? `\n   <code>${t.task_id.slice(0, 8)}…</code>` : ""}${t.final_report_preview ? `\n   <i>${String(t.final_report_preview).slice(0, 140).replace(/<[^>]+>/g, "")}…</i>` : ""}`);
        });
        if (args.crystals && args.crystals.length) {
          parts.push(`\n<b>💎 New knowledge crystals (${args.crystals.length}):</b>`);
          args.crystals.slice(0, 8).forEach(c => parts.push(`   - ${String(c).slice(0, 120)}`));
        }
        if (args.integrations && args.integrations.length) {
          parts.push(`\n<b>🛠 Integrations:</b>`);
          args.integrations.forEach(it => {
            const ic = it.status === "healthy" ? "🟢" : it.status === "degraded" ? "🟡" : "🔴";
            parts.push(`   ${ic} ${it.name} — ${it.status}`);
          });
        }
        const r = await tg("sendMessage", {
          chat_id, text: parts.join("\n"), parse_mode: "HTML",
          disable_web_page_preview: true, disable_notification: true,
        });
        respond(id, { ok: !!r.ok, chat_id, message_id: r && r.result && r.result.message_id, tasks: (args.tasks || []).length, raw: r });
        return;
      }
      if (name === "send_document") {
        const chat_id = resolveChat(args);
        if (!token || !chat_id) { respond(id, { ok: false, stub: true, error: "Telegram credentials missing" }); return; }
        const fs = require("fs"); const path = require("path"); const os = require("os");
        const tmpFile = path.join(os.tmpdir(), (args.document_filename || "report.txt").replace(/[^a-zA-Z0-9._-]/g, "_"));
        fs.writeFileSync(tmpFile, String(args.document_text || ""), "utf8");
        const { execFileSync } = require("child_process");
        try {
          const r = JSON.parse(execFileSync("node", ["-e", `
            const fs=require("fs");
            (async ()=>{
              const FormData = (await import("undici")).FormData;
              const f = new FormData();
              f.append("chat_id", ${JSON.stringify(chat_id)});
              f.append("document", new Blob([fs.readFileSync(${JSON.stringify(tmpFile)})], {type:"text/plain"}), ${JSON.stringify(args.document_filename)});
              if (args.caption) f.append("caption", args.caption);
              if (args.parse_mode) f.append("parse_mode", args.parse_mode);
              const u = "https://api.telegram.org/bot"+encodeURIComponent(${JSON.stringify(token)})+"/sendDocument";
              const resp = await fetch(u, {method:"POST", body: f});
              process.stdout.write(JSON.stringify(await resp.json()));
            })().catch(e=>process.stdout.write(JSON.stringify({ok:false, error:String(e.message||e)})));
          `], { encoding: "utf8", maxBuffer: 20 * 1024 * 1024 }));
          respond(id, { ok: !!r.ok, chat_id, message_id: r && r.result && r.result.message_id, file: tmpFile, raw: r });
        } catch (err) {
          respond(id, { ok: false, error: String(err && err.message || err) });
        }
        return;
      }
      if (name === "pin_message") {
        const chat_id = resolveChat(args);
        const r = await tg("pinChatMessage", {
          chat_id, message_id: args.message_id,
          disable_notification: !!args.disable_notification,
        });
        respond(id, { ok: !!r.ok, chat_id, message_id: args.message_id, raw: r });
        return;
      }
      if (name === "get_updates") {
        const r = await tg("getUpdates", { offset: args.offset || 0, limit: args.limit || 20, timeout: args.timeout || 0 });
        respond(id, { ok: !!r.ok, count: r && r.result ? r.result.length : 0, updates: r && r.result });
        return;
      }
      respondErr(id, -32601, "Unknown tool: " + name);
    } catch (e) {
      respondErr(id, -32000, String(e && e.message || e));
    }
  },
};

process.stdin.on("data", buf => {
  const lines = String(buf).split("\n").filter(Boolean);
  for (const line of lines) {
    let msg;
    try { msg = JSON.parse(line); } catch { continue; }
    if (!msg || !msg.method) continue;
    const handler = METHODS[msg.method];
    if (handler) handler(msg);
    else if (msg.id) respondErr(msg.id, -32601, "Unknown method " + msg.method);
  }
});
sendStdio({ jsonrpc: "2.0", method: "notifications/initialized" });
"""


class TelegramMcpServer:
    """Telegram MCP server wrapper — direct HTTP shim (no pip deps).

    Credentials order:
      1. ``TELEGRAM_BOT_TOKEN`` (format ``123456:ABC-DEF...`` from @BotFather)
      2. ``TELEGRAM_CHAT_ID`` — default target (numeric user/group/channel id
         or ``@channelname``). ``TELEGRAM_ADMIN_IDS`` = comma-separated list of
         numeric user ids allowed to send command messages back to the agent.
    """

    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        admin_ids: List[str] | None = None,
        repo_root: str = "",
    ) -> None:
        self.bot_token = bot_token or ""
        self.chat_id = chat_id or ""
        self.admin_ids = [str(x).strip() for x in (admin_ids or []) if str(x).strip()]
        self.repo_root = repo_root
        self._log = get_logger("mcp.servers.telegram")
        if self.bot_token:
            prefix = self.bot_token.split(":", 1)[0]
            self._log.info("telegram_configured", bot_prefix=prefix, chat_id=self.chat_id, admins=len(self.admin_ids))
        else:
            self._log.warning("telegram_missing_credentials", hint="Set TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID")

    def exposed_tools(self) -> List[Tool]:
        return [
            Tool(
                name="send_message",
                description="Send a text message to Telegram chat. Default chat = TELEGRAM_CHAT_ID. HTML parse_mode default.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "chat_id": {"type": "string"},
                        "text": {"type": "string"},
                        "parse_mode": {"type": "string", "enum": ["HTML", "MarkdownV2", "Markdown"]},
                        "disable_web_page_preview": {"type": "boolean"},
                        "disable_notification": {"type": "boolean"},
                        "pin": {"type": "boolean"},
                    },
                    "required": ["text"],
                },
                server="telegram",
            ),
            Tool(
                name="send_alert",
                description="Priority alert routed to Telegram. P0 pinned+sound; P1 sound; P2/P3 silent.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "priority": {"type": "string", "enum": ["P0_CRITICAL", "P1_ACTION", "P2_UPDATE", "P3_INFO"]},
                        "title": {"type": "string"},
                        "body": {"type": "string"},
                        "action_items": {"type": "array", "items": {"type": "string"}},
                        "chat_id": {"type": "string"},
                    },
                    "required": ["title", "body"],
                },
                server="telegram",
            ),
            Tool(
                name="send_digest",
                description="Task-status / knowledge-crystal / integration-health digest.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "tasks": {"type": "array", "items": {"type": "object"}},
                        "crystals": {"type": "array", "items": {"type": "string"}},
                        "integrations": {"type": "array", "items": {"type": "object"}},
                        "chat_id": {"type": "string"},
                    },
                    "required": ["tasks"],
                },
                server="telegram",
            ),
            Tool(
                name="send_document",
                description="Upload a document (written to /tmp) as Telegram file.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "chat_id": {"type": "string"},
                        "caption": {"type": "string"},
                        "document_filename": {"type": "string"},
                        "document_text": {"type": "string"},
                        "parse_mode": {"type": "string", "enum": ["HTML", "MarkdownV2", "Markdown"]},
                    },
                    "required": ["document_filename", "document_text"],
                },
                server="telegram",
            ),
            Tool(
                name="pin_message",
                description="Pin a message by message_id.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "chat_id": {"type": "string"},
                        "message_id": {"type": "integer"},
                        "disable_notification": {"type": "boolean"},
                    },
                    "required": ["message_id"],
                },
                server="telegram",
            ),
            Tool(
                name="get_updates",
                description="Fetch recent Telegram updates (for /cancel /status commands).",
                input_schema={
                    "type": "object",
                    "properties": {
                        "offset": {"type": "integer"},
                        "limit": {"type": "integer"},
                        "timeout": {"type": "integer"},
                    },
                },
                server="telegram",
            ),
        ]

    def server_command(self) -> Tuple[str, List[str], Dict[str, Any]]:
        cmd = "node"
        args = ["-e", _TELEGRAM_SHIM_CODE]
        env = {
            "TELEGRAM_BOT_TOKEN": self.bot_token,
            "TELEGRAM_CHAT_ID": self.chat_id,
            "TELEGRAM_ADMIN_IDS": ",".join(self.admin_ids),
            "NODE_PATH": os.environ.get("NODE_PATH", ""),
        }
        return cmd, args, env

    async def start(self) -> asyncio.subprocess.Process:
        cmd, args, env = self.server_command()
        merged_env = os.environ.copy()
        merged_env.update(env)
        proc = await asyncio.create_subprocess_exec(
            cmd,
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=merged_env,
        )
        self._log.info("telegram_server_started", pid=proc.pid, configured=bool(self.bot_token))
        return proc
