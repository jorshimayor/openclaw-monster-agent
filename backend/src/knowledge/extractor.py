from __future__ import annotations

import re
from typing import List, Optional, TYPE_CHECKING

from pydantic import ValidationError

from ..core.logging import get_logger
from ..core.types import KnowledgeCrystals

if TYPE_CHECKING:
    from ..llm.router import LLMRouter

logger = get_logger(__name__)


class KnowledgeExtractor:
    def __init__(self, llm: Optional["LLMRouter"] = None) -> None:
        self.llm = llm

    def _split_sentences(self, text: str) -> List[str]:
        sentences = re.split(r"(?<=[.!?])\s+", text)
        return [s.strip() for s in sentences if s.strip()]

    def _extract_entities_heuristic(self, text: str) -> List[str]:
        entities: List[str] = []

        capitalized_phrases = re.findall(
            r"\b([A-Z][a-zA-Z0-9]+(?:\s+[A-Z][a-zA-Z0-9]+)+)\b", text
        )
        for phrase in capitalized_phrases:
            if len(phrase.split()) >= 2 and phrase not in entities:
                entities.append(phrase)

        python_ids = re.findall(
            r"\b([a-zA-Z_][a-zA-Z0-9_]{3,})\b", text
        )
        id_keywords = {
            "class", "function", "method", "module", "package", "async", "await",
            "return", "import", "from", "def", "self", "true", "false", "none",
            "and", "or", "not", "for", "while", "if", "elif", "else", "try",
            "except", "finally", "with", "raise", "pass", "break", "continue",
            "yield", "lambda", "global", "nonlocal", "del", "in", "is", "as",
            "the", "and", "for", "are", "but", "not", "you", "all", "can",
            "had", "her", "was", "one", "our", "out", "day", "get", "has",
            "him", "his", "how", "its", "let", "may", "new", "now", "old",
            "see", "two", "way", "who", "boy", "did", "its", "let", "put",
            "say", "she", "too", "use",
        }
        for pid in python_ids:
            lower = pid.lower()
            if lower not in id_keywords and pid not in entities:
                if re.search(r"[A-Z]", pid) or re.search(r"_", pid):
                    entities.append(pid)

        protocol_names = re.findall(
            r"\b(HTTP|HTTPS|TCP|UDP|IP|RPC|REST|GraphQL|gRPC|JSON|XML|YAML|HTML|CSS|JS|TS|SQL|NoSQL|WebSocket|TLS|SSL|OAuth|JWT|SAML|LDAP|SSH|FTP|SFTP|SMTP|POP|IMAP|DNS|DHCP|NAT|VPN|CIDR|EVM|EIP|ERC|BIP|SIP|ERC20|ERC721|ERC1155|Uniswap|Aave|Maker|Compound)\b",
            text,
        )
        for proto in protocol_names:
            if proto not in entities:
                entities.append(proto)

        return list(dict.fromkeys(entities))[:20]

    def _extract_strategies_heuristic(self, text: str) -> List[str]:
        strategies: List[str] = []
        sentences = self._split_sentences(text)
        keywords = {
            "strategy", "strategies", "approach", "approaches", "we use",
            "we apply", "we implement", "we follow", "best practice",
            "best practices", "recommended approach", "to solve this",
            "to handle this", "the way to", "method", "technique",
            "pattern", "tactic", "workflow",
        }
        for s in sentences:
            low = s.lower()
            if any(k in low for k in keywords):
                stripped = s.rstrip(".!?")
                if 10 < len(stripped) < 300 and stripped not in strategies:
                    strategies.append(stripped)
        return list(dict.fromkeys(strategies))[:15]

    def _extract_pitfalls_heuristic(self, text: str) -> List[str]:
        pitfalls: List[str] = []
        sentences = self._split_sentences(text)
        keywords = {
            "pitfall", "pitfalls", "watch out", "avoid", "common mistake",
            "common mistakes", "be careful", "beware", "danger", "risk",
            "issue", "issues", "bug", "bugs", "problem", "problems",
            "error", "errors", "failure", "failures", "vulnerability",
            "vulnerabilities", "exploit", "attack", "attack vector",
            "gotcha", "gotchas", "trap", "traps", "do not", "don't",
            "never", "shouldn't", "should not",
        }
        for s in sentences:
            low = s.lower()
            if any(k in low for k in keywords):
                stripped = s.rstrip(".!?")
                if 10 < len(stripped) < 300 and stripped not in pitfalls:
                    pitfalls.append(stripped)
        return list(dict.fromkeys(pitfalls))[:15]

    def _extract_frameworks_heuristic(self, text: str) -> List[str]:
        frameworks: List[str] = []
        words = re.findall(r"\b[A-Za-z][A-Za-z0-9_]+\b", text)

        er_suffix = re.compile(r"^[A-Z][a-zA-Z]+(er|or)$")
        orchestrator_suffix = re.compile(r"^[A-Z][a-zA-Z]+orchestrator$")
        pipeline_pattern = re.compile(r"^[A-Z][a-zA-Z0-9_]*Pipeline$")

        for w in words:
            if er_suffix.match(w) and len(w) >= 5:
                if w not in frameworks:
                    frameworks.append(w)
            if orchestrator_suffix.match(w):
                if w not in frameworks:
                    frameworks.append(w)
            if pipeline_pattern.match(w):
                if w not in frameworks:
                    frameworks.append(w)

        common_framework_keywords = {
            "orchestrator", "coordinator", "manager", "handler",
            "processor", "pipeline", "workflow", "controller", "router",
            "builder", "factory", "provider", "registry", "service",
            "repository", "adapter", "wrapper", "client", "server",
            "executor", "scheduler", "dispatcher", "broker",
        }
        for w in words:
            low = w.lower()
            if low in common_framework_keywords and w not in frameworks:
                frameworks.append(w)
            if low.endswith("pipeline") and w not in frameworks:
                frameworks.append(w)

        return list(dict.fromkeys(frameworks))[:15]

    async def extract(
        self,
        output_text: str,
        source_task_id: str,
    ) -> KnowledgeCrystals:
        if not output_text:
            raise ValueError("output_text cannot be empty")
        if not source_task_id:
            raise ValueError("source_task_id cannot be empty")

        from uuid import UUID

        try:
            task_uuid = UUID(str(source_task_id))
        except Exception:
            from uuid import uuid4

            task_uuid = uuid4()

        entities = self._extract_entities_heuristic(output_text)
        strategies = self._extract_strategies_heuristic(output_text)
        pitfalls = self._extract_pitfalls_heuristic(output_text)
        frameworks = self._extract_frameworks_heuristic(output_text)

        if len(entities) < 3 and self.llm is not None:
            try:
                llm_entities = await self._llm_extract_entities(output_text)
                for e in llm_entities:
                    if e not in entities:
                        entities.append(e)
                entities = entities[:20]
            except Exception as exc:
                logger.warning(
                    "llm_entity_extraction_failed",
                    error=str(exc),
                    entities_found=len(entities),
                )

        crystals = KnowledgeCrystals(
            entities=entities,
            strategies=strategies,
            pitfalls=pitfalls,
            frameworks=frameworks,
            source_task_id=task_uuid,
        )

        try:
            KnowledgeCrystals.model_validate(crystals.model_dump())
        except ValidationError as exc:
            logger.error("knowledge_crystals_validation_failed", error=str(exc))
            raise

        logger.info(
            "knowledge_extracted",
            entities=len(crystals.entities),
            strategies=len(crystals.strategies),
            pitfalls=len(crystals.pitfalls),
            frameworks=len(crystals.frameworks),
        )
        return crystals

    async def _llm_extract_entities(self, text: str) -> List[str]:
        if self.llm is None:
            return []
        from ..core.types import AgentRole

        preview = text[:2000]
        prompt = (
            "Extract 10-15 concrete technical ENTITIES (nouns: tools, libraries, "
            "protocols, classes, functions, modules, data structures) from the "
            "text below. Return as a bulleted markdown list with one entity per "
            "line, starting with '- '. No commentary.\n\n"
            f"TEXT:\n{preview}"
        )
        try:
            result = await self.llm.generate(prompt, AgentRole.KNOWLEDGE)
            response = result.get("response", "")
            lines = response.split("\n")
            extracted: List[str] = []
            for line in lines:
                stripped = line.strip()
                if stripped.startswith("- "):
                    item = stripped[2:].strip().rstrip(".")
                    if item and 2 < len(item) < 80:
                        extracted.append(item)
            return list(dict.fromkeys(extracted))[:15]
        except Exception as exc:
            logger.warning("llm_entity_call_failed", error=str(exc))
            return []
