from __future__ import annotations

import json
from typing import Any, Dict, List

from ..core.types import AgentRole, AgentResult
from ..core.logging import get_logger
from .base import Agent, Tool
from ._utils import _call_tool, tool_matches

logger = get_logger(__name__)


class ContentWeb2Agent(Agent):
    role: AgentRole = AgentRole.CONTENT_WEB2
    model_profile: str = "groq/llama-3.1-8b-instant"
    tool_allowlist: List[str] = [
        "github.read_file",
        "github.read_repo",
        "notion.*",
        "google_workspace.docs_read",
        "hashnode.read_posts",
    ]
    soul_path: str = "src/souls/content_web2.md"

    async def invoke(
        self, context: Dict[str, Any], tools: List[Tool], llm,
        extra_llm_kwargs: Optional[Dict[str, Any]] = None,
    ) -> AgentResult:
        brief = context.get("content_brief") or context.get(
            "description", "No writing brief provided."
        )
        title = context.get("title", context.get("topic", "Untitled Draft"))
        audience = context.get("audience", "beginner developers")
        word_count = context.get("word_count", 1200)
        extra = context.get("extra_instructions", "")
        references = list(context.get("references", []))
        mcp_transport = context.get("mcp_transport")

        tool_names = [t.name for t in tools] if tools else []
        github_repo_ref = context.get("github_repo", "jorshimayor/*")

        try:
            if tool_matches(tool_names, "github.read_repo") or any(
                tool_matches(self.tool_allowlist, n) and "github.read_repo" in n for n in tool_names
            ) or (tool_names and "github.read_repo" in tool_names):
                repo_result = await _call_tool(
                    "github.read_repo",
                    {"repo": github_repo_ref},
                    transport=mcp_transport,
                )
                if not repo_result.get("skipped"):
                    references.append(
                        f"[github.read_repo] {github_repo_ref}: {json.dumps(repo_result, default=str)[:600]}"
                    )
        except Exception as tool_err:
            logger.warning("content_web2_github_tool_failed", error=str(tool_err))

        prompt = self._build_prompt(
            {
                "title": title,
                "audience": audience,
                "target_word_count": word_count,
                "brief": brief,
                "references": references,
            },
            extra_instructions=(
                f"{extra}\nProduce a complete, beginner-friendly Web2 blog article in markdown. "
                f"Use: `# Title`, `## H2 sections`, bullet lists, at least 1 code block or table, "
                f"and a **Key Takeaways** section at the end. "
                f"Keep voice pragmatic, like a senior engineer writing for juniors. "
                f"Aim for ~{word_count} words. "
                f"Prefer real-world examples over theory. "
                f"End with 3 actionable next steps."
                + (f"\n\nAdditional references pulled via MCP tools:\n" + "\n".join(references) if references else "")
            ),
        )

        try:
            result = await llm.generate(prompt, self.role, **(extra_llm_kwargs or {}))
            output = result["response"]
            confidence = 0.86
            errors = None
        except Exception as e:
            logger.error("content_web2_invoke_error", error=str(e))
            fallback = (
                f"# {title}\n\n"
                f"> Audience: {audience} | ~{word_count} words (draft)\n\n"
                f"## Introduction\n"
                f"This is a draft of {title}. We'll walk through the core ideas with concrete examples.\n\n"
                f"## What You'll Learn\n"
                f"- Core concepts that matter\n"
                f"- Common pitfalls\n"
                f"- Actionable next steps\n\n"
                f"## Key Takeaways\n"
                f"1. Start small, ship often.\n"
                f"2. Measure before you optimize.\n"
                f"3. Document while you build.\n\n"
                f"*Note: This is a fallback draft; the LLM call failed with: {e}"
            )
            output = fallback
            confidence = 0.5
            errors = [str(e)]

        return AgentResult(
            agent_role=self.role,
            output=output,
            confidence=confidence,
            errors=errors,
        )
