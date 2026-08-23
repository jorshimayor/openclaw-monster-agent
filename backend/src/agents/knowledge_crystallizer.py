from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from ..core.types import AgentRole, AgentResult, KnowledgeCrystals
from ..core.logging import get_logger
from .base import Agent, Tool
from ._utils import _call_tool, tool_matches

logger = get_logger(__name__)


class KnowledgeCrystallizerAgent(Agent):
    role: AgentRole = AgentRole.KNOWLEDGE
    model_profile: str = "groq/llama-3.1-8b-instant"
    tool_allowlist: List[str] = [
        "notion.*",
        "notion.API-post-page",
        "google_workspace.sheets_read",
    ]
    soul_path: str = "src/souls/knowledge_crystallizer.md"

    def _extract_naive(
        self, text: str, max_items: int = 12
    ) -> Dict[str, List[str]]:
        import re

        sentences = re.split(r"(?<=[.!?])\s+", text)
        entities: List[str] = []
        strategies: List[str] = []
        pitfalls: List[str] = []
        frameworks: List[str] = []

        keywords = {
            "entities": [
                "contract",
                "module",
                "library",
                "agent",
                "pipeline",
                "oracle",
                "pool",
                "hook",
                "protocol",
                "chain",
                "api",
                "endpoint",
                "schema",
                "database",
                "model",
            ],
            "strategies": [
                "use",
                "apply",
                "implement",
                "follow",
                "pattern",
                "strategy",
                "approach",
                "tactic",
                "method",
                "technique",
            ],
            "pitfalls": [
                "avoid",
                "beware",
                "pitfall",
                "risk",
                "danger",
                "attack",
                "exploit",
                "vulnerability",
                "bug",
                "issue",
                "problem",
                "mistake",
            ],
            "frameworks": [
                "framework",
                "library",
                "sdk",
                "standard",
                "stack",
                "architecture",
            ],
        }

        for s in sentences:
            low = s.lower()
            stripped = s.strip().rstrip(".!?")
            if not stripped:
                continue
            if any(k in low for k in keywords["entities"]) and len(entities) < max_items:
                entities.append(stripped[:160])
            if any(k in low for k in keywords["strategies"]) and len(strategies) < max_items:
                strategies.append(stripped[:200])
            if any(k in low for k in keywords["pitfalls"]) and len(pitfalls) < max_items:
                pitfalls.append(stripped[:200])
            if any(k in low for k in keywords["frameworks"]) and len(frameworks) < max_items:
                frameworks.append(stripped[:160])

        return {
            "entities": list(dict.fromkeys(entities)),
            "strategies": list(dict.fromkeys(strategies)),
            "pitfalls": list(dict.fromkeys(pitfalls)),
            "frameworks": list(dict.fromkeys(frameworks)),
        }

    async def invoke(
        self, context: Dict[str, Any], tools: List[Tool], llm,
        extra_llm_kwargs: Optional[Dict[str, Any]] = None,
    ) -> AgentResult:
        raw = context.get("pipeline_outputs") or context.get(
            "text", context.get("description", "No content to crystallize.")
        )
        source_task_id: Optional[UUID] = context.get("source_task_id")
        if source_task_id is None:
            source_task_id = uuid4()
        if isinstance(raw, dict):
            try:
                text = json.dumps(raw, indent=2, default=str)
            except Exception:
                text = str(raw)
        else:
            text = str(raw)

        mcp_transport = context.get("mcp_transport")
        tool_names = [t.name for t in tools] if tools else []

        preview = text[:800] + ("..." if len(text) > 800 else "")
        prompt = self._build_prompt(
            {
                "source_task_id": str(source_task_id),
                "content_preview": preview,
                "content_length_chars": len(text),
            },
            extra_instructions=(
                "Return a structured KnowledgeCrystals extraction as markdown with EXACT sections:\n"
                "# Knowledge Crystals\n"
                "## Entities (bulleted, 6-12 items: nouns/concepts/tools used)\n"
                "## Strategies (bulleted: what worked, approaches to repeat)\n"
                "## Pitfalls (bulleted: traps, mistakes, attack vectors to avoid)\n"
                "## Frameworks (bulleted: reusable patterns, libraries, checklists)\n"
                "## 1-Sentence TL;DR\n"
                "If unsure, err on the side of more items rather than fewer. Keep every item concrete."
            ),
        )

        crystals: Optional[KnowledgeCrystals] = None
        errors: Optional[List[str]] = None
        confidence = 0.83

        try:
            result = await llm.generate(prompt, self.role, **(extra_llm_kwargs or {}))
            output = result["response"]
            naive = self._extract_naive(text)
            crystals = KnowledgeCrystals(
                id=uuid4(),
                entities=naive["entities"] or [],
                strategies=naive["strategies"] or [],
                pitfalls=naive["pitfalls"] or [],
                frameworks=naive["frameworks"] or [],
                source_task_id=source_task_id,
            )
        except Exception as e:
            logger.error("knowledge_crystallizer_invoke_error", error=str(e))
            naive = self._extract_naive(text)
            crystals = KnowledgeCrystals(
                id=uuid4(),
                entities=naive["entities"],
                strategies=naive["strategies"],
                pitfalls=naive["pitfalls"],
                frameworks=naive["frameworks"],
                source_task_id=source_task_id,
            )
            output = (
                "# Knowledge Crystals (fallback heuristic extraction)\n\n"
                f"## Entities\n- " + "\n- ".join(crystals.entities or ["(none)"]) + "\n\n"
                f"## Strategies\n- " + "\n- ".join(crystals.strategies or ["(none)"]) + "\n\n"
                f"## Pitfalls\n- " + "\n- ".join(crystals.pitfalls or ["(none)"]) + "\n\n"
                f"## Frameworks\n- " + "\n- ".join(crystals.frameworks or ["(none)"]) + "\n\n"
                f"_LLM error: {e}"
            )
            confidence = 0.42
            errors = [str(e)]

        try:
            has_notion_create = "notion.API-post-page" in tool_names or any(
                tool_matches(self.tool_allowlist, n) and "API-post-page" in n for n in tool_names
            )
            if has_notion_create and crystals is not None:
                from ..core.config import get_settings

                db_id = get_settings().notion_db_id
                # Official Notion API shape (verified live): title property +
                # paragraph blocks; a summary line carries the crystal metadata.
                meta_line = (
                    f"source_task_id: {source_task_id} · "
                    f"entities: {len(crystals.entities)} · "
                    f"strategies: {len(crystals.strategies)}"
                )
                blocks = [
                    {"object": "block", "type": "paragraph",
                     "paragraph": {"rich_text": [{"text": {"content": chunk}}]}}
                    for chunk in ([meta_line] + [output[i:i + 1800] for i in range(0, min(len(output), 9000), 1800)])
                ]
                notion_result = await _call_tool(
                    "notion.API-post-page",
                    {
                        "parent": {"database_id": db_id},
                        "properties": {"title": {"title": [{"text": {"content": f"KnowledgeCrystal-{crystals.id}"}}]}},
                        "children": blocks,
                    },
                    transport=mcp_transport,
                )
                if notion_result.get("skipped"):
                    logger.info(
                        "knowledge_crystallizer_notion_skipped",
                        reason=notion_result.get("reason"),
                    )
                else:
                    logger.info(
                        "knowledge_crystallizer_notion_write_attempted",
                        crystal_id=str(crystals.id),
                    )
        except Exception as notion_err:
            logger.warning(
                "knowledge_crystallizer_notion_write_failed",
                error=str(notion_err),
            )

        structured_payload = crystals.model_dump(mode="json") if crystals else {}
        final_output = (
            f"{output}\n\n---\n\n"
            f"## Extracted KnowledgeCrystals (JSON)\n```json\n"
            f"{json.dumps(structured_payload, indent=2, default=str)}\n```"
        )

        return AgentResult(
            agent_role=self.role,
            output=final_output,
            confidence=confidence,
            errors=errors,
        )
