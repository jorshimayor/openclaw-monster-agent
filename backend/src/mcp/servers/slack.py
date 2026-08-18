from __future__ import annotations

import asyncio
import os
from typing import List, Tuple

from ...core.logging import get_logger
from ..registry import Tool

logger = get_logger("mcp.servers.slack")

_SLACK_SHIM_CODE = r"""
const readline = require('readline');
const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
const pending = new Map();
let idCounter = 0;

function send(obj) {
  process.stdout.write(JSON.stringify(obj) + '\n');
}

function respond(id, result) {
  send({ jsonrpc: '2.0', id, result });
}

function respondError(id, code, message) {
  send({ jsonrpc: '2.0', id, error: { code, message } });
}

rl.on('line', (line) => {
  let req;
  try { req = JSON.parse(line); } catch (e) { return; }
  const { id, method, params } = req;
  if (method === 'ping') {
    respond(id, { pong: true });
  } else if (method === 'initialize') {
    respond(id, { protocolVersion: '2024-11-05', capabilities: {}, serverInfo: { name: 'slack-shim', version: '1.0.0' } });
  } else if (method === 'tools/list') {
    respond(id, { tools: [
      { name: 'send_message', description: 'Send message to Slack channel', inputSchema: { type: 'object', properties: { channel: { type: 'string' }, text: { type: 'string' } }, required: ['text'] } },
      { name: 'list_channels', description: 'List Slack channels', inputSchema: { type: 'object', properties: { limit: { type: 'integer', default: 50 } } } },
      { name: 'post_update', description: 'Post an update to the default channel', inputSchema: { type: 'object', properties: { text: { type: 'string' }, blocks: { type: 'array' } }, required: ['text'] } },
    ]});
  } else if (method === 'tools/call') {
    const name = params && params.name;
    respond(id, { ok: true, tool: name, stub: true, channel: process.env.SLACK_DEFAULT_CHANNEL || '#general' });
  } else {
    respondError(id, -32601, `Method not found: ${method}`);
  }
});
"""


class SlackMcpServer:
    """Slack MCP server wrapper with dual-token support.

    Token selection rules (applied in order):
      1. If ``bot_token`` is set (SLACK_BOT_TOKEN, starts with ``xoxb-``) → use it.
         Bot tokens act as the bot user and need channel invites + scopes
         ``chat:write`` and ``channels:read``.
      2. Otherwise use ``user_token`` (SLACK_USER_TOKEN, starts with ``xoxp-``).
         User tokens act as YOUR user identity and inherit your permissions.
      3. If neither is set → fall back to the empty string and let the shim log
         a graceful no-op during tool calls.

    Both tokens are passed through to the shim as env vars so future tools can
    use the right token for the right method (e.g. list_channels often needs
    user-level scope for private channels the bot isn't in).
    """

    def __init__(
        self,
        bot_token: str = "",
        user_token: str = "",
        default_channel: str = "#agent-updates",
    ) -> None:
        self.bot_token = bot_token
        self.user_token = user_token
        self.default_channel = default_channel
        self._log = get_logger("mcp.servers.slack")
        self._selected_token, self._selected_kind = self._resolve_token()

    def _resolve_token(self) -> Tuple[str, str]:
        if self.bot_token:
            self._log.info("slack_token_selected", kind="bot", prefix=self.bot_token[:4])
            return self.bot_token, "bot"
        if self.user_token:
            self._log.info("slack_token_selected", kind="user", prefix=self.user_token[:4])
            return self.user_token, "user"
        self._log.warning("slack_token_missing", hint="Set SLACK_BOT_TOKEN or SLACK_USER_TOKEN")
        return "", "none"

    def selected_token(self) -> Tuple[str, str]:
        """Public read-back: returns (token_string, kind ∈ {bot,user,none})."""
        return self._selected_token, self._selected_kind

    def exposed_tools(self) -> List[Tool]:
        return [
            Tool(
                name="send_message",
                description="Send a direct message to a Slack channel or user",
                input_schema={
                    "type": "object",
                    "properties": {
                        "channel": {"type": "string"},
                        "text": {"type": "string"},
                        "blocks": {"type": "array", "items": {"type": "object"}},
                    },
                    "required": ["text"],
                },
                server="slack",
            ),
            Tool(
                name="list_channels",
                description="List accessible Slack channels in the workspace",
                input_schema={
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "default": 50},
                        "exclude_archived": {"type": "boolean", "default": True},
                    },
                },
                server="slack",
            ),
            Tool(
                name="post_update",
                description="Post a status update to the default Slack channel",
                input_schema={
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "blocks": {"type": "array", "items": {"type": "object"}},
                    },
                    "required": ["text"],
                },
                server="slack",
            ),
        ]

    def server_command(self) -> Tuple[str, List[str], dict]:
        cmd = "node"
        args = ["-e", _SLACK_SHIM_CODE]
        env = {
            "SLACK_BOT_TOKEN": self.bot_token,
            "SLACK_USER_TOKEN": self.user_token,
            "SLACK_TOKEN": self._selected_token,
            "SLACK_DEFAULT_CHANNEL": self.default_channel,
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
        self._log.info("slack_server_started", pid=proc.pid)
        return proc
