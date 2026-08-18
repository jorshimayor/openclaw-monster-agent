from __future__ import annotations

from typing import Any, Dict, List

from ..core.types import AgentRole, AgentResult
from ..core.logging import get_logger
from .base import Agent, Tool
from ._utils import _call_tool, tool_matches

logger = get_logger(__name__)


class EditorReviewerAgent(Agent):
    role: AgentRole = AgentRole.EDITOR
    model_profile: str = "groq/llama-3.1-8b-instant"
    tool_allowlist: List[str] = [
        "notion.*",
        "google_workspace.docs_read",
        "google_workspace.append_to_doc",
        "hashnode.read_posts",
    ]
    soul_path: str = "src/souls/editor_reviewer.md"

    async def invoke(
        self, context: Dict[str, Any], tools: List[Tool], llm,
        extra_llm_kwargs: Optional[Dict[str, Any]] = None,
    ) -> AgentResult:
        draft = context.get("draft") or context.get(
            "content", context.get("description", "No draft to review.")
        )
        title = context.get("title", "Untitled Submission")
        author = context.get("author", "Unknown")
        rubric = context.get(
            "rubric",
            ["clarity", "accuracy", "structure", "examples", "tone", "actionability"],
        )
        extra = context.get("extra_instructions", "")
        mcp_transport = context.get("mcp_transport")
        tool_names = [t.name for t in tools] if tools else []

        preview = draft[:400] + ("..." if len(draft) > 400 else "")
        prompt = self._build_prompt(
            {
                "title": title,
                "author": author,
                "rubric_dimensions": rubric,
                "draft_preview": preview,
                "draft_length_chars": len(draft),
            },
            extra_instructions=(
                f"{extra}\nReturn a STRUCTURED review as markdown with EXACTLY these sections.\n"
                f"# Editorial Review: {title}\n"
                f"## Overall Score /10 (a single integer 0-10 on its own line right after the heading)\n"
                f"## Rubric Scores TABLE: columns Dimension | Score /10 | Comment\n"
                f"## Findings (numbered list, each with severity: [LOW] [MEDIUM] [HIGH] [CRITICAL] prefix)\n"
                f"## Suggestions (numbered list of actionable rewrites / additions, ranked by impact)\n"
                f"## Verdict: one of { {'APPROVE', 'APPROVE_WITH_MINOR', 'REVISE_AND_RESUBMIT', 'REJECT'} }\n"
                f"Be specific; reference line-position hints when possible. Keep voice kind but direct."
            ),
        )

        try:
            result = await llm.generate(prompt, self.role, **(extra_llm_kwargs or {}))
            output = result["response"]
            confidence = 0.87
            errors = None
        except Exception as e:
            logger.error("editor_invoke_error", error=str(e))
            dimensions = rubric[:6]
            rows = "\n".join(f"| {d} | 6 | Initial pass." for d in dimensions)
            fallback = (
                f"# Editorial Review: {title}\n\n"
                f"## Overall Score /10\n6\n\n"
                f"## Rubric Scores\n\n| Dimension | Score /10 | Comment |\n"
                f"|---|---|---|\n{rows}\n\n"
                f"## Findings\n1. [MEDIUM] Draft review incomplete; LLM unavailable for deep inspection.\n\n"
                f"## Suggestions\n1. Re-run review when LLM recovers; meantime check flow manually.\n\n"
                f"## Verdict\nREVISE_AND_RESUBMIT\n\n"
                f"_Fallback review; error: {e}"
            )
            output = fallback
            confidence = 0.5
            errors = [str(e)]

        try:
            has_gdoc_append = "google_workspace.append_to_doc" in tool_names or any(
                tool_matches(self.tool_allowlist, n) and "append_to_doc" in n for n in tool_names
            )
            if has_gdoc_append:
                gdoc_result = await _call_tool(
                    "google_workspace.append_to_doc",
                    {
                        "document_id": context.get("google_doc_id", "default-review-doc"),
                        "content": f"# Editorial Review: {title}\n\n" + output,
                    },
                    transport=mcp_transport,
                )
                if gdoc_result.get("skipped"):
                    logger.info(
                        "editor_gdoc_append_skipped",
                        reason=gdoc_result.get("reason"),
                    )
                else:
                    logger.info(
                        "editor_would_have_written_review_to_google_doc",
                        title=title,
                    )
                    output = output + "\n\n---\n[EditorReviewerAgent] would have written review to Google Doc (tool available)."
        except Exception as gdoc_err:
            logger.warning("editor_gdoc_append_failed", error=str(gdoc_err))

        return AgentResult(
            agent_role=self.role,
            output=output,
            confidence=confidence,
            errors=errors,
        )
