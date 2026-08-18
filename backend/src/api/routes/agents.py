from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ...agents import get_agent, list_agents as agents_list_agents
from ...core.logging import get_logger
from ...core.types import AgentRole, AgentResult

logger = get_logger(__name__)
router = APIRouter(prefix="/api/agents", tags=["agents"])


class AgentInfo(BaseModel):
    role: str
    status: str
    description: str
    model_profile: str
    tool_allowlist: List[str]
    soul_file: str


class AgentDetailResponse(BaseModel):
    role: str
    status: str
    description: str
    model_profile: str
    tool_allowlist: List[str]
    soul_file: str
    healthy: bool
    last_run: Optional[str] = None


class AgentInvokeRequest(BaseModel):
    context: Dict[str, Any]


class AgentInvokeResponse(AgentResult):
    pass


_DESCRIPTIONS: Dict[str, str] = {
    "ORCHESTRATOR": "Project Lead Agent — decomposes tasks into the 11-step pipeline, assembles agent teams, synthesizes outputs.",
    "CONTENT_WEB2": "Web2 Content Builder — drafts blog posts, tutorials, and technical docs for traditional Web2 audiences.",
    "CONTENT_WEB3": "Web3 Content Builder — drafts smart contract walkthroughs, DeFi deep-dives, and AI × Web3 explainers.",
    "FOOTBALL": "Football Data Analyst — produces xG-anchored match reports, scouting dossiers, and tactical breakdowns.",
    "EDITOR": "Editor & Reviewer — scores content quality, flags gaps, and runs the P6 quality gate (0-10 score + verdict).",
    "SECURITY": "Security Auditor — audits code & smart contracts; ranks findings per CVSS 3.1 severity.",
    "KNOWLEDGE": "Knowledge Crystallizer — distills completed work into reusable entities/strategies/pitfalls/frameworks.",
    "STUDY": "Study Partner — builds module-based study plans with exercises and quizzes for any technical topic.",
}


def _normalize_role(role: str) -> AgentRole:
    try:
        return AgentRole(role.upper())
    except ValueError:
        try:
            return AgentRole(role)
        except ValueError:
            mapping = {
                "orchestrator": AgentRole.ORCHESTRATOR,
                "content_web2": AgentRole.CONTENT_WEB2,
                "content_web3": AgentRole.CONTENT_WEB3,
                "football": AgentRole.FOOTBALL,
                "editor": AgentRole.EDITOR,
                "security": AgentRole.SECURITY,
                "knowledge": AgentRole.KNOWLEDGE,
                "study": AgentRole.STUDY,
            }
            if role.lower() in mapping:
                return mapping[role.lower()]
            raise HTTPException(status_code=404, detail=f"Unknown agent role: {role}")


@router.get("", response_model=List[AgentInfo])
async def list_agents(request: Request):
    logger.info("agents_list_requested")
    registry = agents_list_agents()
    result: List[AgentInfo] = []
    for role_value, meta in registry.items():
        result.append(
            AgentInfo(
                role=role_value,
                status="READY",
                description=_DESCRIPTIONS.get(role_value, "Specialized agent."),
                model_profile=str(meta.get("model_profile", "nvidia/deepseek-v4-flash")),
                tool_allowlist=list(meta.get("tool_allowlist", [])),
                soul_file=str(meta.get("soul_path", "")),
            )
        )
    result.sort(key=lambda a: a.role)
    return result


@router.get("/{role}", response_model=AgentDetailResponse)
async def get_agent_detail(request: Request, role: str):
    logger.info("agent_detail_requested", role=role)
    role_enum = _normalize_role(role)
    registry = agents_list_agents()
    role_value = role_enum.value
    meta = registry.get(role_value)
    if meta is None:
        raise HTTPException(status_code=404, detail=f"Agent not found: {role}")
    return AgentDetailResponse(
        role=role_value,
        status="READY",
        description=_DESCRIPTIONS.get(role_value, "Specialized agent."),
        model_profile=str(meta.get("model_profile", "nvidia/deepseek-v4-flash")),
        tool_allowlist=list(meta.get("tool_allowlist", [])),
        soul_file=str(meta.get("soul_path", "")),
        healthy=True,
        last_run=None,
    )


@router.post("/{role}/invoke", response_model=AgentInvokeResponse)
async def invoke_agent(
    request: Request,
    role: str,
    body: AgentInvokeRequest,
):
    logger.info("agent_invoke_requested", role=role, has_context=bool(body.context))
    role_enum = _normalize_role(role)
    llm_router = getattr(request.app.state, "llm_router", None)

    try:
        agent = get_agent(role_enum)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    context = dict(body.context or {})
    tools: List[Any] = []
    started = time.perf_counter()

    if llm_router is None:
        class _StubLLM:
            async def generate(self, prompt, role):
                return {
                    "provider": "stub",
                    "model": "stub-offline",
                    "response": f"[STUB LLM OFFLINE] Would process prompt for {role_enum.value} ({len(prompt)} chars).",
                }
        llm_router = _StubLLM()

    _ROLE_TIMEOUT_OVERRIDES: Dict[AgentRole, float] = {
        AgentRole.ORCHESTRATOR: 360.0,
        AgentRole.SECURITY: 240.0,
        AgentRole.EDITOR: 240.0,
        AgentRole.CONTENT_WEB3: 240.0,
    }
    _ROLE_MAX_TOKENS_OVERRIDES: Dict[AgentRole, int] = {
        AgentRole.ORCHESTRATOR: 2048,
    }
    route_timeout = _ROLE_TIMEOUT_OVERRIDES.get(role_enum, 180.0)
    extra_kwargs: Dict[str, Any] = {}
    if role_enum in _ROLE_MAX_TOKENS_OVERRIDES:
        extra_kwargs["max_tokens"] = _ROLE_MAX_TOKENS_OVERRIDES[role_enum]

    try:
        result = await asyncio.wait_for(
            agent.invoke(context, tools=tools, llm=llm_router, extra_llm_kwargs=extra_kwargs),
            timeout=route_timeout,
        )
    except asyncio.TimeoutError:
        logger.warning("agent_invoke_timeout", role=role_enum.value, timeout_s=route_timeout)
        raise HTTPException(
            status_code=504,
            detail=f"Agent invoke timed out ({int(route_timeout)}s)",
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("agent_invoke_failed", role=role_enum.value, error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))

    latency_ms = int((time.perf_counter() - started) * 1000)

    return AgentInvokeResponse(
        agent_role=result.agent_role,
        status=getattr(result, "status", "success"),
        output=result.output,
        summary=getattr(result, "summary", None),
        confidence=result.confidence,
        errors=result.errors,
        actions=getattr(result, "actions", None),
        references=getattr(result, "references", None),
        metadata={
            **(getattr(result, "metadata", {}) or {}),
            "latency_ms": latency_ms,
        },
    )
