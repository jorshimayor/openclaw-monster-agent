from __future__ import annotations

import asyncio
import os
from typing import List, Optional, Tuple

from ...core.logging import get_logger
from ..registry import Tool

logger = get_logger("mcp.servers.google_workspace")


class GoogleWorkspaceMcpServer:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        refresh_token: Optional[str] = None,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token or ""
        self._log = get_logger("mcp.servers.google_workspace")

    def exposed_tools(self) -> List[Tool]:
        return [
            Tool(
                name="create_doc",
                description="Create a new Google Doc with title and optional content",
                input_schema={
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "content": {"type": "string"},
                        "folder_id": {"type": "string"},
                    },
                    "required": ["title"],
                },
                server="google_workspace",
            ),
            Tool(
                name="read_doc",
                description="Read the contents of an existing Google Doc",
                input_schema={
                    "type": "object",
                    "properties": {
                        "doc_id": {"type": "string"},
                    },
                    "required": ["doc_id"],
                },
                server="google_workspace",
            ),
            Tool(
                name="append_to_doc",
                description="Append text content to the end of a Google Doc",
                input_schema={
                    "type": "object",
                    "properties": {
                        "doc_id": {"type": "string"},
                        "content": {"type": "string"},
                    },
                    "required": ["doc_id", "content"],
                },
                server="google_workspace",
            ),
            Tool(
                name="read_calendar",
                description="Read events from Google Calendar within a date range",
                input_schema={
                    "type": "object",
                    "properties": {
                        "calendar_id": {"type": "string", "default": "primary"},
                        "time_min": {"type": "string"},
                        "time_max": {"type": "string"},
                        "max_results": {"type": "integer", "default": 50},
                    },
                    "required": ["time_min", "time_max"],
                },
                server="google_workspace",
            ),
            Tool(
                name="write_sheet",
                description="Write values to a range in a Google Sheet",
                input_schema={
                    "type": "object",
                    "properties": {
                        "sheet_id": {"type": "string"},
                        "range": {"type": "string"},
                        "values": {
                            "type": "array",
                            "items": {
                                "type": "array",
                                "items": {"type": ["string", "number", "boolean"]},
                            },
                        },
                    },
                    "required": ["sheet_id", "range", "values"],
                },
                server="google_workspace",
            ),
            Tool(
                name="read_sheet",
                description="Read values from a range in a Google Sheet",
                input_schema={
                    "type": "object",
                    "properties": {
                        "sheet_id": {"type": "string"},
                        "range": {"type": "string"},
                    },
                    "required": ["sheet_id", "range"],
                },
                server="google_workspace",
            ),
        ]

    def server_command(self) -> Tuple[str, List[str], dict]:
        cmd = "npx"
        args = ["-y", "workspace-mcp"]
        env = {
            "GOOGLE_CLIENT_ID": self.client_id,
            "GOOGLE_CLIENT_SECRET": self.client_secret,
            "GOOGLE_REFRESH_TOKEN": self.refresh_token,
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
        self._log.info("google_workspace_server_started", pid=proc.pid)
        return proc
