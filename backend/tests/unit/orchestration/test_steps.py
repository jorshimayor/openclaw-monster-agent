from __future__ import annotations

import asyncio
from typing import Any, Dict, List
from uuid import uuid4

import pytest

from src.core.types import AgentRole, AgentResult, PipelineStep, Task, TaskStatus
from src.knowledge.memory import ExperienceMemory
from src.orchestration import patterns as patterns_mod
from src.orchestration.graph_builder import WorkflowGraphBuilder
from src.orchestration.patterns import (
    PATTERN_CONFIGS,
    PatternConfig,
    WorkflowPattern,
    match_pattern,
)
from src.orchestration import steps as pipeline_steps


@pytest.fixture
def sample_task() -> Task:
    return Task(
        id=uuid4(),
        description=(
            "Write a comprehensive blog post comparing Uniswap v4 hooks "
            "with custom AMM strategies on Ethereum mainnet. Analyze gas costs "
            "and security best practices for liquidity providers."
        ),
        status=TaskStatus.PENDING,
        step=None,
        outputs={},
    )


@pytest.mark.asyncio
async def test_step1_complexity_multi_agent(sample_task: Task):
    status, state = await pipeline_steps.step1_complexity_check(sample_task)
    assert status == pipeline_steps.MULTI_AGENT
    assert "complexity" in state
    assert state["complexity"] == pipeline_steps.MULTI_AGENT
    assert state["description_length"] == len(sample_task.description)
    assert state["keyword_hits"] >= 1


@pytest.mark.asyncio
async def test_step1_complexity_single_agent():
    simple = Task(
        id=uuid4(),
        description="Hi",
        status=TaskStatus.PENDING,
    )
    status, state = await pipeline_steps.step1_complexity_check(simple)
    assert status == pipeline_steps.SINGLE_AGENT
    assert state["complexity_reason"]


@pytest.mark.asyncio
async def test_step2_pattern_match_blog():
    status, state = await pipeline_steps.step2_pattern_match(
        "Write a blog post about Solidity smart contract tutorial"
    )
    assert status in {WorkflowPattern.DRAFT_BLOG_POST, WorkflowPattern.GENERIC}
    assert 0.0 <= state["confidence"] <= 1.0


@pytest.mark.asyncio
async def test_step2_pattern_match_football():
    status, state = await pipeline_steps.step2_pattern_match(
        "Premier League tactical analysis: high pressing formation transfer news"
    )
    assert status in {WorkflowPattern.FOOTBALL_ANALYSIS, WorkflowPattern.GENERIC}


@pytest.mark.asyncio
async def test_step2_pattern_match_audit():
    status, state = await pipeline_steps.step2_pattern_match(
        "Audit this solidity smart contract for vulnerabilities security review"
    )
    assert status in {WorkflowPattern.AUDIT_CODE, WorkflowPattern.GENERIC}


@pytest.mark.asyncio
async def test_step2_pattern_match_study():
    status, state = await pipeline_steps.step2_pattern_match(
        "Build me a study plan curriculum syllabus for learning Rust and Solana"
    )
    assert status in {WorkflowPattern.STUDY_PLAN, WorkflowPattern.GENERIC}


@pytest.mark.asyncio
async def test_step3_experience_recall_with_memory(sample_task: Task):
    mem = ExperienceMemory()
    mem.store(
        "Uniswap v4 blog post about hooks",
        ["Hook lifecycle matters", "Fee-on-transfer edge case"],
    )
    mem.store(
        "Football formation analysis",
        ["4-3-3 overlap runs"],
    )
    pattern = WorkflowPattern.DRAFT_BLOG_POST
    status, state = await pipeline_steps.step3_experience_recall(
        pattern, sample_task.description, mem
    )
    assert status == "OK"
    assert isinstance(state["lessons"], list)
    assert state["recalled_count"] >= 0


@pytest.mark.asyncio
async def test_step3_experience_recall_empty_memory(sample_task: Task):
    mem = ExperienceMemory()
    status, state = await pipeline_steps.step3_experience_recall(
        WorkflowPattern.GENERIC, sample_task.description, mem
    )
    assert state["lessons"] == []
    assert state["recalled_count"] == 0


@pytest.mark.asyncio
async def test_step4_team_assembly():
    cfg = PATTERN_CONFIGS[WorkflowPattern.DRAFT_BLOG_POST]
    status, state = await pipeline_steps.step4_team_assembly(cfg, [], None)
    assert status == "OK"
    assert state["verifier_role"] == AgentRole.EDITOR
    assert state["total_agents"] >= 1
    assert len(state["agent_waves_cfg"]) >= 1
    wave0 = state["agent_waves_cfg"][0]
    assert len(wave0) >= 1
    agent_cfg = wave0[0]
    assert "role" in agent_cfg
    assert "model" in agent_cfg
    assert "tool_allowlist" in agent_cfg


@pytest.mark.asyncio
async def test_step5_prompt_injection():
    cfg = PATTERN_CONFIGS[WorkflowPattern.GENERIC]
    _, s4 = await pipeline_steps.step4_team_assembly(cfg, [], None)
    shared = {
        "task_description": "Hello world task",
        "experience_lessons": ["Lesson A", "Lesson B"],
    }
    status, state = await pipeline_steps.step5_prompt_injection(
        s4["agent_waves_cfg"], shared, None
    )
    assert status == "OK"
    waves = state["agent_waves_with_prompts"]
    assert len(waves) == len(s4["agent_waves_cfg"])
    for wave in waves:
        for agent_cfg in wave:
            assert "built_prompt" in agent_cfg
            assert len(agent_cfg["built_prompt"]) > 50


@pytest.mark.asyncio
async def test_step6_parallel_execution_stub():
    cfg = PATTERN_CONFIGS[WorkflowPattern.GENERIC]
    _, s4 = await pipeline_steps.step4_team_assembly(cfg, [], None)
    shared = {"task_description": "Stub task", "experience_lessons": []}
    _, s5 = await pipeline_steps.step5_prompt_injection(
        s4["agent_waves_cfg"], shared, None
    )
    status, state = await pipeline_steps.step6_parallel_execution(
        s5["agent_waves_with_prompts"],
        llm=None,
        agent_factory=None,
    )
    assert status == "OK"
    assert state["execution_seconds"] >= 0.0
    assert len(state["all_outputs"]) >= 1
    # State contract: steps return model_dump()'d state (JSON-safe — it goes
    # into task.outputs and Postgres JSONB). Consumers coerce via
    # ensure_agent_results; assert that round-trip is lossless.
    coerced = pipeline_steps.ensure_agent_results(state["all_outputs"])
    for out in coerced:
        assert isinstance(out, AgentResult)
        assert isinstance(out.output, str)
        assert 0.0 <= out.confidence <= 1.0


@pytest.mark.asyncio
async def test_step7_verifier_all_pass():
    outputs = [
        AgentResult(
            agent_role=AgentRole.CONTENT_WEB2,
            output="A" * 200,
            confidence=0.9,
            errors=None,
        ),
        AgentResult(
            agent_role=AgentRole.CONTENT_WEB3,
            output="B" * 200,
            confidence=0.85,
            errors=None,
        ),
    ]
    status, state = await pipeline_steps.step7_verifier(
        outputs, None, None, None, ttl_seconds=3600, confidence_threshold=0.7
    )
    assert status == "OK"
    assert state["passed_count"] == 2
    assert state["failed_count"] == 0
    for v in state["verified_outputs"]:
        assert v["passed"] is True


@pytest.mark.asyncio
async def test_step7_verifier_some_fail_low_confidence():
    outputs = [
        AgentResult(
            agent_role=AgentRole.CONTENT_WEB2,
            output="A" * 200,
            confidence=0.95,
            errors=None,
        ),
        AgentResult(
            agent_role=AgentRole.CONTENT_WEB3,
            output="B" * 200,
            confidence=0.2,
            errors=None,
        ),
        AgentResult(
            agent_role=AgentRole.EDITOR,
            output="short",
            confidence=0.9,
            errors=None,
        ),
    ]
    status, state = await pipeline_steps.step7_verifier(
        outputs, None, None, None, confidence_threshold=0.7
    )
    assert state["failed_count"] >= 2


@pytest.mark.asyncio
async def test_step8_p6_quality_gate_pass(sample_task: Task):
    verified = [
        {
            "agent_role": AgentRole.CONTENT_WEB2,
            "passed": True,
            "confidence": 0.9,
            "feedback": "OK",
            "stale": False,
            "original_output": AgentResult(
                agent_role=AgentRole.CONTENT_WEB2, output="A" * 200, confidence=0.9
            ),
        },
        {
            "agent_role": AgentRole.CONTENT_WEB3,
            "passed": True,
            "confidence": 0.85,
            "feedback": "OK",
            "stale": False,
            "original_output": AgentResult(
                agent_role=AgentRole.CONTENT_WEB3, output="B" * 200, confidence=0.85
            ),
        },
    ]
    review = [AgentRole.EDITOR, AgentRole.ORCHESTRATOR]
    status, state = await pipeline_steps.step8_p6_quality_gate(verified, review, None, None)
    assert status in {pipeline_steps.PASS, pipeline_steps.FAIL}
    assert 0.0 <= state["aggregate_score"] <= 1.0
    assert len(state["approved_outputs"]) == 2
    assert len(state["failed_outputs"]) == 0


@pytest.mark.asyncio
async def test_step8_quality_gate_fail_triggers_step9_branch():
    verified = [
        {
            "agent_role": AgentRole.CONTENT_WEB2,
            "passed": False,
            "confidence": 0.1,
            "feedback": "Confidence too low, output too short",
            "stale": False,
            "original_output": AgentResult(
                agent_role=AgentRole.CONTENT_WEB2,
                output="nope",
                confidence=0.1,
            ),
        },
    ]
    review_team = [AgentRole.EDITOR]
    gate, gate_state = await pipeline_steps.step8_p6_quality_gate(
        verified, review_team, None, None
    )
    assert gate == pipeline_steps.FAIL
    assert len(gate_state["failed_outputs"]) >= 1

    failed = gate_state["failed_outputs"]
    _, fix_state = await pipeline_steps.step9_fix_and_revalidate(
        failed, [], None, None, single_rework=True
    )
    assert fix_state["stop_after"] is True
    assert fix_state["single_rework_performed"] is True
    assert len(fix_state["reworked_outputs"]) == len(failed)
    # Same state contract as step6: dumped dicts, coercible losslessly.
    for out in pipeline_steps.ensure_agent_results(fix_state["reworked_outputs"]):
        assert isinstance(out, AgentResult)
        # A stub rework (no LLM) must not smuggle in an error-crash output.
        assert "rework failed" not in out.output


@pytest.mark.asyncio
async def test_step9_single_rework_flag_respected():
    fail_item = {
        "agent_role": AgentRole.EDITOR,
        "passed": False,
        "confidence": 0.1,
        "feedback": "Needs more cowbell",
        "stale": False,
        "original_output": AgentResult(
            agent_role=AgentRole.EDITOR, output="bad", confidence=0.1
        ),
    }
    _, s_default = await pipeline_steps.step9_fix_and_revalidate(
        [fail_item], [], None, None, single_rework=True
    )
    assert s_default["stop_after"] is True
    _, s_false = await pipeline_steps.step9_fix_and_revalidate(
        [fail_item], [], None, None, single_rework=False
    )
    assert s_false["stop_after"] is False


@pytest.mark.asyncio
async def test_step10_synthesizer():
    approved = [
        AgentResult(
            agent_role=AgentRole.CONTENT_WEB3,
            output="Web3 output section with analysis.",
            confidence=0.8,
        ),
        AgentResult(
            agent_role=AgentRole.CONTENT_WEB2,
            output="Web2 output section.",
            confidence=0.9,
        ),
    ]
    status, state = await pipeline_steps.step10_synthesizer(
        approved, None, None, None, "Draft report on blockchain"
    )
    assert status == "OK"
    assert isinstance(state["final_report"], str)
    assert len(state["final_report"]) > 100
    assert state["overall_confidence"] > 0.0
    for role_val, c in state["confidence_ratings"].items():
        assert 0.0 <= c <= 1.0


@pytest.mark.asyncio
async def test_step11_reflection_no_crash(sample_task: Task):
    from src.core.config import get_settings
    from src.knowledge.store import CrystallizedKnowledgeStore

    mem = ExperienceMemory()
    store = CrystallizedKnowledgeStore(get_settings(), memory=mem)
    final_report = "# Final Report\n\nDiscusses Ethereum, Solidity, React, and TypeScript. Strategy: use SSR. Pitfall: avoid reentrancy. Framework: Next.js pipeline orchestrator."
    status, state = await pipeline_steps.step11_post_task_reflection(
        final_report, sample_task, None, None, None, store, mem
    )
    assert status == "OK"
    assert state["saved_crystal_id"] is not None
    assert len(state["lessons_stored"]) >= 1

    recalled = mem.recall("Ethereum solidity report", top_k=3, min_similarity=0.0)
    assert len(recalled) >= 1


def test_workflow_graph_builder_builds_dag():
    builder = WorkflowGraphBuilder()
    for pattern in WorkflowPattern:
        graph = builder.build(pattern)
        import networkx as nx

        assert nx.is_directed_acyclic_graph(graph)
        assert graph.has_node("task_input")
        assert graph.has_node("final_output")
        assert graph.has_node("step8_quality_gate")
        assert graph.has_node("step9_fix")
        assert graph.has_node("step10_synthesize")
        succ = list(graph.successors("step8_quality_gate"))
        assert "step10_synthesize" in succ
        assert "step9_fix" in succ
        succ9 = list(graph.successors("step9_fix"))
        # Rework re-verification is a distinct bounded node (matches the
        # executor's "step7b_reverify" event), keeping the graph a true DAG.
        assert "step7b_reverify" in succ9
        assert "step10_synthesize" in graph.successors("step7b_reverify")


@pytest.mark.asyncio
async def test_match_pattern_returns_confidence_tuple():
    result = await match_pattern("write a blog post article tutorial")
    assert isinstance(result, tuple)
    assert len(result) == 2
    pattern, confidence = result
    assert isinstance(pattern, WorkflowPattern)
    assert 0.0 <= confidence <= 1.0


@pytest.mark.asyncio
async def test_all_11_steps_run_together_end_to_end(sample_task: Task):
    sr1, ss1 = await pipeline_steps.step1_complexity_check(sample_task)
    assert sr1 in {pipeline_steps.SINGLE_AGENT, pipeline_steps.MULTI_AGENT}

    sr2, ss2 = await pipeline_steps.step2_pattern_match(sample_task.description)
    cfg = PATTERN_CONFIGS.get(sr2, PATTERN_CONFIGS[WorkflowPattern.GENERIC])

    mem = ExperienceMemory()
    sr3, ss3 = await pipeline_steps.step3_experience_recall(sr2, sample_task.description, mem)

    sr4, ss4 = await pipeline_steps.step4_team_assembly(cfg, ss3["lessons"], None)

    shared = {
        "task_description": sample_task.description,
        "experience_lessons": ss3["lessons"],
    }
    sr5, ss5 = await pipeline_steps.step5_prompt_injection(ss4["agent_waves_cfg"], shared)

    sr6, ss6 = await pipeline_steps.step6_parallel_execution(
        ss5["agent_waves_with_prompts"], llm=None, agent_factory=None
    )

    sr7, ss7 = await pipeline_steps.step7_verifier(ss6["all_outputs"], None, None)

    review_team = ss4["review_team"]
    sr8, ss8 = await pipeline_steps.step8_p6_quality_gate(ss7["verified_outputs"], review_team, None)

    if sr8 == pipeline_steps.FAIL and ss8["failed_outputs"]:
        sr9, ss9 = await pipeline_steps.step9_fix_and_revalidate(
            ss8["failed_outputs"], [], None, None, single_rework=True
        )
        assert ss9["single_rework_performed"] is True

    approved = ss8["approved_outputs"]
    sr10, ss10 = await pipeline_steps.step10_synthesizer(
        approved, None, None, None, sample_task.description
    )
    assert isinstance(ss10["final_report"], str)

    from src.core.config import get_settings
    from src.knowledge.store import CrystallizedKnowledgeStore

    store = CrystallizedKnowledgeStore(get_settings(), memory=mem)
    sr11, ss11 = await pipeline_steps.step11_post_task_reflection(
        ss10["final_report"], sample_task, None, None, None, store, mem
    )
    assert ss11["saved_crystal_id"] is not None
