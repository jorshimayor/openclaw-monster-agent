from __future__ import annotations

import asyncio
import os
from typing import List, Tuple

from ...core.logging import get_logger
from ..registry import Tool

logger = get_logger("mcp.servers.github")


class GithubMcpServer:
    def __init__(self, token: str) -> None:
        self.token = token
        self._log = get_logger("mcp.servers.github")

    def exposed_tools(self) -> List[Tool]:
        return [
            # Tool names/schemas MUST match what @modelcontextprotocol/server-github
            # actually serves (verified via tools/list) — a declared name the real
            # server doesn't know fails every agent call with "Unknown tool".
            Tool(
                name="get_file_contents",
                description="Read a file or directory listing from a repository",
                input_schema={
                    "type": "object",
                    "properties": {
                        "owner": {"type": "string"},
                        "repo": {"type": "string"},
                        "path": {"type": "string"},
                        "branch": {"type": "string"},
                    },
                    "required": ["owner", "repo", "path"],
                },
                server="github",
            ),
            Tool(
                name="search_repositories",
                description="Search GitHub repositories",
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "page": {"type": "integer"},
                        "perPage": {"type": "integer"},
                    },
                    "required": ["query"],
                },
                server="github",
            ),
            Tool(
                name="list_commits",
                description="List recent commits for a repository",
                input_schema={
                    "type": "object",
                    "properties": {
                        "owner": {"type": "string"},
                        "repo": {"type": "string"},
                        "sha": {"type": "string"},
                        "page": {"type": "integer"},
                        "perPage": {"type": "integer"},
                    },
                    "required": ["owner", "repo"],
                },
                server="github",
            ),
            Tool(
                name="list_pull_requests",
                description="List open and recent pull requests",
                input_schema={
                    "type": "object",
                    "properties": {
                        "owner": {"type": "string"},
                        "repo": {"type": "string"},
                        "state": {
                            "type": "string",
                            "enum": ["open", "closed", "all"],
                            "default": "open",
                        },
                    },
                    "required": ["owner", "repo"],
                },
                server="github",
            ),
            Tool(
                name="create_issue",
                description="Create a new issue in a repository",
                input_schema={
                    "type": "object",
                    "properties": {
                        "owner": {"type": "string"},
                        "repo": {"type": "string"},
                        "title": {"type": "string"},
                        "body": {"type": "string"},
                        "labels": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["owner", "repo", "title"],
                },
                server="github",
            ),
        ]

    def server_command(self) -> Tuple[str, List[str], dict]:
        cmd = "npx"
        args = ["-y", "@modelcontextprotocol/server-github"]
        env = {
            "GITHUB_PERSONAL_ACCESS_TOKEN": self.token,
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
        self._log.info("github_server_started", pid=proc.pid)
        return proc
