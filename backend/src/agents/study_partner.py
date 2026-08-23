from __future__ import annotations

import json
from typing import Any, Dict, List

from ..core.types import AgentRole, AgentResult
from ..core.logging import get_logger
from .base import Agent, Tool
from ._utils import _call_tool, tool_matches

logger = get_logger(__name__)


class StudyPartnerAgent(Agent):
    role: AgentRole = AgentRole.STUDY
    model_profile: str = "groq/llama-3.1-8b-instant"
    tool_allowlist: List[str] = [
        "notion.*",
        "notion.API-post-page",
        "google_workspace.*",
        "slack.send_message",
    ]
    soul_path: str = "src/souls/study_partner.md"

    def _build_fallback_plan(self, topic: str, weeks: int, level: str) -> str:
        modules = max(1, min(8, weeks or 4))
        topic_str = topic or "Selected Subject"
        sections = [f"# Structured Study Plan: {topic_str}", ""]
        sections.append(f"> Level: {level} | Duration: {modules} modules (~{modules} weeks)")
        sections.append("")
        sections.append("## Overview")
        sections.append(
            f"A pragmatic, beginner-friendly plan to learn {topic_str}. "
            "Modules stack sequentially; quizzes at the end of every module."
        )
        sections.append("")

        topic_lower = topic_str.lower()
        sample_topics = [
            "Foundations & Mental Models",
            "Core Primitives Deep Dive",
            "First Hands-On Project",
            "Common Patterns & Anti-Patterns",
            "Tooling & Testing",
            "Security / Performance / Operations",
            "Capstone Project Design",
            "Advanced Topics & What's Next",
        ]
        for i in range(modules):
            title = sample_topics[i % len(sample_topics)]
            sections.append(f"## Module {i + 1}: {title}")
            sections.append("")
            sections.append("### Learning Objectives")
            sections.append(
                f"1. Explain {title.lower()} in plain English with 1 analogy."
            )
            sections.append("2. Implement a 50-line working example.")
            sections.append("3. Debug 3 common issues in this module.")
            sections.append("")
            sections.append("### Topics")
            sections.append(f"- {topic_str} — {title}: concept 1")
            sections.append(f"- {topic_str} — {title}: concept 2")
            sections.append(f"- {topic_str} — {title}: concept 3")
            sections.append("")
            sections.append("### Practice Exercise")
            sections.append(
                f"Build a mini-project using only Module {i + 1} ideas. "
                "Do NOT look ahead. Commit your code to GitHub with a descriptive README."
            )
            sections.append("")
            sections.append("### Comprehension Quiz (5 questions)")
            sections.append(f"1. Define {title.lower()} in your own words.")
            sections.append("2. When would you use this vs. skip it? Give 1 scenario each.")
            sections.append("3. Give 2 pitfalls from this module.")
            sections.append(f"4. Write a 10-line snippet demonstrating a core {topic_lower} concept.")
            sections.append("5. How does this module connect to Module 1 (or next module)?")
            sections.append("")

        sections.append("## Final Capstone")
        sections.append("Build a non-trivial project that uses every module. Write a 1-page post-mortem.")
        sections.append("")
        sections.append("## Recommended Pace")
        sections.append("- 1 module / week, 5 study sessions / week, 60-90 min each.")
        sections.append("- Spend 40% reading, 60% coding.")
        sections.append("- After every quiz: revisit anything you scored <70%.")
        sections.append("")
        return "\n".join(sections)

    async def invoke(
        self, context: Dict[str, Any], tools: List[Tool], llm,
        extra_llm_kwargs: Optional[Dict[str, Any]] = None,
    ) -> AgentResult:
        topic = context.get("topic") or context.get(
            "subject", context.get("description", "No study topic provided.")
        )
        level = context.get("level", "beginner")
        weeks = int(context.get("duration_weeks", 4))
        prior = context.get("prior_knowledge", "")
        goal = context.get("learning_goal", "Build a small project and explain the ideas to someone else.")
        extra = context.get("extra_instructions", "")
        mcp_transport = context.get("mcp_transport")
        tool_names = [t.name for t in tools] if tools else []

        prompt = self._build_prompt(
            {
                "topic": topic,
                "level": level,
                "duration_weeks": weeks,
                "prior_knowledge": prior,
                "learning_goal": goal,
            },
            extra_instructions=(
                f"{extra}\nReturn a STRUCTURED STUDY PLAN in markdown with EXACTLY these sections:\n"
                f"# Structured Study Plan: {topic}\n"
                f"## Overview (who this is for, level, duration, goal)\n"
                f"Repeat a section for EACH module: \n"
                f"## Module N: <Title>\n"
                f"### Learning Objectives (3 bullets with verbs)\n"
                f"### Topics (3-6 bullets)\n"
                f"### Practice Exercise (hands-on, measurable)\n"
                f"### Comprehension Quiz (5 mixed-format questions + answer hints at very bottom of module)\n"
                f"Then:\n"
                f"## Final Capstone Project\n"
                f"## Recommended Cadence & Resource List\n"
                f"Keep every module beginner-friendly and beginner-correct. "
                f"Voice: pragmatic, hands-on, 'I break things so you don't have to.' "
                f"Total modules: {max(1, min(8, weeks))}."
            ),
        )

        try:
            result = await llm.generate(prompt, self.role, **(extra_llm_kwargs or {}))
            output = result["response"]
            confidence = 0.84
            errors = None
        except Exception as e:
            logger.error("study_partner_invoke_error", error=str(e))
            output = self._build_fallback_plan(topic, weeks, level) + (
                f"\n\n_Fallback plan; LLM error: {e}"
            )
            confidence = 0.52
            errors = [str(e)]

        try:
            has_notion_create = "notion.API-post-page" in tool_names or any(
                tool_matches(self.tool_allowlist, n) and "API-post-page" in n for n in tool_names
            )
            if has_notion_create:
                from ..core.config import get_settings

                db_id = get_settings().notion_db_id
                meta_line = f"level: {level} · duration_weeks: {weeks} · topic: {topic}"
                blocks = [
                    {"object": "block", "type": "paragraph",
                     "paragraph": {"rich_text": [{"text": {"content": chunk}}]}}
                    for chunk in ([meta_line] + [output[i:i + 1800] for i in range(0, min(len(output), 9000), 1800)])
                ]
                notion_result = await _call_tool(
                    "notion.API-post-page",
                    {
                        "parent": {"database_id": db_id},
                        "properties": {"title": {"title": [{"text": {"content": f"Study Plan: {topic}"}}]}},
                        "children": blocks,
                    },
                    transport=mcp_transport,
                )
                if notion_result.get("skipped"):
                    logger.info(
                        "study_partner_notion_save_skipped",
                        reason=notion_result.get("reason"),
                    )
                else:
                    logger.info("study_partner_would_save_plan_to_notion", topic=topic)
                    output = output + "\n\n---\n[StudyPartnerAgent] would save plan to Notion (tool available)."
        except Exception as notion_err:
            logger.warning("study_partner_notion_save_failed", error=str(notion_err))

        return AgentResult(
            agent_role=self.role,
            output=output,
            confidence=confidence,
            errors=errors,
        )
