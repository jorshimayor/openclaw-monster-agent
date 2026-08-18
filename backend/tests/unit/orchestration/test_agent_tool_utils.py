from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from src.agents._utils import _call_tool, tool_matches
from src.agents.content_web2 import ContentWeb2Agent
from src.agents.knowledge_crystallizer import KnowledgeCrystallizerAgent
from src.agents.base import Tool
from src.core.types import AgentRole, KnowledgeCrystals
from src.knowledge.extractor import KnowledgeExtractor


pytestmark = pytest.mark.asyncio


async def test_call_tool_no_transport_returns_skipped():
    result = await _call_tool("github.read_repo", {"repo": "test/repo"}, transport=None)
    assert result == {"skipped": True, "reason": "no_mcp_transport"}


def test_tool_matches_globs():
    allowlist = ["github.*", "notion.create_page", "google_workspace.*_doc"]

    assert tool_matches(allowlist, "github.read_file") is True
    assert tool_matches(allowlist, "github.read_repo") is True
    assert tool_matches(allowlist, "github.anything") is True
    assert tool_matches(allowlist, "notion.create_page") is True
    assert tool_matches(allowlist, "notion.read_page") is False
    assert tool_matches(allowlist, "google_workspace.append_to_doc") is True
    assert tool_matches(allowlist, "google_workspace.write_sheet") is False
    assert tool_matches(allowlist, "slack.send_message") is False
    assert tool_matches([], "anything") is False


async def test_content_web2_agent_github_tool_fallback_graceful():
    class _StubLLM:
        async def generate(self, prompt, role):
            return {
                "provider": "stub",
                "model": "stub",
                "response": "# Test Article\n\nThis is a test blog post.\n\n## Key Takeaways\n1. Done\n",
            }

    class _BadTransport:
        def __init__(self):
            self._pending = {}
            self._lock = MagicMock()
            self._lock.__aenter__ = AsyncMock()
            self._lock.__aexit__ = AsyncMock(return_value=False)
            self._proc = MagicMock()
            self._proc.stdin = MagicMock()
            self._proc.stdin.write = MagicMock(side_effect=RuntimeError("boom"))
            self._proc.stdin.drain = AsyncMock()

    agent = ContentWeb2Agent()
    tools = [Tool(name="github.read_repo", description="read repo tree")]

    context_good = {
        "title": "Test",
        "github_repo": "jorshimayor/demo",
        "mcp_transport": _BadTransport(),
    }

    result = await agent.invoke(context_good, tools, _StubLLM())
    assert result.agent_role == AgentRole.CONTENT_WEB2
    assert len(result.output) > 0
    assert result.confidence > 0.4

    context_no_transport = {
        "title": "Test2",
        "github_repo": "jorshimayor/demo",
    }
    result2 = await agent.invoke(context_no_transport, tools, _StubLLM())
    assert result2.agent_role == AgentRole.CONTENT_WEB2
    assert result2.confidence > 0.4

    result3 = await agent.invoke({"title": "Test3"}, [], _StubLLM())
    assert result3.agent_role == AgentRole.CONTENT_WEB2


async def test_knowledge_crystallizer_invokes_extractor_validates_pydantic():
    sample = (
        "The OrchestratorAgent uses a Pipeline pattern. Avoid the common pitfall of "
        "forgetting to validate Pydantic models. Best practice: use KnowledgeCrystals "
        "to structure data. The LLMRouter strategy works well. Do not skip pydantic "
        "validation or you will hit bugs in production."
    )
    extractor = KnowledgeExtractor(llm=None)
    task_id = str(uuid4())
    crystals = await extractor.extract(sample, task_id)

    assert isinstance(crystals, KnowledgeCrystals)
    KnowledgeCrystals.model_validate(crystals.model_dump())

    assert crystals.source_task_id is not None
    assert isinstance(crystals.entities, list)
    assert isinstance(crystals.strategies, list)
    assert isinstance(crystals.pitfalls, list)
    assert isinstance(crystals.frameworks, list)

    class _StubLLM:
        async def generate(self, prompt, role):
            return {
                "provider": "stub",
                "model": "stub",
                "response": "# Knowledge Crystals\n\n## Entities\n- test\n\n## Strategies\n- s\n\n## Pitfalls\n- p\n\n## Frameworks\n- f\n\n## TL;DR\ntest\n",
            }

    agent = KnowledgeCrystallizerAgent()
    result = await agent.invoke(
        {"text": sample, "source_task_id": uuid4()},
        [],
        _StubLLM(),
    )
    assert result.agent_role == AgentRole.KNOWLEDGE
    assert "JSON" in result.output
    assert result.confidence >= 0.4
