from __future__ import annotations

from abc import ABC, abstractmethod
from importlib import resources
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from ..core.logging import get_logger
from ..core.types import AgentRole, AgentResult

if TYPE_CHECKING:
    from ..llm.router import LLMRouter

logger = get_logger(__name__)

_REGISTRY: Dict[AgentRole, "type[Agent]"] = {}


class Tool:
    def __init__(self, name: str, description: str = "") -> None:
        self.name = name
        self.description = description


class Agent(ABC):
    role: AgentRole
    model_profile: str
    tool_allowlist: List[str]
    soul_path: str

    _soul_cache: Optional[str] = None

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if hasattr(cls, "role") and cls.role is not None:
            _REGISTRY[cls.role] = cls

    def __init__(self) -> None:
        if not self.soul_path:
            raise ValueError(f"Agent {type(self).__name__} must define soul_path")
        self.soul_content: str = self.load_soul()

    def load_soul(self) -> str:
        if self._soul_cache is not None:
            return self._soul_cache

        try:
            soul_rel = Path(self.soul_path)
            module_parts = ["src", "souls"]
            if soul_rel.parent.name == "souls":
                file_name = soul_rel.name
            else:
                file_name = soul_rel.as_posix().replace("src/souls/", "")

            try:
                data = resources.files("src.souls").joinpath(file_name).read_text(encoding="utf-8")
                self._soul_cache = data
                return data
            except (FileNotFoundError, OSError, ImportError):
                pass

            project_root = Path(__file__).resolve().parent.parent.parent
            soul_file = project_root / "src" / "souls" / file_name
            if soul_file.exists():
                data = soul_file.read_text(encoding="utf-8")
                self._soul_cache = data
                return data

            fallback = project_root / self.soul_path
            if fallback.exists():
                data = fallback.read_text(encoding="utf-8")
                self._soul_cache = data
                return data

        except Exception as e:
            logger.warning("soul_load_failed", agent=self.role, error=str(e))

        default = (
            f"# SOUL: {self.role.value}\n"
            f"## Role\nAgent {self.role.value}\n"
            f"## Mission\nFulfill agent duties to the best of ability.\n"
        )
        self._soul_cache = default
        return default

    def _build_prompt(self, context: Dict[str, Any], extra_instructions: str = "") -> str:
        context_str = context.get("context_str") or self._stringify_context(context)
        prompt = (
            f"{self.soul_content}\n\n"
            f"---\n\n"
            f"## CONTEXT\n{context_str}\n\n"
            f"## EXTRA INSTRUCTIONS\n{extra_instructions or 'None.'}\n\n"
            f"## TASK\n"
            f"Act in your role as {self.role.value}. "
            f"Produce a high-quality output aligned with your SOUL constraints. "
            f"Return structured content appropriate for your role."
        )
        return prompt

    def _stringify_context(self, context: Dict[str, Any]) -> str:
        parts: List[str] = []
        for k, v in context.items():
            if k in ("llm", "tools", "context_str"):
                continue
            if isinstance(v, (dict, list)):
                import json

                try:
                    parts.append(f"- **{k}**: {json.dumps(v, indent=2, default=str)}")
                except Exception:
                    parts.append(f"- **{k}**: {v}")
            else:
                parts.append(f"- **{k}**: {v}")
        return "\n".join(parts) or "No additional context provided."

    @abstractmethod
    async def invoke(
        self,
        context: Dict[str, Any],
        tools: List[Tool],
        llm: "LLMRouter",
        extra_llm_kwargs: Optional[Dict[str, Any]] = None,
    ) -> AgentResult:
        ...
