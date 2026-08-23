from __future__ import annotations

import json
from typing import Any, Dict, List

from ..core.types import AgentRole, AgentResult
from ..core.logging import get_logger
from .base import Agent, Tool
from ._utils import _call_tool, tool_matches

logger = get_logger(__name__)


class ContentWeb3Agent(Agent):
    role: AgentRole = AgentRole.CONTENT_WEB3
    model_profile: str = "groq/gpt-oss-120b"
    tool_allowlist: List[str] = [
        "github.get_file_contents",
        "github.list_pull_requests",
        "github.list_commits",
        "notion.*",
        "hashnode.read_posts",
    ]
    soul_path: str = "src/souls/content_web3.md"

    async def invoke(
        self, context: Dict[str, Any], tools: List[Tool], llm,
        extra_llm_kwargs: Optional[Dict[str, Any]] = None,
    ) -> AgentResult:
        brief = context.get("content_brief") or context.get(
            "description", "No Web3 writing brief provided."
        )
        title = context.get("title", context.get("topic", "Untitled Web3 Deep Dive"))
        chain = context.get("blockchain", "Ethereum / EVM-compatible")
        audience = context.get("audience", "Web2 devs moving into Web3")
        extra = context.get("extra_instructions", "")
        code_refs = list(context.get("code_references", []))
        mcp_transport = context.get("mcp_transport")

        tool_names = [t.name for t in tools] if tools else []
        github_repo_ref = context.get("github_repo", "jorshimayor/*")

        try:
            if "github.get_file_contents" in tool_names or any(
                tool_matches(self.tool_allowlist, n) and "get_file_contents" in n for n in tool_names
            ):
                owner, _, repo_name = github_repo_ref.partition("/")
                repo_result = await _call_tool(
                    "github.get_file_contents",
                    {"owner": owner or "jorshimayor", "repo": repo_name or github_repo_ref, "path": ""},
                    transport=mcp_transport,
                )
                if not repo_result.get("skipped"):
                    code_refs.append(
                        f"[github.get_file_contents] {github_repo_ref}: {json.dumps(repo_result, default=str)[:600]}"
                    )
        except Exception as tool_err:
            logger.warning("content_web3_github_repo_tool_failed", error=str(tool_err))

        try:
            if "github.list_pull_requests" in tool_names or any(
                tool_matches(self.tool_allowlist, n) and "list_pull_requests" in n for n in tool_names
            ):
                owner, _, repo_name = github_repo_ref.partition("/")
                prs_result = await _call_tool(
                    "github.list_pull_requests",
                    {"owner": owner or "jorshimayor", "repo": repo_name or github_repo_ref, "state": "closed", "perPage": 10},
                    transport=mcp_transport,
                )
                if not prs_result.get("skipped"):
                    code_refs.append(
                        f"[github.list_pull_requests] recent audits/PRs: {json.dumps(prs_result, default=str)[:600]}"
                    )
        except Exception as tool_err:
            logger.warning("content_web3_github_prs_tool_failed", error=str(tool_err))

        prompt = self._build_prompt(
            {
                "title": title,
                "blockchain_context": chain,
                "audience": audience,
                "brief": brief,
                "code_references": code_refs,
            },
            extra_instructions=(
                    f"{extra}\nProduce a Web3 technical article in markdown. "
                    f"Use: `# Title`, `## Prerequisites`, `## Core Concept`, "
                    f"`## Minimal Example` (with a solidity/vyper/typescript code block), "
                    f"`## Common Pitfalls` (I break smart contracts more often than I should...), "
                    f"`## AI × AI-Web3 Bridge Notes` (how AI and Web3 intersect here). "
                    f"Keep it beginner-friendly but technically accurate. "
                    f"End with a security disclaimer (this is not financial advice). "
                    f"Conclude with 3 places to read more."
                    + (f"\n\nAdditional code refs / audits via MCP tools:\n" + "\n".join(code_refs) if code_refs else "")
                ),
        )

        try:
            result = await llm.generate(prompt, self.role, **(extra_llm_kwargs or {}))
            output = result["response"]
            confidence = 0.85
            errors = None
        except Exception as e:
            logger.error("content_web3_invoke_error", error=str(e))
            fallback = (
                f"# {title}\n\n"
                f"> Context: {chain} | Audience: {audience} | Draft (LLM fallback)\n\n"
                f"## Prerequisites\n"
                f"- Basic {chain} wallet & tools\n- Devnet familiarity\n- Curiosity\n\n"
                f"## Core Concept\n"
                f"{brief}\n\n"
                f"## Minimal Example\n"
                f"```solidity\n"
                f"// SPDX-License-Identifier: MIT\n"
                f"pragma solidity ^0.8.24;\n"
                f"contract Minimal {{ uint256 public count = 0; }}\n"
                f"```\n\n"
                f"## Common Pitfalls\n"
                f"- Reentrancy\n- Integer overflow (pre 0.8)\n- Off-by-one in loops\n\n"
                f"## AI × Web3 Bridge\n"
                f"LLMs can draft tests and audit; humans must verify. On-chain verifiable inference is coming.\n\n"
                f"⚠️ *Not financial advice. Educational only.\n\n"
                f"_LLM failed: {e}"
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
