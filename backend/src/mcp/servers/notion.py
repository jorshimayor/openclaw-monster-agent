from __future__ import annotations

import asyncio
import os
from typing import List, Tuple

from ...core.logging import get_logger
from ..registry import Tool

logger = get_logger("mcp.servers.notion")


class NotionMcpServer:
    def __init__(self, token: str, db_id: str) -> None:
        self.token = token
        self.db_id = db_id
        self._log = get_logger("mcp.servers.notion")

    def exposed_tools(self) -> List[Tool]:
        return [
            Tool(
                name="read_page",
                description="Read the content and properties of a Notion page",
                input_schema={
                    "type": "object",
                    "properties": {
                        "page_id": {"type": "string"},
                    },
                    "required": ["page_id"],
                },
                server="notion",
            ),
            Tool(
                name="create_page",
                description="Create a new page in the default database",
                input_schema={
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "content": {"type": "string"},
                        "properties": {"type": "object"},
                    },
                    "required": ["title"],
                },
                server="notion",
            ),
            Tool(
                name="update_page",
                description="Update an existing Notion page content or properties",
                input_schema={
                    "type": "object",
                    "properties": {
                        "page_id": {"type": "string"},
                        "title": {"type": "string"},
                        "content": {"type": "string"},
                        "properties": {"type": "object"},
                    },
                    "required": ["page_id"],
                },
                server="notion",
            ),
            Tool(
                name="query_db",
                description="Query pages in the Notion database with filters",
                input_schema={
                    "type": "object",
                    "properties": {
                        "database_id": {"type": "string"},
                        "filter": {"type": "object"},
                        "sorts": {"type": "array", "items": {"type": "object"}},
                        "limit": {"type": "integer", "default": 50},
                    },
                    "required": ["database_id"],
                },
                server="notion",
            ),
        ]

    def server_command(self) -> Tuple[str, List[str], dict]:
        cmd = "npx"
        args = ["-y", "@shck-dev/notion-mcp"]
        env = {
            "NOTION_TOKEN": self.token,
            "NOTION_DB_ID": self.db_id,
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
        self._log.info("notion_server_started", pid=proc.pid)
        return proc
