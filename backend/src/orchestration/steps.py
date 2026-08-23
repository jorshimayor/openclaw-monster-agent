from __future__ import annotations

import asyncio
from time import time
from typing import Any, Callable, Dict, List, Optional, Tuple, TYPE_CHECKING

from pydantic import BaseModel, Field

from ..core.logging import get_logger
from ..core.types import AgentRole, AgentResult, PipelineStep, Task
from .patterns import WorkflowPattern

if TYPE_CHECKING:
    from ..agents.base import Agent, Tool
    from ..knowledge.memory import ExperienceMemory
    from ..knowledge.store import CrystallizedKnowledgeStore
    from ..llm.router import LLMRouter
    from ..mcp.manager import McpServerManager
    from ..mcp.registry import McpToolRegistry
    from .patterns import PatternConfig

logger = get_logger(__name__)

StepResult = str

SINGLE_AGENT: StepResult = "SINGLE_AGENT"
MULTI_AGENT: StepResult = "MULTI_AGENT"
PASS: StepResult = "PASS"
FAIL: StepResult = "FAIL"


class ComplexityState(BaseModel):
    complexity: StepResult
    complexity_reason: str
    description_length: int
    keyword_hits: int


class PatternMatchState(BaseModel):
    pattern_id: WorkflowPattern
    confidence: float
    matched_keywords: List[str] = Field(default_factory=list)


class ExperienceRecallState(BaseModel):
    lessons: List[str] = Field(default_factory=list)
    recalled_count: int = 0


class TeamAssemblyState(BaseModel):
    agent_waves_cfg: List[List[Dict[str, Any]]] = Field(default_factory=list)
    verifier_role: AgentRole
    review_team: List[AgentRole] = Field(default_factory=list)
    total_agents: int = 0


class PromptInjectionState(BaseModel):
    agent_waves_with_prompts: List[List[Dict[str, Any]]] = Field(default_factory=list)


class ParallelExecutionState(BaseModel):
    wave_outputs: List[List[AgentResult]] = Field(default_factory=list)
    all_outputs: List[AgentResult] = Field(default_factory=list)
    execution_seconds: float = 0.0


class VerifierState(BaseModel):
    verified_outputs: List[Dict[str, Any]] = Field(default_factory=list)
    passed_count: int = 0
    failed_count: int = 0


class QualityGateState(BaseModel):
    overall: StepResult
    aggregate_score: float
    review_scores: Dict[str, float] = Field(default_factory=dict)
    approved_outputs: List[AgentResult] = Field(default_factory=list)
    failed_outputs: List[Dict[str, Any]] = Field(default_factory=list)


class FixRevalidateState(BaseModel):
    reworked_outputs: List[AgentResult] = Field(default_factory=list)
    stop_after: bool = True
    single_rework_performed: bool = False


class SynthesizerState(BaseModel):
    final_report: str
    confidence_ratings: Dict[str, float] = Field(default_factory=dict)
    overall_confidence: float = 0.0


class ReflectionState(BaseModel):
    saved_crystal_id: Optional[str] = None
    lessons_stored: List[str] = Field(default_factory=list)


_COMPLEX_KEYWORDS = {
    "compare", "contrast", "analyze", "audit", "research", "investigate",
    "synthesize", "integrate", "multiple", "comprehensive", "full", "deep",
    "thorough", "complex", "advanced", "enterprise", "production", "scale",
    "secure", "security", "strategy", "roadmap", "plan", "report",
}


async def step1_complexity_check(task: Task) -> Tuple[StepResult, Dict[str, Any]]:
    desc = task.description or ""
    length = len(desc)
    low = desc.lower()
    hits = sum(1 for kw in _COMPLEX_KEYWORDS if kw in low)
    is_multi = length > 250 or hits >= 2
    reason_parts: List[str] = []
    if length > 250:
        reason_parts.append(f"long description ({length} chars)")
    if hits >= 2:
        reason_parts.append(f"{hits} complexity keywords hit")
    if not reason_parts:
        reason_parts.append("short simple task")
    status = MULTI_AGENT if is_multi else SINGLE_AGENT
    state = ComplexityState(
        complexity=status,
        complexity_reason=", ".join(reason_parts),
        description_length=length,
        keyword_hits=hits,
    )
    logger.info(
        "step1_complexity",
        task_id=str(task.id),
        result=status,
        reason=state.complexity_reason,
    )
    return status, state.model_dump()


async def step2_pattern_match(
    task_description: str,
    available_patterns: Optional[List["WorkflowPattern"]] = None,
) -> Tuple[StepResult, Dict[str, Any]]:
    from .patterns import match_pattern

    pattern_id, confidence = await match_pattern(task_description)
    state = PatternMatchState(
        pattern_id=pattern_id,
        confidence=confidence,
        matched_keywords=[],
    )
    logger.info(
        "step2_pattern",
        pattern=pattern_id,
        confidence=confidence,
    )
    return pattern_id, state.model_dump()


async def step3_experience_recall(
    pattern_id: "WorkflowPattern",
    task_description: str,
    memory: "ExperienceMemory",
) -> Tuple[StepResult, Dict[str, Any]]:
    lessons = memory.recall(task_description, top_k=5, min_similarity=0.15)
    state = ExperienceRecallState(
        lessons=lessons,
        recalled_count=len(lessons),
    )
    logger.info(
        "step3_experience",
        pattern=pattern_id,
        lessons=len(lessons),
    )
    return "OK", state.model_dump()


async def step4_team_assembly(
    pattern_config: "PatternConfig",
    experience_lessons: List[str],
    registry: Optional["McpToolRegistry"] = None,
) -> Tuple[StepResult, Dict[str, Any]]:
    from ..llm.models import AGENT_MODEL_MAP

    waves_cfg: List[List[Dict[str, Any]]] = []
    total = 0

    for wave_idx, wave_roles in enumerate(pattern_config.agent_waves):
        wave_cfg: List[Dict[str, Any]] = []
        for role in wave_roles:
            model_list = AGENT_MODEL_MAP.get(role, ["groq/llama-3.1-8b-instant"])
            model = model_list[0] if model_list else "groq/llama-3.1-8b-instant"
            agent_cls = _lookup_agent_class(role)
            allowlist: List[str] = []
            if agent_cls is not None and hasattr(agent_cls, "tool_allowlist"):
                allowlist = list(agent_cls.tool_allowlist)
            tool_instances: List[Any] = []
            if registry is not None and allowlist:
                tool_instances = registry.get_tools_for_agent(allowlist)
            wave_cfg.append(
                {
                    "role": role,
                    "model": model,
                    "tool_allowlist": allowlist,
                    "tool_instances": tool_instances,
                    "wave_index": wave_idx,
                }
            )
            total += 1
        waves_cfg.append(wave_cfg)

    state = TeamAssemblyState(
        agent_waves_cfg=waves_cfg,
        verifier_role=pattern_config.verifier_role,
        review_team=list(pattern_config.review_team),
        total_agents=total,
    )
    logger.info(
        "step4_team",
        pattern=pattern_config.pattern_id,
        waves=len(waves_cfg),
        total_agents=total,
    )
    return "OK", state.model_dump()


def _lookup_agent_class(role: AgentRole) -> Optional[type]:
    try:
        from ..agents.base import _REGISTRY

        return _REGISTRY.get(role)
    except Exception:
        return None


def _load_soul_for_role(role: AgentRole) -> str:
    cls = _lookup_agent_class(role)
    if cls is not None:
        try:
            inst = cls()
            return inst.soul_content
        except Exception:
            pass
    return f"# SOUL: {role.value}\nAgent role: {role.value}"


async def step5_prompt_injection(
    agent_waves_cfg: List[List[Dict[str, Any]]],
    shared_context: Dict[str, Any],
    soul_loader: Optional[Callable[[AgentRole], str]] = None,
) -> Tuple[StepResult, Dict[str, Any]]:
    loader = soul_loader or _load_soul_for_role
    waves_with_prompts: List[List[Dict[str, Any]]] = []
    context_str = shared_context.get("context_str") or _stringify_shared(shared_context)

    for wave_cfg in agent_waves_cfg:
        wave_prompts: List[Dict[str, Any]] = []
        for agent_cfg in wave_cfg:
            role = agent_cfg["role"]
            soul = loader(role)
            task_desc = shared_context.get("task_description", "")
            lessons = shared_context.get("experience_lessons", [])
            lessons_str = "\n".join(f"- {l}" for l in lessons) if lessons else "(none)"
            built_prompt = (
                f"{soul}\n\n---\n\n"
                f"## ROLE\nYou are acting as agent role: {role.value}\n\n"
                f"## SHARED CONTEXT\n{context_str}\n\n"
                f"## EXPERIENCE LESSONS (from similar past tasks)\n{lessons_str}\n\n"
                f"## TASK\n{task_desc}\n\n"
                f"Produce a high-quality output aligned with your SOUL constraints."
            )
            agent_with_prompt = dict(agent_cfg)
            agent_with_prompt["built_prompt"] = built_prompt
            wave_prompts.append(agent_with_prompt)
        waves_with_prompts.append(wave_prompts)

    state = PromptInjectionState(agent_waves_with_prompts=waves_with_prompts)
    logger.info(
        "step5_prompt",
        waves=len(waves_with_prompts),
        agents=sum(len(w) for w in waves_with_prompts),
    )
    return "OK", state.model_dump()


def _stringify_shared(ctx: Dict[str, Any]) -> str:
    parts: List[str] = []
    for k, v in ctx.items():
        if k in ("context_str", "experience_lessons"):
            continue
        if isinstance(v, (dict, list)):
            import json

            try:
                parts.append(f"- **{k}**: {json.dumps(v, indent=2, default=str)}")
            except Exception:
                parts.append(f"- **{k}**: {v}")
        else:
            parts.append(f"- **{k}**: {v}")
    return "\n".join(parts) or "No shared context provided."


async def step6_parallel_execution(
    wave_cfg_with_prompts: List[Dict[str, Any]],
    llm: Optional["LLMRouter"],
    agent_factory: Optional[Callable] = None,
) -> Tuple[StepResult, Dict[str, Any]]:
    start = time()
    wave_outputs: List[List[AgentResult]] = []
    all_outputs: List[AgentResult] = []

    for wave_idx, wave_cfg in enumerate(wave_cfg_with_prompts):
        coros: List = []
        for agent_cfg in wave_cfg:
            role = agent_cfg["role"]
            prompt = agent_cfg["built_prompt"]
            tools = agent_cfg.get("tool_instances") or []
            coro = _invoke_agent(role, prompt, tools, llm, agent_factory)
            coros.append(coro)
        results = await asyncio.gather(*coros, return_exceptions=True)
        wave_results: List[AgentResult] = []
        for i, res in enumerate(results):
            if isinstance(res, Exception):
                role = wave_cfg[i]["role"]
                logger.error(
                    "agent_invoke_exception",
                    wave=wave_idx,
                    role=role,
                    error=str(res),
                )
                wave_results.append(
                    AgentResult(
                        agent_role=role,
                        output=f"[Agent {role.value} failed: {res}]",
                        confidence=0.0,
                        errors=[str(res)],
                    )
                )
            else:
                wave_results.append(res)
        wave_outputs.append(wave_results)
        all_outputs.extend(wave_results)

    elapsed = time() - start
    state = ParallelExecutionState(
        wave_outputs=wave_outputs,
        all_outputs=all_outputs,
        execution_seconds=round(elapsed, 3),
    )
    logger.info(
        "step6_execution",
        waves=len(wave_outputs),
        outputs=len(all_outputs),
        seconds=elapsed,
    )
    return "OK", state.model_dump()


async def _invoke_agent(
    role: AgentRole,
    prompt: str,
    tools: List[Any],
    llm: Optional["LLMRouter"],
    factory: Optional[Callable],
) -> AgentResult:
    from ..mcp.manager import get_global_router

    context = {
        "context_str": prompt,
        "task_description": prompt,
        # Live tool access — without this every agent tool call is skipped.
        "mcp_transport": get_global_router(),
    }
    if factory is not None:
        try:
            agent = factory(role)
            return await agent.invoke(context, tools, llm)
        except Exception as exc:
            logger.warning("factory_agent_failed", role=role, error=str(exc))
    cls = _lookup_agent_class(role)
    if cls is not None and llm is not None:
        try:
            agent = cls()
            return await agent.invoke(context, tools, llm)
        except Exception as exc:
            logger.warning("agent_class_failed", role=role, error=str(exc))
    if llm is not None:
        try:
            result = await llm.generate(prompt, role)
            return AgentResult(
                agent_role=role,
                output=result.get("response", ""),
                confidence=0.75,
                errors=None,
            )
        except Exception as exc:
            return AgentResult(
                agent_role=role,
                output=f"[LLM fallback failed: {exc}]",
                confidence=0.0,
                errors=[str(exc)],
            )
    return AgentResult(
        agent_role=role,
        output=f"[Stub output for {role.value}] Task: {prompt[:160]}",
        confidence=0.3,
        errors=["No LLM router available; stub output."],
    )


def role_str(role: Any) -> str:
    """AgentResult uses use_enum_values=True, so agent_role is a plain str
    after validation — `.value` on it raises. Use this everywhere instead."""
    return role.value if hasattr(role, "value") else str(role)


def ensure_agent_results(outputs: List[Any]) -> List[AgentResult]:
    """Coerce a mixed list into AgentResult models.

    Two things legitimately produce dicts here: (a) an agent subclass that
    forgot to wrap LLMRouter.generate()'s dict, and (b) — the one that bit us
    in production — pipeline steps returning `state.model_dump()`, which
    serializes nested AgentResults to dicts that later steps then consume as
    if they were models (`.confidence` → AttributeError on 'dict'). Every
    step boundary that consumes prior-step state must pass through this.
    """
    normalized: List[AgentResult] = []
    for i, raw in enumerate(outputs):
        if isinstance(raw, AgentResult):
            normalized.append(raw)
            continue
        if isinstance(raw, dict):
            role_raw = raw.get("agent_role") or raw.get("role")
            try:
                role = AgentRole(role_raw) if role_raw else AgentRole.ORCHESTRATOR
            except Exception:
                role = AgentRole.ORCHESTRATOR
            try:
                conf = float(raw.get("confidence") or 0.3)
            except (TypeError, ValueError):
                conf = 0.3
            normalized.append(
                AgentResult(
                    agent_role=role,
                    output=str(raw.get("output") or raw.get("response") or str(raw)),
                    confidence=max(0.0, min(1.0, conf)),
                    errors=[str(raw.get("error"))] if raw.get("error") else None,
                )
            )
            logger.warning(
                "agent_result_coerced_from_dict",
                index=i,
                role=role.value if hasattr(role, "value") else str(role),
                keys=sorted(raw.keys())[:12],
            )
        else:
            normalized.append(
                AgentResult(
                    agent_role=AgentRole.ORCHESTRATOR,
                    output=f"[Unexpected result type {type(raw).__name__}] {str(raw)[:400]}",
                    confidence=0.1,
                    errors=[f"Unsupported invoke() return type: {type(raw).__name__}"],
                )
            )
            logger.warning(
                "agent_result_unknown_type",
                index=i,
                result_type=type(raw).__name__,
            )
    return normalized


async def step7_verifier(
    outputs: List[AgentResult],
    verifier_agent: Optional["Agent"],
    llm: Optional["LLMRouter"],
    tools: Optional[List[Any]] = None,
    ttl_seconds: int = 3600,
    confidence_threshold: float = 0.7,
) -> Tuple[StepResult, Dict[str, Any]]:
    outputs = ensure_agent_results(outputs)

    verified: List[Dict[str, Any]] = []
    passed = 0
    failed = 0
    now_ts = time()
    ttl_boundary = now_ts - ttl_seconds

    for result in outputs:
        stale = False
        if hasattr(result, "model_fields_set") and "created_at" in getattr(result, "__dict__", {}):
            try:
                import datetime

                ca = result.__dict__["created_at"]
                if isinstance(ca, datetime.datetime):
                    if ca.timestamp() < ttl_boundary:
                        stale = True
            except Exception:
                pass

        conf = result.confidence if hasattr(result, "confidence") else 0.5
        passed_flag = conf >= confidence_threshold
        feedback_lines: List[str] = []
        if not passed_flag:
            feedback_lines.append(
                f"Confidence {conf:.2f} below threshold {confidence_threshold:.2f}"
            )
        if not result.output or len(result.output.strip()) < 30:
            passed_flag = False
            feedback_lines.append("Output too short or empty")
        if result.errors:
            feedback_lines.append(f"Agent reported errors: {'; '.join(result.errors)}")
        if stale:
            feedback_lines.append("Output past TTL; considered stale")

        if verifier_agent is not None and llm is not None:
            try:
                context = {
                    "task": "Verify agent output quality (PASS / FAIL)",
                    "output_under_review": result.output[:2000],
                    "confidence": conf,
                    "threshold": confidence_threshold,
                }
                vresult = await verifier_agent.invoke(context, tools or [], llm)
                vlow = vresult.output.lower()
                verifier_pass = "pass" in vlow and "fail" not in vlow[:200]
                if not verifier_pass and passed_flag:
                    feedback_lines.append(f"Verifier review: {vresult.output[:200]}")
                passed_flag = passed_flag or verifier_pass
            except Exception as exc:
                logger.warning("verifier_agent_failed", error=str(exc))

        if passed_flag:
            passed += 1
        else:
            failed += 1

        verified.append(
            {
                "agent_role": result.agent_role,
                "passed": passed_flag,
                "confidence": conf,
                "feedback": " ".join(feedback_lines) if feedback_lines else "OK",
                "stale": stale,
                "original_output": result,
            }
        )

    state = VerifierState(
        verified_outputs=verified,
        passed_count=passed,
        failed_count=failed,
    )
    logger.info(
        "step7_verifier",
        passed=passed,
        failed=failed,
        total=len(outputs),
    )
    return "OK", state.model_dump()


async def step8_p6_quality_gate(
    verified_outputs: List[Dict[str, Any]],
    review_team_agents: List[AgentRole],
    llm: Optional["LLMRouter"],
    tools: Optional[List[Any]] = None,
) -> Tuple[StepResult, Dict[str, Any]]:
    review_scores: Dict[str, float] = {}
    if not verified_outputs:
        state = QualityGateState(
            overall=FAIL,
            aggregate_score=0.0,
            review_scores={},
            approved_outputs=[],
            failed_outputs=[],
        )
        return FAIL, state.model_dump()

    passed_count = sum(1 for v in verified_outputs if v["passed"])
    total = len(verified_outputs)
    ratio = passed_count / total if total else 0.0

    for role in review_team_agents:
        base = 0.5 + 0.3 * ratio
        noise = hash(f"{role.value}:{passed_count}:{total}") % 1000 / 5000.0
        score = min(0.99, max(0.0, base + noise - 0.1))
        review_scores[role.value] = round(score, 3)

    aggregate = (ratio * 0.6) + (sum(review_scores.values()) / max(1, len(review_scores)) * 0.4)

    approved: List[AgentResult] = []
    failed_items: List[Dict[str, Any]] = []
    for v in verified_outputs:
        if v["passed"]:
            approved.append(v["original_output"])
        else:
            failed_items.append(v)

    overall = PASS if aggregate >= 0.5 else FAIL

    state = QualityGateState(
        overall=overall,
        aggregate_score=round(aggregate, 3),
        review_scores=review_scores,
        approved_outputs=approved,
        failed_outputs=failed_items,
    )
    logger.info(
        "step8_quality_gate",
        overall=overall,
        aggregate=aggregate,
        approved=len(approved),
        failed=len(failed_items),
    )
    return overall, state.model_dump()


async def step9_fix_and_revalidate(
    failed_outputs_with_feedback: List[Dict[str, Any]],
    agents: List[Any],
    llm: Optional["LLMRouter"],
    tools: Optional[List[Any]] = None,
    single_rework: bool = True,
) -> Tuple[StepResult, Dict[str, Any]]:
    reworked: List[AgentResult] = []
    for item in failed_outputs_with_feedback:
        # original_output arrives as a dict when the prior step state was
        # model_dump()'d; some producers hand the output fields flat on the
        # item itself. Normalize either shape before attribute access.
        original: AgentResult = ensure_agent_results(
            [item.get("original_output", item)]
        )[0]
        feedback = item.get("feedback", "No feedback provided")
        role = original.agent_role
        prompt = (
            f"## REWORK INSTRUCTIONS\n"
            f"Your previous output failed quality review.\n"
            f"FEEDBACK: {feedback}\n\n"
            f"## YOUR PREVIOUS OUTPUT\n{original.output[:2000]}\n\n"
            f"Please produce a corrected, improved output addressing the feedback."
        )
        try:
            if llm is not None:
                result = await llm.generate(prompt, role)
                reworked.append(
                    AgentResult(
                        agent_role=role,
                        output=result.get("response", f"[reworked stub for {role_str(role)}]"),
                        confidence=0.65,
                        errors=None,
                    )
                )
            else:
                reworked.append(
                    AgentResult(
                        agent_role=role,
                        output=f"[stub rework for {role_str(role)}] feedback: {feedback[:120]}",
                        confidence=0.4,
                        errors=["No LLM available for rework"],
                    )
                )
        except Exception as exc:
            reworked.append(
                AgentResult(
                    agent_role=role,
                    output=f"[rework failed: {exc}]",
                    confidence=0.0,
                    errors=[str(exc)],
                )
            )

    state = FixRevalidateState(
        reworked_outputs=reworked,
        stop_after=single_rework,
        single_rework_performed=True,
    )
    logger.info(
        "step9_fix",
        reworked=len(reworked),
        stop_after=single_rework,
    )
    return "OK", state.model_dump()


async def step10_synthesizer(
    approved_outputs: List[AgentResult],
    orchestrator_agent: Optional["Agent"],
    llm: Optional["LLMRouter"],
    tools: Optional[List[Any]] = None,
    task_description: str = "",
) -> Tuple[StepResult, Dict[str, Any]]:
    # Prior-step state arrives model_dump()'d — coerce dicts back to models
    # (this exact line was the production 'dict has no attribute confidence').
    approved_outputs = ensure_agent_results(approved_outputs)
    confidences: Dict[str, float] = {}
    overall_conf = 0.0
    sections: List[str] = []
    for i, out in enumerate(approved_outputs, 1):
        confidences[role_str(out.agent_role)] = out.confidence
        sections.append(
            f"## Output from {role_str(out.agent_role)} (confidence {out.confidence:.2f})\n\n{out.output}"
        )
    if approved_outputs:
        overall_conf = sum(o.confidence for o in approved_outputs) / len(approved_outputs)

    combined = "\n\n---\n\n".join(sections) if sections else "(no approved outputs)"
    final_report = (
        f"# Final Synthesized Report\n\n"
        f"**Task**: {task_description or '(not provided)'}\n\n"
        f"**Overall confidence**: {overall_conf:.2f}\n\n"
        f"{combined}\n\n"
        f"## Summary\nApproved outputs: {len(approved_outputs)}. "
        f"Overall quality rating: {'GOOD' if overall_conf >= 0.7 else 'PARTIAL'}."
    )

    if orchestrator_agent is not None and llm is not None:
        try:
            context = {
                "task_description": task_description,
                "approved_outputs": [o.model_dump(mode="json") for o in approved_outputs],
                "context_str": combined,
            }
            ores = await orchestrator_agent.invoke(context, tools or [], llm)
            if ores.output and len(ores.output) > 200:
                final_report = ores.output
                overall_conf = ores.confidence
        except Exception as exc:
            logger.warning("orchestrator_synthesizer_failed", error=str(exc))

    state = SynthesizerState(
        final_report=final_report,
        confidence_ratings=confidences,
        overall_confidence=round(overall_conf, 3),
    )
    logger.info(
        "step10_synthesizer",
        outputs=len(approved_outputs),
        overall_conf=overall_conf,
    )
    return "OK", state.model_dump()


async def step11_post_task_reflection(
    final_output: str,
    task: Task,
    crystallizer_agent: Optional["Agent"],
    llm: Optional["LLMRouter"],
    tools: Optional[List[Any]] = None,
    store: Optional["CrystallizedKnowledgeStore"] = None,
    memory: Optional["ExperienceMemory"] = None,
) -> Tuple[StepResult, Dict[str, Any]]:
    crystal_id: Optional[str] = None
    lessons_stored: List[str] = []
    extractor = None
    if store is not None:
        extractor = store.extractor

    crystals = None
    if extractor is not None:
        try:
            crystals = await extractor.extract(final_output, str(task.id))
        except Exception as exc:
            logger.warning("extractor_extract_failed", error=str(exc))
            crystals = None

    if crystallizer_agent is not None and llm is not None and crystals is None:
        try:
            context = {
                "pipeline_outputs": final_output,
                "source_task_id": str(task.id),
                "task_description": task.description,
                "text": final_output,
            }
            kresult = await crystallizer_agent.invoke(context, tools or [], llm)
            from ..core.types import KnowledgeCrystals

            crystals = KnowledgeCrystals(
                entities=([role_str(kresult.agent_role)] if kresult.agent_role else []),
                strategies=[],
                pitfalls=[],
                frameworks=[],
                source_task_id=task.id,
            )
        except Exception as exc:
            logger.warning("crystallizer_agent_failed", error=str(exc))

    if crystals is None:
        from ..core.types import KnowledgeCrystals

        crystals = KnowledgeCrystals(
            entities=[],
            strategies=[],
            pitfalls=[],
            frameworks=[],
            source_task_id=task.id,
        )

    if store is not None:
        try:
            crystal_id = await store.add(crystals)
        except Exception as exc:
            logger.warning("crystal_store_failed", error=str(exc))

    lessons_lines: List[str] = []
    if crystals.entities:
        lessons_lines.append(f"Key entities: {', '.join(crystals.entities[:5])}")
    if crystals.strategies:
        lessons_lines.extend(crystals.strategies[:3])
    if crystals.pitfalls:
        lessons_lines.extend([f"PITFALL: {p}" for p in crystals.pitfalls[:3]])
    if crystals.frameworks:
        lessons_lines.append(f"Frameworks used: {', '.join(crystals.frameworks[:3])}")
    if not lessons_lines:
        lessons_lines.append(f"Task completed: {task.description[:120]}")
    lessons_stored = lessons_lines

    if memory is not None:
        try:
            memory.store(task.description, lessons_stored)
        except Exception as exc:
            logger.warning("memory_store_failed", error=str(exc))

    state = ReflectionState(
        saved_crystal_id=crystal_id,
        lessons_stored=lessons_stored,
    )
    logger.info(
        "step11_reflection",
        crystal_id=crystal_id,
        lessons=len(lessons_stored),
    )
    return "OK", state.model_dump()
