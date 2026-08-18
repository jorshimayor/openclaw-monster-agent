from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.config import Settings
from src.mcp.manager import McpServerManager, SUPPORTED_SERVERS
from src.mcp.registry import McpToolRegistry


@pytest.fixture
def test_settings() -> Settings:
    return Settings(
        github_token="test_gh_token",
        notion_token="test_notion_token",
        notion_db_id="test_notion_db",
        slack_token="test_slack_token",
        slack_channel="#test",
        google_workspace_client_id="test_gw_client",
        google_workspace_client_secret="test_gw_secret",
        hashnode_token="test_hn_token",
        hashnode_publication_id="test_hn_pub",
    )


class FakeProcess:
    def __init__(self) -> None:
        self.pid = 12345
        self.returncode = None
        self.stdin = MagicMock()
        self.stdin.write = MagicMock()
        self.stdin.drain = AsyncMock()
        self.stdout = MagicMock()
        self.stderr = MagicMock()
        self._killed = False

    async def wait(self) -> int:
        return 0 if not self._killed else -1

    def terminate(self) -> None:
        self.returncode = 0

    def kill(self) -> None:
        self._killed = True
        self.returncode = -1


@pytest.fixture
def manager_with_mocked_subprocess(test_settings: Settings) -> McpServerManager:
    manager = McpServerManager(test_settings)
    return manager


def test_manager_init_creates_registry(test_settings: Settings) -> None:
    manager = McpServerManager(test_settings)
    assert isinstance(manager.registry, McpToolRegistry)
    assert manager.settings is test_settings
    assert manager._processes == {}
    assert manager._transports == {}


@pytest.mark.asyncio
async def test_probe_server_unknown_raises(
    manager_with_mocked_subprocess: McpServerManager,
) -> None:
    with pytest.raises(ValueError, match="Unknown MCP server"):
        await manager_with_mocked_subprocess.probe_server("does_not_exist")


@pytest.mark.asyncio
async def test_get_server_statuses_returns_5_servers(
    manager_with_mocked_subprocess: McpServerManager,
) -> None:
    statuses = manager_with_mocked_subprocess.get_server_statuses()
    assert len(statuses) == len(SUPPORTED_SERVERS)
    names = [s.name for s in statuses]
    for expected in SUPPORTED_SERVERS:
        assert expected in names
    for s in statuses:
        assert s.status in {"down", "degraded", "healthy"}
        assert isinstance(s.tools_available, int)
        assert s.tools_available >= 0


@pytest.mark.asyncio
async def test_start_all_registers_tools_with_mocked_spawn(
    test_settings: Settings,
) -> None:
    fake_proc = FakeProcess()
    with patch(
        "src.mcp.manager.asyncio.create_subprocess_exec",
        new_callable=AsyncMock,
        return_value=fake_proc,
    ):
        manager = McpServerManager(test_settings)
        try:
            await manager.start_all()
        except Exception:
            pass
    all_tools = manager.registry.list_all_tools()
    for server in SUPPORTED_SERVERS:
        assert server in all_tools
        assert len(all_tools[server]) >= 1
