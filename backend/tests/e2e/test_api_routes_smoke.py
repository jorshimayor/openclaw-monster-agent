from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.api.main import app as fastapi_app
from src.core.types import AgentRole, AgentResult
from src.mcp.manager import McpServerStatus

pytestmark = pytest.mark.asyncio(loop_scope="session")


def test_health_ok(app) -> None:
    response = app.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "version" in body


def test_llm_test_mocked_returns_response(app, monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_generate(prompt: str, agent_role: AgentRole, **kwargs: Any) -> Dict[str, Any]:
        return {
            "provider": "mocked-groq",
            "model": "groq-llama-3.3-70b-versatile",
            "response": f"Mocked response: {prompt[:30]}",
            "model_name": "groq-llama-3.3-70b-versatile",
        }

    router = getattr(fastapi_app.state, "llm_router", None)
    if router is None:
        fake_router = MagicMock()
        fake_router.generate = AsyncMock(side_effect=fake_generate)
        fastapi_app.state.llm_router = fake_router
    else:
        monkeypatch.setattr(router, "generate", fake_generate)

    response = app.post(
        "/api/llm/test",
        json={"prompt": "Hello from the smoke test suite."},
    )
    assert response.status_code == 200
    body = response.json()
    for key in ("provider", "model", "response"):
        assert key in body, f"Missing key '{key}' in llm/test response"
    assert isinstance(body["response"], str)
    assert len(body["response"]) > 0


def test_list_agents_returns_9(app) -> None:
    response = app.get("/api/agents")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    # 9 since the PERSONAL_ASSISTANT agent joined the roster
    assert len(body) == 9, f"Expected 9 agents, got {len(body)}"


def test_get_single_agent(app) -> None:
    response = app.get("/api/agents/security")
    assert response.status_code == 200
    body = response.json()
    assert "role" in body
    assert body["role"].upper() == AgentRole.SECURITY.value
    assert "status" in body
    assert "description" in body
    assert body.get("healthy") is True


def test_invoke_agent_security_auditor_mocked(
    app,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_generate(prompt: str, agent_role: AgentRole, **kwargs: Any) -> Dict[str, Any]:
        return {
            "provider": "stub",
            "model": "stub-model",
            "response": (
                '{"findings": [{"severity":"HIGH","cvss":8.1,"title":"Reentrancy"}], '
                '"summary":"1 critical-like issue found"}'
            ),
        }

    router = getattr(fastapi_app.state, "llm_router", None)
    if router is None:
        fake_router = MagicMock()
        fake_router.generate = AsyncMock(side_effect=fake_generate)
        fastapi_app.state.llm_router = fake_router
    else:
        monkeypatch.setattr(router, "generate", fake_generate)

    response = app.post(
        "/api/agents/security/invoke",
        json={"context": {"code": "contract Demo {}", "prompt": "audit this"}},
    )
    assert response.status_code == 200
    body = response.json()
    for key in ("agent_role", "output", "confidence"):
        assert key in body, f"Missing AgentResult key '{key}' in invoke response"
    assert 0.0 <= float(body["confidence"]) <= 1.0


def _install_mock_mcp(app, monkeypatch):
    server_names = ["github", "notion", "google_workspace", "slack", "hashnode"]

    def _statuses() -> List[McpServerStatus]:
        return [
            McpServerStatus(
                name=n,
                status="HEALTHY",
                tools_available=3,
                last_probe=datetime.utcnow().isoformat(),
            )
            for n in server_names
        ]

    async def _probe(server: str) -> Dict[str, Any]:
        if server not in server_names:
            raise ValueError(f"Unknown MCP server: {server}")
        return {
            "server": server,
            "ok": True,
            "latency_ms": 7,
            "tools": ["list", "read", "write"],
        }

    manager = getattr(fastapi_app.state, "mcp_manager", None)
    if manager is None:
        fake = MagicMock()
        fake.get_server_statuses = MagicMock(side_effect=_statuses)
        fake.probe_server = AsyncMock(side_effect=_probe)
        fastapi_app.state.mcp_manager = fake
    else:
        monkeypatch.setattr(manager, "get_server_statuses", _statuses)
        monkeypatch.setattr(manager, "probe_server", _probe)


def test_mcp_doctor_returns_5_servers(app, monkeypatch: pytest.MonkeyPatch) -> None:
    _install_mock_mcp(app, monkeypatch)
    response = app.get("/api/mcp/doctor")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) == 5
    for entry in body:
        assert "status" in entry
        assert "name" in entry


def test_mcp_doctor_probe_github(app, monkeypatch: pytest.MonkeyPatch) -> None:
    _install_mock_mcp(app, monkeypatch)
    response = app.get("/api/mcp/doctor/github/probe")
    assert response.status_code == 200
    body = response.json()
    assert body.get("server") == "github" or "ok" in body


def test_mcp_doctor_probe_unknown_404(app, monkeypatch: pytest.MonkeyPatch) -> None:
    _install_mock_mcp(app, monkeypatch)
    response = app.get("/api/mcp/doctor/unknown_server/probe")
    assert response.status_code == 404


def test_knowledge_list_empty_200(app, monkeypatch: pytest.MonkeyPatch) -> None:
    from src.core.config import get_settings
    from src.knowledge.memory import ExperienceMemory
    from src.knowledge.store import CrystallizedKnowledgeStore

    settings = get_settings()
    empty_store = CrystallizedKnowledgeStore(settings, memory=ExperienceMemory())
    monkeypatch.setattr(fastapi_app.state, "knowledge_store", empty_store, raising=False)

    response = app.get("/api/knowledge")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert body == []


def test_knowledge_query_200(app, monkeypatch: pytest.MonkeyPatch) -> None:
    from src.core.config import get_settings
    from src.knowledge.memory import ExperienceMemory
    from src.knowledge.store import CrystallizedKnowledgeStore

    settings = get_settings()
    store = CrystallizedKnowledgeStore(settings, memory=ExperienceMemory())
    monkeypatch.setattr(fastapi_app.state, "knowledge_store", store, raising=False)

    response = app.post(
        "/api/knowledge/query",
        json={"query": "uniswap", "top_k": 5},
    )
    assert response.status_code == 200
    body = response.json()
    assert "query" in body
    assert "results" in body
    assert isinstance(body["results"], list)
    assert "took_ms" in body


def test_task_submit_and_stream_sse(
    app,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from unittest.mock import MagicMock as _MagicMock, AsyncMock as _AsyncMock
    from src.core.config import get_settings
    from src.knowledge.memory import ExperienceMemory
    from src.knowledge.store import CrystallizedKnowledgeStore
    from src.orchestration.pipeline import PipelineExecutor

    settings = get_settings()
    memory = ExperienceMemory()
    store = CrystallizedKnowledgeStore(settings, memory=memory)

    async def _fake_llm_generate(prompt, role, **kw):
        return {
            "provider": "mock",
            "model": "mock-model",
            "response": "SSE test LLM response",
        }

    fake_llm = _MagicMock()
    fake_llm.generate = _AsyncMock(side_effect=_fake_llm_generate)

    fake_manager = _MagicMock()
    fake_manager.registry = _MagicMock()
    fake_manager.get_server_statuses = _MagicMock(return_value=[])
    fake_manager.probe_server = _AsyncMock(return_value={"ok": True})

    executor = PipelineExecutor(
        settings=settings,
        llm=fake_llm,
        manager=fake_manager,
        store=store,
        memory=memory,
    )
    monkeypatch.setattr(fastapi_app.state, "pipeline_executor", executor, raising=False)
    monkeypatch.setattr(fastapi_app.state, "knowledge_store", store, raising=False)
    monkeypatch.setattr(fastapi_app.state, "knowledge_memory", memory, raising=False)
    monkeypatch.setattr(fastapi_app.state, "llm_router", fake_llm, raising=False)
    monkeypatch.setattr(fastapi_app.state, "mcp_manager", fake_manager, raising=False)

    create_response = app.post(
        "/api/tasks",
        json={"description": "SSE smoke test task"},
    )
    assert create_response.status_code == 201
    task_id = create_response.json()["id"]

    stream_response = app.get(f"/api/tasks/{task_id}/stream")
    assert stream_response.status_code == 200
    ctype = stream_response.headers.get("Content-Type", "")
    assert "text/event-stream" in ctype or "text/event-stream" in ctype.lower()


def test_task_cancel(
    app,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from unittest.mock import MagicMock as _MagicMock, AsyncMock as _AsyncMock
    from src.core.config import get_settings
    from src.knowledge.memory import ExperienceMemory
    from src.knowledge.store import CrystallizedKnowledgeStore
    from src.orchestration.pipeline import PipelineExecutor

    settings = get_settings()
    memory = ExperienceMemory()
    store = CrystallizedKnowledgeStore(settings, memory=memory)

    fake_llm = _MagicMock()

    async def _slow_generate(*_a, **_kw):
        # Keep the pipeline demonstrably in-flight so the cancel request
        # deterministically wins the race (an instant fake completed the
        # whole pipeline before cancel landed, flaking this test).
        await asyncio.sleep(5.0)
        return {"provider": "m", "model": "m", "response": "ok"}

    fake_llm.generate = _AsyncMock(side_effect=_slow_generate)
    fake_manager = _MagicMock()
    fake_manager.registry = _MagicMock()
    fake_manager.get_server_statuses = _MagicMock(return_value=[])
    fake_manager.probe_server = _AsyncMock(return_value={"ok": True})

    executor = PipelineExecutor(
        settings=settings,
        llm=fake_llm,
        manager=fake_manager,
        store=store,
        memory=memory,
    )
    monkeypatch.setattr(fastapi_app.state, "pipeline_executor", executor, raising=False)
    monkeypatch.setattr(fastapi_app.state, "knowledge_store", store, raising=False)
    monkeypatch.setattr(fastapi_app.state, "knowledge_memory", memory, raising=False)

    create_response = app.post(
        "/api/tasks",
        json={"description": "Cancel smoke test task"},
    )
    assert create_response.status_code == 201
    task_id = create_response.json()["id"]

    cancel_response = app.get(f"/api/tasks/{task_id}/cancel")
    assert cancel_response.status_code == 200
    body = cancel_response.json()
    assert body["cancelled"] is True
    assert body["status"] == "CANCELLED"
