from __future__ import annotations

from enum import Enum
from typing import Dict, List, Tuple

from pydantic import BaseModel, Field

from ..core.logging import get_logger
from ..core.types import AgentRole

logger = get_logger(__name__)


class WorkflowPattern(str, Enum):
    DRAFT_BLOG_POST = "DRAFT_BLOG_POST"
    AUDIT_CODE = "AUDIT_CODE"
    RESEARCH_REPORT = "RESEARCH_REPORT"
    STUDY_PLAN = "STUDY_PLAN"
    FOOTBALL_ANALYSIS = "FOOTBALL_ANALYSIS"
    GENERIC = "GENERIC"


class PatternConfig(BaseModel):
    pattern_id: WorkflowPattern
    description: str
    agent_waves: List[List[AgentRole]] = Field(
        description="Waves of parallel agents to execute"
    )
    verifier_role: AgentRole
    review_team: List[AgentRole]
    needs_knowledge_reflection: bool = True
    task_keywords: List[str] = Field(
        default_factory=list,
        description="Keywords used for pattern matching against task description",
    )


PATTERN_CONFIGS: Dict[WorkflowPattern, PatternConfig] = {
    WorkflowPattern.DRAFT_BLOG_POST: PatternConfig(
        pattern_id=WorkflowPattern.DRAFT_BLOG_POST,
        description="Draft a polished blog post: research + write + review + publish-ready output",
        agent_waves=[
            [AgentRole.CONTENT_WEB3, AgentRole.CONTENT_WEB2],
        ],
        verifier_role=AgentRole.EDITOR,
        review_team=[AgentRole.EDITOR, AgentRole.ORCHESTRATOR],
        needs_knowledge_reflection=True,
        task_keywords=[
            "blog", "post", "article", "write", "draft", "publish",
            "content", "medium", "hashnode", "dev.to", "tutorial",
            "guide", "how-to", "how to", "explain", "explainer",
        ],
    ),
    WorkflowPattern.AUDIT_CODE: PatternConfig(
        pattern_id=WorkflowPattern.AUDIT_CODE,
        description="Audit codebase or contract: security, quality, gas, test coverage + report",
        agent_waves=[
            [AgentRole.SECURITY, AgentRole.EDITOR],
        ],
        verifier_role=AgentRole.SECURITY,
        review_team=[AgentRole.SECURITY, AgentRole.ORCHESTRATOR],
        needs_knowledge_reflection=True,
        task_keywords=[
            "audit", "security", "review code", "code review", "vulnerability",
            "exploit", "bug", "smart contract", "contract audit", "solidity",
            "pentest", "penetration", "threat model", "risk", "sast", "dast",
        ],
    ),
    WorkflowPattern.RESEARCH_REPORT: PatternConfig(
        pattern_id=WorkflowPattern.RESEARCH_REPORT,
        description="Deep research report: gather sources, compare, cite, synthesize conclusions",
        agent_waves=[
            [AgentRole.CONTENT_WEB3, AgentRole.CONTENT_WEB2],
        ],
        verifier_role=AgentRole.EDITOR,
        review_team=[AgentRole.EDITOR, AgentRole.ORCHESTRATOR],
        needs_knowledge_reflection=True,
        task_keywords=[
            "research", "report", "compare", "analysis", "survey",
            "study", "investigate", "literature", "whitepaper",
            "benchmark", "market research", "competitive",
        ],
    ),
    WorkflowPattern.STUDY_PLAN: PatternConfig(
        pattern_id=WorkflowPattern.STUDY_PLAN,
        description="Build a study plan with spaced repetition and checkpoints",
        agent_waves=[
            [AgentRole.STUDY],
        ],
        verifier_role=AgentRole.EDITOR,
        review_team=[AgentRole.EDITOR, AgentRole.STUDY],
        needs_knowledge_reflection=True,
        task_keywords=[
            "study", "learn", "study plan", "curriculum", "syllabus",
            "course", "lesson", "flashcard", "spaced repetition",
            "exam", "prepare", "revision", "homework",
        ],
    ),
    WorkflowPattern.FOOTBALL_ANALYSIS: PatternConfig(
        pattern_id=WorkflowPattern.FOOTBALL_ANALYSIS,
        description="Tactical / transfer / fantasy football analysis with data + opinions",
        agent_waves=[
            [AgentRole.FOOTBALL],
        ],
        verifier_role=AgentRole.EDITOR,
        review_team=[AgentRole.EDITOR, AgentRole.FOOTBALL],
        needs_knowledge_reflection=True,
        task_keywords=[
            "football", "soccer", "premier league", "la liga", "bundesliga",
            "serie a", "ligue 1", "champions league", "europa league",
            "world cup", "euros", "copa america", "transfer", "tactic",
            "formation", "fantasy", "fpl", "match", "fixture", "player",
            "team", "manager", "xG", "expected goals",
        ],
    ),
    WorkflowPattern.GENERIC: PatternConfig(
        pattern_id=WorkflowPattern.GENERIC,
        description="Generic task: delegate to orchestrator + reviewer, no specialization",
        agent_waves=[
            [AgentRole.ORCHESTRATOR],
        ],
        verifier_role=AgentRole.EDITOR,
        review_team=[AgentRole.EDITOR],
        needs_knowledge_reflection=True,
        task_keywords=[],
    ),
}


def _keyword_overlap_score(task_description: str, keywords: List[str]) -> float:
    if not keywords:
        return 0.0
    low = task_description.lower()
    matched = sum(1 for kw in keywords if kw.lower() in low)
    if matched == 0:
        return 0.0
    return matched / len(keywords)


async def match_pattern(task_description: str) -> Tuple[WorkflowPattern, float]:
    if not task_description:
        return WorkflowPattern.GENERIC, 0.0

    scored: List[Tuple[float, WorkflowPattern]] = []
    for pattern, cfg in PATTERN_CONFIGS.items():
        score = _keyword_overlap_score(task_description, cfg.task_keywords)
        scored.append((score, pattern))

    scored.sort(key=lambda t: t[0], reverse=True)
    top_score, top_pattern = scored[0]

    if top_score <= 0:
        logger.info(
            "pattern_match_no_keywords",
            fallback=WorkflowPattern.GENERIC,
            task_preview=task_description[:60],
        )
        return WorkflowPattern.GENERIC, 0.0

    logger.info(
        "pattern_matched",
        pattern=top_pattern,
        confidence=top_score,
        runner_up=scored[1][1] if len(scored) > 1 else None,
        runner_up_score=scored[1][0] if len(scored) > 1 else None,
    )
    return top_pattern, top_score
