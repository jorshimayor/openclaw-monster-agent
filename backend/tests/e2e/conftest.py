from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from src.api.main import app as fastapi_app
from src.core.config import Settings, get_settings
from src.core.types import AgentRole, Task, TaskStatus
from src.knowledge.memory import ExperienceMemory
from src.knowledge.store import CrystallizedKnowledgeStore
from src.mcp.manager import McpServerStatus
from src.orchestration.pipeline import PipelineExecutor

pytestmark = pytest.mark.asyncio(loop_scope="session")


def pytest_configure(config: Any) -> None:
    try:
        config.option.asyncio_mode = "auto"
    except Exception:
        pass


@pytest.fixture
def app() -> TestClient:
    client = TestClient(
        fastapi_app,
        raise_server_exceptions=False,
    )
    return client


@pytest.fixture
def mock_llm_router_always_success(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncMock:
    async def _fake_generate(prompt: str, agent_role: AgentRole, **kwargs: Any) -> Dict[str, Any]:
        return {
            "provider": "mock",
            "model": "mock-model",
            "response": "Mock LLM response OK",
            "model_name": "mock-model",
        }

    mock_gen = AsyncMock(side_effect=_fake_generate)

    router = getattr(fastapi_app.state, "llm_router", None)
    if router is None:
        fake_router = MagicMock()
        fake_router.generate = mock_gen
        fastapi_app.state.llm_router = fake_router
    else:
        monkeypatch.setattr(router, "generate", mock_gen)

    return mock_gen


@pytest.fixture
def mock_mcp_manager_healthy(
    monkeypatch: pytest.MonkeyPatch,
) -> MagicMock:
    server_names = ["github", "notion", "google_workspace", "slack", "hashnode"]

    def _statuses() -> List[McpServerStatus]:
        return [
            McpServerStatus(
                name=name,
                status="HEALTHY",
                tools_available=3,
                last_probe=datetime.utcnow().isoformat(),
            )
            for name in server_names
        ]

    async def _probe(server: str) -> Dict[str, Any]:
        if server not in server_names:
            raise ValueError(f"Unknown MCP server: {server}")
        return {
            "server": server,
            "ok": True,
            "latency_ms": 12,
            "tools": ["tool1", "tool2", "tool3"],
        }

    manager = getattr(fastapi_app.state, "mcp_manager", None)
    if manager is None:
        fake_manager = MagicMock()
        fake_manager.get_server_statuses = MagicMock(side_effect=_statuses)
        fake_manager.probe_server = AsyncMock(side_effect=_probe)
        fake_manager.registry = MagicMock()
        fastapi_app.state.mcp_manager = fake_manager
        manager = fake_manager
    else:
        monkeypatch.setattr(manager, "get_server_statuses", _statuses)
        monkeypatch.setattr(manager, "probe_server", _probe)
        if not hasattr(manager, "registry") or manager.registry is None:
            manager.registry = MagicMock()

    return manager


@pytest.fixture
def mock_pipeline_executor() -> PipelineExecutor:
    settings = get_settings()

    memory = ExperienceMemory()
    store = CrystallizedKnowledgeStore(settings, memory=memory, extractor=None)

    async def _fake_llm_generate(prompt: str, agent_role: AgentRole, **kwargs: Any) -> Dict[str, Any]:
        return {
            "provider": "mock",
            "model": "mock-model",
            "response": "Mock LLM response OK for pipeline execution.",
        }

    fake_llm = MagicMock()
    fake_llm.generate = AsyncMock(side_effect=_fake_llm_generate)

    fake_manager = MagicMock()
    fake_manager.registry = MagicMock()
    fake_manager.get_server_statuses = MagicMock(return_value=[])
    fake_manager.probe_server = AsyncMock(return_value={"ok": True})

    executor = PipelineExecutor(
        settings=settings,
        llm=fake_llm,
        manager=fake_manager,
        store=store,
        memory=memory,
    )

    fastapi_app.state.pipeline_executor = executor
    fastapi_app.state.knowledge_store = store
    fastapi_app.state.knowledge_memory = memory
    fastapi_app.state.llm_router = fake_llm
    fastapi_app.state.mcp_manager = fake_manager

    return executor


@pytest.fixture
def blog_and_study_plan_task_description() -> str:
    return (
        "Draft a beginner-friendly blog post on auditing a Uniswap v4 hook, "
        "referencing my codebase, and then create a study plan for zk-SNARKs."
    )


@pytest.fixture
def sample_task(blog_and_study_plan_task_description: str) -> Task:
    return Task(
        id=uuid4(),
        description=blog_and_study_plan_task_description,
        status=TaskStatus.PENDING,
        step=None,
        outputs={},
    )


@pytest.fixture
def mock_settings_with_notion_token(
    monkeypatch: pytest.MonkeyPatch,
) -> Settings:
    original = get_settings()
    monkeypatch.setattr(original, "notion_token", "secret_notion_token_test_123")
    monkeypatch.setattr(original, "notion_db_id", "test_db_id")
    return original
