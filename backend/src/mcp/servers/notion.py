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
        # Names/schemas MUST match what @notionhq/notion-mcp-server (the
        # official Notion MCP) actually serves — verified via tools/list.
        # Page creation against the default DB was verified live with
        # parent={"database_id": ...}.
        return [
            Tool(
                name="API-post-search",
                description="Search Notion pages and databases by title",
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "page_size": {"type": "integer", "default": 20},
                    },
                    "required": ["query"],
                },
                server="notion",
            ),
            Tool(
                name="API-post-page",
                description=(
                    "Create a Notion page. parent: {\"database_id\": id} or "
                    "{\"page_id\": id}; properties uses the Notion API shape "
                    "(title: {title: [{text: {content: ...}}]}); children is a "
                    "list of block objects."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "parent": {"type": "object"},
                        "properties": {"type": "object"},
                        "children": {"type": "array", "items": {"type": "object"}},
                    },
                    "required": ["parent", "properties"],
                },
                server="notion",
            ),
            Tool(
                name="API-retrieve-a-page",
                description="Retrieve a Notion page's properties",
                input_schema={
                    "type": "object",
                    "properties": {"page_id": {"type": "string"}},
                    "required": ["page_id"],
                },
                server="notion",
            ),
            Tool(
                name="API-retrieve-page-markdown",
                description="Read a Notion page's full content as markdown",
                input_schema={
                    "type": "object",
                    "properties": {"page_id": {"type": "string"}},
                    "required": ["page_id"],
                },
                server="notion",
            ),
            Tool(
                name="API-patch-page",
                description="Update a Notion page's properties",
                input_schema={
                    "type": "object",
                    "properties": {
                        "page_id": {"type": "string"},
                        "properties": {"type": "object"},
                    },
                    "required": ["page_id", "properties"],
                },
                server="notion",
            ),
            Tool(
                name="API-get-block-children",
                description="List the child blocks (content) of a page or block",
                input_schema={
                    "type": "object",
                    "properties": {
                        "block_id": {"type": "string"},
                        "page_size": {"type": "integer", "default": 50},
                    },
                    "required": ["block_id"],
                },
                server="notion",
            ),
            Tool(
                name="API-query-data-source",
                description="Query pages in a Notion data source (database) with filters",
                input_schema={
                    "type": "object",
                    "properties": {
                        "data_source_id": {"type": "string"},
                        "filter": {"type": "object"},
                        "sorts": {"type": "array", "items": {"type": "object"}},
                        "page_size": {"type": "integer", "default": 50},
                    },
                    "required": ["data_source_id"],
                },
                server="notion",
            ),
        ]

    def server_command(self) -> Tuple[str, List[str], dict]:
        cmd = "npx"
        args = ["-y", "@notionhq/notion-mcp-server"]
        env = {
            "NOTION_TOKEN": self.token,
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
