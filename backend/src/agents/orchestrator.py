from __future__ import annotations

from typing import Any, Dict, List

from ..core.types import AgentRole, AgentResult
from ..core.logging import get_logger
from .base import Agent, Tool

logger = get_logger(__name__)


class OrchestratorAgent(Agent):
    role: AgentRole = AgentRole.ORCHESTRATOR
    model_profile: str = "groq/llama-3.1-8b-instant"
    tool_allowlist: List[str] = [
        "github.*",
        "notion.*",
        "google_workspace.*",
        "slack.*",
        "hashnode.*",
    ]
    soul_path: str = "src/souls/orchestrator.md"

    async def invoke(
        self, context: Dict[str, Any], tools: List[Tool], llm,
        extra_llm_kwargs: Optional[Dict[str, Any]] = None,
    ) -> AgentResult:
        task_description = context.get("task_description") or context.get(
            "description", "No task description provided."
        )
        extra = context.get("extra_instructions", "")
        prompt = self._build_prompt(
            {
                "task": task_description,
                "previous_outputs": context.get("previous_outputs", {}),
                "team": context.get("team", []),
            },
            extra_instructions=(
                f"{extra}\nBuild a concrete, ordered 11-step execution plan "
                f"per the Monster Agent pipeline. Format output as structured markdown with sections: "
                f"## 1. Task Complexity Assessment\n"
                f"## 2. Pattern Match\n"
                f"## 3. Experience Recall (Hypothetical)\n"
                f"## 4. Team Assembly (waves of agents + tools)\n"
                f"## 5. Prompt Injection Strategy\n"
                f"## 6. Parallel Execution Plan\n"
                f"## 7. Verifier Criteria\n"
                f"## 8. P6 Quality Gate Thresholds\n"
                f"## 9. Rework Policy\n"
                f"## 10. Synthesis Target\n"
                f"## 11. Reflection / Knowledge Capture Targets"
            ),
        )

        try:
            result = await llm.generate(prompt, self.role, **(extra_llm_kwargs or {}))
            output = result["response"]
            confidence = 0.88
            errors = None
        except Exception as e:
            logger.error("orchestrator_invoke_error", error=str(e))
            fallback = (
                "## 1. Task Complexity\nAssessed as: SINGLE_AGENT (fallback plan)\n\n"
                f"Task: {task_description}\n\n"
                "## 4. Team Assembly\nWave 1: [assigned agent]\n\n"
                "## 11. Reflection Targets\nCapture: entities, strategies, pitfalls, frameworks"
            )
            output = fallback
            confidence = 0.55
            errors = [str(e)]

        return AgentResult(
            agent_role=self.role,
            output=output,
            confidence=confidence,
            errors=errors,
        )
