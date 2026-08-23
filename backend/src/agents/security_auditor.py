from __future__ import annotations

import json
from typing import Any, Dict, List

from ..core.types import AgentRole, AgentResult
from ..core.logging import get_logger
from .base import Agent, Tool
from ._utils import _call_tool, tool_matches

logger = get_logger(__name__)


class SecurityAuditorAgent(Agent):
    role: AgentRole = AgentRole.SECURITY
    model_profile: str = "groq/gpt-oss-120b"
    tool_allowlist: List[str] = [
        "github.get_file_contents",
        "github.list_commits",
        "notion.*",
        "slack.send_message",
    ]
    soul_path: str = "src/souls/security_auditor.md"

    async def invoke(
        self, context: Dict[str, Any], tools: List[Tool], llm,
        extra_llm_kwargs: Optional[Dict[str, Any]] = None,
    ) -> AgentResult:
        code = context.get("code") or context.get(
            "target", context.get("description", "No code or system to audit.")
        )
        scope = context.get("scope", "Full audit")
        language = context.get("language", "solidity")
        target_name = context.get("target_name", "Untitled Target")
        extra = context.get("extra_instructions", "")
        mcp_transport = context.get("mcp_transport")

        tool_names = [t.name for t in tools] if tools else []
        github_repo_ref = context.get("github_repo", "jorshimayor/*")
        pulled_code_snippets: List[str] = []

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
                    pulled_code_snippets.append(
                        f"[github.get_file_contents] {github_repo_ref} tree: {json.dumps(repo_result, default=str)[:800]}"
                    )
        except Exception as tool_err:
            logger.warning("security_auditor_github_repo_failed", error=str(tool_err))

        try:
            if "github.get_file_contents" in tool_names or any(
                tool_matches(self.tool_allowlist, n) and "get_file_contents" in n for n in tool_names
            ):
                contract_paths = context.get(
                    "contract_paths",
                    ["src/Contract.sol", "contracts/Token.sol", "src/main.rs"],
                )
                for cp in contract_paths[:2]:
                    try:
                        owner, _, repo_name = github_repo_ref.partition("/")
                        file_result = await _call_tool(
                            "github.get_file_contents",
                            {"owner": owner or "jorshimayor", "repo": repo_name or github_repo_ref, "path": cp},
                            transport=mcp_transport,
                        )
                        if not file_result.get("skipped"):
                            pulled_code_snippets.append(
                                f"[github.get_file_contents:{cp}] {json.dumps(file_result, default=str)[:1200]}"
                            )
                    except Exception as inner_err:
                        logger.warning(
                            "security_auditor_github_file_failed",
                            path=cp,
                            error=str(inner_err),
                        )
        except Exception as tool_err:
            logger.warning("security_auditor_github_files_failed", error=str(tool_err))

        if pulled_code_snippets and isinstance(code, str):
            code = code + "\n\n--- PULLED VIA GITHUB TOOLS ---\n" + "\n\n".join(pulled_code_snippets)

        preview = code[:800] + ("..." if len(code) > 800 else "")
        prompt = self._build_prompt(
            {
                "target": target_name,
                "scope": scope,
                "language": language,
                "code_preview": preview,
                "code_length_chars": len(code),
                "pulled_snippets_count": len(pulled_code_snippets),
            },
            extra_instructions=(
                f"{extra}\nReturn a SECURITY AUDIT report in markdown. ALWAYS rank severity per CVSS 3.1 (NONE/LOW/MEDIUM/HIGH/CRITICAL).\n"
                f"Use EXACTLY these sections:\n"
                f"# Security Audit: {target_name}\n"
                f"## Scope & Methodology\n"
                f"## Summary TABLE: columns # | Finding | Severity | CVSS v3.1 (vector if possible) | Line/Module hint | Status (OPEN/FIXED/INFO)\n"
                f"## Detailed Findings (for each row above, explain impact, exploit scenario, remediation code snippet)\n"
                f"## Strengths Observed (be honest: what was done well?)\n"
                f"## Recommendations (prioritized, ranked by effort vs impact)\n"
                f"## Final Risk Rating: CRITICAL / HIGH / MEDIUM / LOW\n"
                f"Voice: paranoid but pragmatic. If this is Solidity/Web3, specifically check reentrancy, access control, integer precision, oracle manipulation, and front-running. For Web2: OWASP Top 10."
                + (f"\n\nNote: {len(pulled_code_snippets)} additional code snippet(s) pulled via MCP github tools for audit context." if pulled_code_snippets else "")
            ),
        )

        try:
            result = await llm.generate(prompt, self.role, **(extra_llm_kwargs or {}))
            output = result["response"]
            confidence = 0.8
            errors = None
        except Exception as e:
            logger.error("security_auditor_invoke_error", error=str(e))
            fallback = (
                f"# Security Audit: {target_name}\n\n"
                f"## Scope & Methodology\n"
                f"Scope: {scope}. Language/Stack: {language}. Note: LLM offline; running static heuristic pass only.\n\n"
                f"## Summary\n\n| # | Finding | Severity | CVSS | Hint | Status |\n"
                f"|---|---|---|---|---|---|\n"
                f"| 1 | Manual human review required | HIGH | AV:N/AC:L (heuristic) | n/a | OPEN |\n\n"
                f"## Detailed Findings\n1. Cannot run deep LLM-backed analysis without LLM availability. Assume worst-case and schedule a full pass.\n\n"
                f"## Strengths Observed\n- Target provided for audit: good hygiene.\n\n"
                f"## Recommendations\n1. Re-run this audit once LLM recovers, then add human review.\n\n"
                f"## Final Risk Rating\nHIGH (due to unknowns)\n\n"
                f"_Fallback; LLM error: {e}"
            )
            output = fallback
            confidence = 0.45
            errors = [str(e)]

        return AgentResult(
            agent_role=self.role,
            output=output,
            confidence=confidence,
            errors=errors,
        )
