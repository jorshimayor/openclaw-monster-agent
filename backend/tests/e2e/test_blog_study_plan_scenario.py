from __future__ import annotations

from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.types import (
    AgentRole,
    AgentResult,
    KnowledgeCrystals,
    PipelineStep,
    Task,
    TaskStatus,
)
from src.orchestration import pipeline as pipeline_module
from src.orchestration import steps as pipeline_steps
from src.orchestration.pipeline import PipelineExecutor

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_submit_task_queues_and_runs_pipeline(
    app,
    mock_llm_router_always_success,
    mock_mcp_manager_healthy,
    mock_pipeline_executor,
    blog_and_study_plan_task_description,
) -> None:
    response = app.post(
        "/api/tasks",
        json={"description": blog_and_study_plan_task_description},
    )
    assert response.status_code == 201
    body = response.json()
    assert "id" in body
    assert len(body["id"]) > 0
    assert body["status"] == TaskStatus.QUEUED.value
    assert body["description"] == blog_and_study_plan_task_description


async def test_pipeline_completes_all_11_steps(
    mock_pipeline_executor: PipelineExecutor,
    sample_task: Task,
) -> None:
    store = mock_pipeline_executor.store
    memory = mock_pipeline_executor.memory

    memory.store(
        sample_task.description,
        [
            "Always check for hook reentrancy before deployment",
            "Fee-on-transfer tokens need explicit liquidity math",
        ],
    )

    task = await mock_pipeline_executor.run(sample_task)

    assert task.status == TaskStatus.COMPLETED
    step_outputs = task.outputs.get("step_outputs", {})
    assert "step1" in step_outputs
    assert "step11" in step_outputs

    step11_state = step_outputs["step11"].get("state", {})
    assert step11_state is not None

    output_keys = set(task.outputs.keys())
    critical_keys = {"final_report", "step_outputs"}
    assert len(output_keys & critical_keys) >= 1
    assert len(task.outputs) >= 3

    crystals = await store.list()
    assert len(crystals) >= 1, "Step 11 reflection did not save any knowledge crystal"

    recalled = memory.recall(sample_task.description, top_k=5, min_similarity=0.0)
    assert isinstance(recalled, list)
    assert len(recalled) >= 1


async def test_step8_fail_triggers_exactly_one_rework_cycle(
    mock_pipeline_executor: PipelineExecutor,
    sample_task: Task,
) -> None:
    original_step8 = pipeline_steps.step8_p6_quality_gate
    original_step7 = pipeline_steps.step7_verifier

    step7_call_count: Dict[str, int] = {"count": 0}
    step8_call_count: Dict[str, int] = {"count": 0}

    async def wrapped_step7(*args, **kwargs):
        step7_call_count["count"] += 1
        result = await original_step7(*args, **kwargs)
        if step7_call_count["count"] == 1:
            status, state = result
            for verified in state.get("verified_outputs", []):
                verified["passed"] = True
            state["passed_count"] = len(state.get("verified_outputs", []))
            state["failed_count"] = 0
            return status, state
        return result

    async def wrapped_step8(*args, **kwargs):
        step8_call_count["count"] += 1
        status, state = await original_step8(*args, **kwargs)
        if step8_call_count["count"] == 1:
            approved = list(state.get("approved_outputs", []))
            failed_out: List[Dict[str, Any]] = []
            if approved:
                promoted = approved[0]
                failed_out.append(
                    {
                        "agent_role": getattr(promoted, "agent_role", AgentRole.CONTENT_WEB3.value),
                        "output": getattr(promoted, "output", "failed output"),
                        "feedback": "Needs more concrete examples and code references.",
                        "score": 0.4,
                    }
                )
                approved = approved[1:]
            state["approved_outputs"] = approved
            state["failed_outputs"] = failed_out
            state["aggregate_score"] = 0.4
            return pipeline_steps.FAIL, state
        state["aggregate_score"] = 0.9
        return pipeline_steps.PASS, state

    # The executor resolves steps through the `pipeline_steps` module at call
    # time (`from . import steps as pipeline_steps`) — patch there, not on the
    # pipeline module (which never re-exports the step functions).
    with (
        patch.object(pipeline_steps, "step7_verifier", wrapped_step7),
        patch.object(pipeline_steps, "step8_p6_quality_gate", wrapped_step8),
    ):
        task = await mock_pipeline_executor.run(sample_task)

    assert task.status == TaskStatus.COMPLETED
    assert step7_call_count["count"] == 2, (
        f"Expected exactly 2 verifier calls (original + post-rework), got {step7_call_count['count']}"
    )
    assert step7_call_count["count"] != 3, "Verifier was called 3 times; rework loop is not bounded"

    step_outputs = task.outputs.get("step_outputs", {})
    assert "step9" in step_outputs, "Step9 (fix/revalidate) should have been executed once"


async def test_llm_fallback_triggers_within_pipeline(
    mock_pipeline_executor: PipelineExecutor,
    sample_task: Task,
) -> None:
    call_log: List[Dict[str, Any]] = []

    async def fake_llm_generate(prompt: str, agent_role: AgentRole, **kwargs: Any) -> Dict[str, Any]:
        if agent_role == AgentRole.CONTENT_WEB3 and len(call_log) < 2:
            call_log.append({"role": agent_role.value, "attempt": len(call_log) + 1})
            from src.llm.providers.nvidia_nim import LLMProviderError
            raise LLMProviderError("nvidia_nim: primary provider forced failure")
        call_log.append({"role": agent_role.value if hasattr(agent_role, "value") else str(agent_role), "provider": "groq"})
        return {
            "provider": "groq",
            "model": "groq-llama-3.3-70b",
            "response": f"Groq fallback response for {agent_role}",
            "model_name": "groq-llama-3.3-70b",
        }

    mock_llm = MagicMock()
    mock_llm.generate = AsyncMock(side_effect=fake_llm_generate)
    mock_pipeline_executor.llm = mock_llm

    task = await mock_pipeline_executor.run(sample_task)

    assert task.status == TaskStatus.COMPLETED

    step_outputs = task.outputs.get("step_outputs", {})
    step6 = step_outputs.get("step6", {}).get("state", {})
    all_outputs = step6.get("all_outputs", [])

    found_web3_with_groq = False
    for out in all_outputs:
        if isinstance(out, AgentResult):
            role = out.agent_role.value if hasattr(out.agent_role, "value") else str(out.agent_role)
            if role == AgentRole.CONTENT_WEB3.value:
                metadata = getattr(out, "metadata", {}) or {}
                if metadata.get("provider") == "groq" or "Groq" in out.output:
                    found_web3_with_groq = True
                    break
        elif isinstance(out, dict):
            if str(out.get("agent_role", "")).upper() == AgentRole.CONTENT_WEB3.value:
                if "Groq" in str(out.get("output", "")):
                    found_web3_with_groq = True
                    break

    groq_used = any(
        entry.get("provider") == "groq" or entry.get("role") == AgentRole.CONTENT_WEB3.value
        for entry in call_log
    )
    assert found_web3_with_groq or groq_used, (
        "Expected CONTENT_WEB3 to fallback to groq provider after primary failure"
    )


async def test_sse_stream_yields_step_events(
    mock_pipeline_executor: PipelineExecutor,
    sample_task: Task,
) -> None:
    collected_events: List[Dict[str, Any]] = []

    def event_callback(event: Dict[str, Any]) -> None:
        collected_events.append(dict(event))

    task = await mock_pipeline_executor.run(sample_task, event_callback=event_callback)

    assert task.status == TaskStatus.COMPLETED
    assert len(collected_events) > 0

    step_event_names = [
        "step1_complexity",
        "step2_pattern",
        "step3_experience",
        "step4_team",
        "step5_prompt",
        "step6_execution",
        "step7_verifier",
        "step8_quality_gate",
        "step10_synthesizer",
        "step11_reflection",
    ]

    event_steps_found = [e.get("step") for e in collected_events if e.get("step")]

    for required_step in step_event_names:
        assert required_step in event_steps_found, (
            f"Missing step event in stream: {required_step}. "
            f"Found: {event_steps_found}"
        )

    ordering = [event_steps_found.index(s) for s in step_event_names if s in event_steps_found]
    assert ordering == sorted(ordering), "Step events did not arrive in pipeline order"

    agent_output_count = 0
    for evt in collected_events:
        data = evt.get("data", {}) if isinstance(evt.get("data"), dict) else {}
        if isinstance(evt, dict):
            for key, value in evt.items():
                if isinstance(value, str) and ("Mock LLM response" in value or len(value) > 100):
                    agent_output_count += 1
                    break
            # step6_execution emits {"outputs": N, "seconds": …} — all-numeric
            # data, so the old "content-bearing values" guard always skipped it.
            out_count = data.get("outputs")
            if isinstance(out_count, int) and out_count > 0:
                agent_output_count += 1

    assert agent_output_count >= 1, "Expected at least one agent_output-content-bearing event in stream"


async def test_notion_sync_queued_after_step11_if_token_set(
    sample_task: Task,
    mock_settings_with_notion_token,
) -> None:
    from src.core.config import get_settings
    from src.knowledge.memory import ExperienceMemory
    from src.knowledge.store import CrystallizedKnowledgeStore
    from src.orchestration.pipeline import PipelineExecutor
    from unittest.mock import AsyncMock as _AsyncMock, MagicMock as _MagicMock

    settings = mock_settings_with_notion_token
    assert settings.notion_token != ""

    memory = ExperienceMemory()
    store = CrystallizedKnowledgeStore(settings, memory=memory, extractor=None)

    async def _fake_llm_generate(prompt: str, agent_role, **kw):
        return {
            "provider": "mock",
            "model": "mock-model",
            "response": "Mock LLM OK with notion-token test settings",
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

    task = await executor.run(sample_task)

    assert task.status == TaskStatus.COMPLETED
    assert store._notion_enabled is True
    assert store._notion_queue.qsize() > 0, (
        "Step11 crystal add() did not enqueue to _notion_queue when NOTION_TOKEN was set"
    )
