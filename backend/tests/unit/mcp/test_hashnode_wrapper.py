import os
from unittest.mock import patch

import pytest

from src.mcp.servers.hashnode import HashnodeMcpServer
from src.mcp.registry import Tool


class TestHashnodeMcpServer:
    @pytest.fixture
    def server(self) -> HashnodeMcpServer:
        return HashnodeMcpServer(
            token="test-token-abc",
            publication_id="pub-123",
            repo_root="/absolute/repo/root",
        )

    def test_server_command_uses_absolute_path(self, server: HashnodeMcpServer) -> None:
        cmd, args, env = server.server_command()

        assert cmd == "node"
        assert len(args) == 1
        server_path = args[0]
        assert os.path.isabs(server_path), (
            f"Expected server path to be absolute, got: {server_path}"
        )
        assert server_path == "/absolute/repo/root/mcp-servers/hashnode/dist/index.js"
        assert server_path.endswith(os.path.join("mcp-servers", "hashnode", "dist", "index.js"))

        assert env["HASHNODE_TOKEN"] == "test-token-abc"
        assert env["HASHNODE_PUBLICATION_ID"] == "pub-123"

    def test_server_command_respects_dynamic_repo_root(self) -> None:
        custom_root = "/Users/me/projects/my-monorepo"
        server = HashnodeMcpServer(
            token="t",
            publication_id="p",
            repo_root=custom_root,
        )
        _, args, _ = server.server_command()
        assert args[0] == os.path.join(
            custom_root, "mcp-servers", "hashnode", "dist", "index.js"
        )

    def test_exposed_tools_has_3_entries(self, server: HashnodeMcpServer) -> None:
        tools = server.exposed_tools()
        assert isinstance(tools, list)
        assert len(tools) == 3

        names = [t.name for t in tools]
        assert names == ["publish_post", "manage_drafts", "read_posts"]

        for tool in tools:
            assert isinstance(tool, Tool)
            assert tool.server == "hashnode"
            assert isinstance(tool.description, str)
            assert tool.description
            assert isinstance(tool.input_schema, dict)
            assert tool.input_schema.get("type") == "object"

    def test_exposed_tools_publish_post_schema(self, server: HashnodeMcpServer) -> None:
        tools = {t.name: t for t in server.exposed_tools()}
        publish = tools["publish_post"]
        assert "title" in publish.input_schema["properties"]
        assert "content_markdown" in publish.input_schema["properties"]
        assert "title" in publish.input_schema.get("required", [])
        assert "content_markdown" in publish.input_schema.get("required", [])

    def test_exposed_tools_manage_drafts_schema(self, server: HashnodeMcpServer) -> None:
        tools = {t.name: t for t in server.exposed_tools()}
        drafts = tools["manage_drafts"]
        props = drafts.input_schema["properties"]
        assert "action" in props
        assert props["action"].get("enum") is not None
        assert "action" in drafts.input_schema.get("required", [])

    def test_exposed_tools_read_posts_schema(self, server: HashnodeMcpServer) -> None:
        tools = {t.name: t for t in server.exposed_tools()}
        read = tools["read_posts"]
        assert "limit" in read.input_schema["properties"]
        assert "page" in read.input_schema["properties"]

    @patch("asyncio.create_subprocess_exec")
    @pytest.mark.asyncio
    async def test_start_uses_server_command_env(
        self, mock_exec, server: HashnodeMcpServer
    ) -> None:
        mock_exec.return_value.pid = 9999

        with patch.dict(os.environ, {"PATH": "/usr/bin"}, clear=True):
            await server.start()

        mock_exec.assert_called_once()
        call_kwargs = mock_exec.call_args
        merged_env = call_kwargs.kwargs["env"]
        assert merged_env["HASHNODE_TOKEN"] == "test-token-abc"
        assert merged_env["HASHNODE_PUBLICATION_ID"] == "pub-123"
        assert "PATH" in merged_env
