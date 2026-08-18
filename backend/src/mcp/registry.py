from __future__ import annotations

from fnmatch import fnmatch
from typing import Dict, List

from pydantic import BaseModel


class Tool(BaseModel):
    name: str
    description: str
    input_schema: dict
    server: str


class McpToolRegistry:
    def __init__(self) -> None:
        self._servers: Dict[str, List[Tool]] = {}

    def register_server(self, server_name: str, tools: List[Tool]) -> None:
        self._servers[server_name] = list(tools)

    def unregister_server(self, server_name: str) -> None:
        if server_name in self._servers:
            del self._servers[server_name]

    def list_all_tools(self) -> Dict[str, List[Tool]]:
        return {name: list(tools) for name, tools in self._servers.items()}

    def get_tools_for_agent(self, agent_tool_allowlist: List[str]) -> List[Tool]:
        matched: List[Tool] = []
        seen: set[tuple[str, str]] = set()
        for server_tools in self._servers.values():
            for tool in server_tools:
                qualified = f"{tool.server}.{tool.name}"
                for pattern in agent_tool_allowlist:
                    if fnmatch(qualified, pattern) or fnmatch(tool.name, pattern):
                        key = (tool.server, tool.name)
                        if key not in seen:
                            seen.add(key)
                            matched.append(tool)
                        break
        return matched
