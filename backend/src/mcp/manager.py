from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel
from tenacity import AsyncRetrying, stop_after_attempt, wait_exponential

from ..core.config import Settings
from ..core.logging import get_logger
from .registry import McpToolRegistry, Tool
from .servers.github import GithubMcpServer
from .servers.google_workspace import GoogleWorkspaceMcpServer
from .servers.notion import NotionMcpServer
from .servers.slack import SlackMcpServer
from .servers.telegram import TelegramMcpServer

logger = get_logger("mcp.manager")

SUPPORTED_SERVERS: List[str] = [
    "github",
    "notion",
    "google_workspace",
    "slack",
    "telegram",
]


class McpServerStatus(BaseModel):
    name: str
    status: str
    tools_available: int
    last_probe: Optional[str]


class McpStdioTransport:
    def __init__(
        self,
        proc: asyncio.subprocess.Process,
        server_name: str,
        read_timeout: float = 30.0,
    ) -> None:
        self._proc = proc
        self._server_name = server_name
        self._read_timeout = read_timeout
        self._pending: Dict[str, asyncio.Future[dict]] = {}
        self._reader_task: Optional[asyncio.Task[None]] = None
        self._lock = asyncio.Lock()
        self._log = get_logger(f"mcp.transport.{server_name}")

    async def start(self) -> None:
        if self._reader_task is None:
            self._reader_task = asyncio.create_task(self._read_loop())

    async def close(self) -> None:
        if self._reader_task is not None:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
            self._reader_task = None
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(ConnectionError("Transport closed"))
        self._pending.clear()

    async def _read_loop(self) -> None:
        assert self._proc.stdout is not None
        while True:
            try:
                raw = await asyncio.wait_for(
                    self._proc.stdout.readline(),
                    timeout=self._read_timeout,
                )
            except asyncio.TimeoutError:
                continue
            if not raw:
                self._log.debug("stdio_eof")
                break
            line = raw.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                self._log.warning("bad_json_line", line_preview=line[:120])
                continue
            await self._handle_message(message)

    async def _handle_message(self, message: dict) -> None:
        msg_id = message.get("id")
        if msg_id is not None and msg_id in self._pending:
            fut = self._pending.pop(msg_id)
            if "error" in message:
                fut.set_exception(RuntimeError(str(message["error"])))
            else:
                fut.set_result(message.get("result", {}))
        elif msg_id is not None:
            self._log.debug("orphan_response", msg_id=msg_id)
        else:
            self._log.debug("notification", method=message.get("method"))

    async def call(self, method: str, params: Optional[dict] = None) -> dict:
        msg_id = str(uuid.uuid4())
        payload: Dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": msg_id,
            "method": method,
        }
        if params is not None:
            payload["params"] = params
        line = json.dumps(payload) + "\n"
        loop = asyncio.get_event_loop()
        future: asyncio.Future[dict] = loop.create_future()
        self._pending[msg_id] = future
        try:
            async with self._lock:
                assert self._proc.stdin is not None
                self._proc.stdin.write(line.encode("utf-8"))
                await self._proc.stdin.drain()
            return await asyncio.wait_for(future, timeout=self._read_timeout)
        finally:
            if msg_id in self._pending:
                self._pending.pop(msg_id, None)


class McpServerManager:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.registry = McpToolRegistry()
        self._processes: Dict[str, asyncio.subprocess.Process] = {}
        self._transports: Dict[str, McpStdioTransport] = {}
        self._specs: Dict[str, Dict[str, Any]] = {}
        self._probe_results: Dict[str, Dict[str, Any]] = {}
        self._log = get_logger("mcp.manager")

    def _build_server_specs(self) -> Dict[str, Dict[str, Any]]:
        repo_root = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
        )
        return {
            "github": {
                "instance": GithubMcpServer(token=self.settings.github_token),
            },
            "notion": {
                "instance": NotionMcpServer(
                    token=self.settings.notion_token,
                    db_id=self.settings.notion_db_id,
                ),
            },
            "google_workspace": {
                "instance": GoogleWorkspaceMcpServer(
                    client_id=self.settings.google_workspace_client_id,
                    client_secret=self.settings.google_workspace_client_secret,
                    refresh_token=self.settings.google_workspace_refresh_token,
                    subject_email=self.settings.google_workspace_subject_email,
                ),
            },
            "slack": {
                "instance": SlackMcpServer(
                    bot_token=self.settings.slack_bot_token,
                    user_token=self.settings.slack_user_token,
                    default_channel=self.settings.slack_channel,
                ),
            },
            "telegram": {
                "instance": TelegramMcpServer(
                    bot_token=self.settings.telegram_bot_token,
                    chat_id=self.settings.telegram_chat_id,
                    admin_ids=self.settings.telegram_admin_ids,
                    repo_root=repo_root,
                ),
            },
        }

    async def start_all(self) -> None:
        self._specs = self._build_server_specs()
        for server_name in SUPPORTED_SERVERS:
            try:
                await self._start_single(server_name)
            except Exception as exc:
                self._log.exception(
                    "server_start_failed",
                    server=server_name,
                    error=str(exc),
                )

    async def _start_single(self, server_name: str) -> None:
        spec = self._specs[server_name]
        instance = spec["instance"]
        cmd, args, env = instance.server_command()
        merged_env = os.environ.copy()
        merged_env.update(env or {})
        try:
            proc = await asyncio.create_subprocess_exec(
                cmd,
                *args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=merged_env,
            )
        except Exception as exc:
            self._log.error(
                "spawn_failed",
                server=server_name,
                cmd=cmd,
                args=args,
                error=str(exc),
            )
            raise
        transport = McpStdioTransport(proc, server_name)
        await transport.start()
        self._processes[server_name] = proc
        self._transports[server_name] = transport
        try:
            tools = instance.exposed_tools()
        except Exception as exc:
            self._log.warning(
                "tools_enumeration_failed",
                server=server_name,
                error=str(exc),
            )
            tools = []
        self.registry.register_server(server_name, tools)
        self._log.info(
            "server_started",
            server=server_name,
            tools_registered=len(tools),
            pid=proc.pid,
        )

    async def stop_all(self) -> None:
        for server_name in list(self._processes.keys()):
            try:
                await self._stop_single(server_name)
            except Exception as exc:
                self._log.exception(
                    "server_stop_failed",
                    server=server_name,
                    error=str(exc),
                )

    async def _stop_single(self, server_name: str) -> None:
        transport = self._transports.pop(server_name, None)
        if transport is not None:
            try:
                await transport.close()
            except Exception:
                pass
        proc = self._processes.pop(server_name, None)
        if proc is not None:
            try:
                proc.terminate()
            except Exception:
                pass
            try:
                await asyncio.wait_for(proc.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                try:
                    proc.kill()
                except Exception:
                    pass
                try:
                    await proc.wait()
                except Exception:
                    pass
        self.registry.unregister_server(server_name)
        self._log.info("server_stopped", server=server_name)

    async def health_check(self, server_name: str) -> Tuple[bool, str]:
        transport = self._transports.get(server_name)
        if transport is None:
            return False, f"No transport for server '{server_name}'"
        proc = self._processes.get(server_name)
        if proc is None or proc.returncode is not None:
            return False, "Process not running"
        try:
            start = time.perf_counter()
            await transport.call("ping", {})
            latency_ms = int((time.perf_counter() - start) * 1000)
            return True, f"OK ({latency_ms}ms)"
        except Exception as exc:
            return False, f"ping failed: {exc}"

    async def probe_server(self, server_name: str) -> Dict[str, Any]:
        if server_name not in SUPPORTED_SERVERS:
            raise ValueError(f"Unknown MCP server '{server_name}'")
        if server_name not in self._transports:
            raise RuntimeError(f"Server '{server_name}' not started")
        tools = self.registry.list_all_tools().get(server_name, [])
        sample_tool = tools[0] if tools else None
        start = time.perf_counter()
        sample_result: Any = None
        ok = False
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(2),
            wait=wait_exponential(multiplier=0.2, min=0.1, max=0.5),
            reraise=False,
        ):
            with attempt:
                transport = self._transports[server_name]
                if sample_tool is not None:
                    try:
                        sample_result = await transport.call(
                            "tools/call",
                            {
                                "name": sample_tool.name,
                                "arguments": {},
                            },
                        )
                    except Exception as exc:
                        sample_result = {"probe_error": str(exc)}
                else:
                    sample_result = await transport.call("ping", {})
                ok = True
        latency_ms = int((time.perf_counter() - start) * 1000)
        result = {
            "server": server_name,
            "tool_count": len(tools),
            "sample_result": sample_result,
            "latency_ms": latency_ms,
        }
        self._probe_results[server_name] = {
            **result,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "ok": ok,
        }
        return result

    def get_server_statuses(self) -> List[McpServerStatus]:
        results: List[McpServerStatus] = []
        all_tools = self.registry.list_all_tools()
        for server_name in SUPPORTED_SERVERS:
            tools = all_tools.get(server_name, [])
            probe = self._probe_results.get(server_name)
            last_probe = probe["timestamp"] if probe else None
            status = "down"
            if probe and probe.get("ok"):
                status = "healthy"
            elif server_name in self._processes:
                proc = self._processes[server_name]
                if proc.returncode is None:
                    status = "degraded"
            results.append(
                McpServerStatus(
                    name=server_name,
                    status=status,
                    tools_available=len(tools),
                    last_probe=last_probe,
                )
            )
        return results

    async def restart_server(self, server_name: str) -> None:
        if server_name not in SUPPORTED_SERVERS:
            raise ValueError(f"Unknown MCP server '{server_name}'")
        try:
            await self._stop_single(server_name)
        except Exception as exc:
            self._log.warning(
                "restart_stop_warning",
                server=server_name,
                error=str(exc),
            )
        await self._start_single(server_name)
