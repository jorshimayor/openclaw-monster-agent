from __future__ import annotations

import asyncio
import os
from typing import List, Tuple

from ...core.logging import get_logger
from ..registry import Tool

logger = get_logger("mcp.servers.hashnode")


class HashnodeMcpServer:
    def __init__(self, token: str, publication_id: str, repo_root: str) -> None:
        self.token = token
        self.publication_id = publication_id
        self.repo_root = repo_root
        self._log = get_logger("mcp.servers.hashnode")

    def exposed_tools(self) -> List[Tool]:
        return [
            Tool(
                name="publish_post",
                description="Publish a new post to Hashnode publication",
                input_schema={
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "content_markdown": {"type": "string"},
                        "slug": {"type": "string"},
                        "tags": {"type": "array", "items": {"type": "object"}},
                        "cover_image_url": {"type": "string"},
                        "published_at": {"type": "string"},
                    },
                    "required": ["title", "content_markdown"],
                },
                server="hashnode",
            ),
            Tool(
                name="manage_drafts",
                description="List, update, or schedule Hashnode post drafts",
                input_schema={
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["list", "update", "schedule", "delete"],
                            "default": "list",
                        },
                        "draft_id": {"type": "string"},
                        "title": {"type": "string"},
                        "content_markdown": {"type": "string"},
                    },
                    "required": ["action"],
                },
                server="hashnode",
            ),
            Tool(
                name="read_posts",
                description="Read and search published posts from Hashnode publication",
                input_schema={
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "default": 20},
                        "page": {"type": "integer", "default": 1},
                        "query": {"type": "string"},
                        "tag": {"type": "string"},
                    },
                },
                server="hashnode",
            ),
        ]

    def server_command(self) -> Tuple[str, List[str], dict]:
        server_path = os.path.join(
            self.repo_root, "mcp-servers", "hashnode", "dist", "index.js"
        )
        cmd = "node"
        args = [server_path]
        env = {
            "HASHNODE_TOKEN": self.token,
            "HASHNODE_PUBLICATION_ID": self.publication_id,
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
        self._log.info("hashnode_server_started", pid=proc.pid)
        return proc
