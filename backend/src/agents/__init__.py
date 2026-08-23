from __future__ import annotations

from typing import Dict, Optional

from ..core.logging import get_logger
from ..core.types import AgentRole
from .base import Agent, Tool, _REGISTRY

from .orchestrator import OrchestratorAgent
from .content_web2 import ContentWeb2Agent
from .content_web3 import ContentWeb3Agent
from .football_analyst import FootballAnalystAgent
from .editor_reviewer import EditorReviewerAgent
from .security_auditor import SecurityAuditorAgent
from .knowledge_crystallizer import KnowledgeCrystallizerAgent
from .study_partner import StudyPartnerAgent
from .personal_assistant import PersonalAssistantAgent

logger = get_logger(__name__)


ROLE_TO_CLASS: Dict[AgentRole, type[Agent]] = {
    AgentRole.PERSONAL_ASSISTANT: PersonalAssistantAgent,
    AgentRole.ORCHESTRATOR: OrchestratorAgent,
    AgentRole.CONTENT_WEB2: ContentWeb2Agent,
    AgentRole.CONTENT_WEB3: ContentWeb3Agent,
    AgentRole.FOOTBALL: FootballAnalystAgent,
    AgentRole.EDITOR: EditorReviewerAgent,
    AgentRole.SECURITY: SecurityAuditorAgent,
    AgentRole.KNOWLEDGE: KnowledgeCrystallizerAgent,
    AgentRole.STUDY: StudyPartnerAgent,
}

for _role, _cls in ROLE_TO_CLASS.items():
    if _role not in _REGISTRY:
        _REGISTRY[_role] = _cls


def get_agent(role: AgentRole | str) -> Agent:
    if isinstance(role, str):
        try:
            role_enum = AgentRole(role.upper())
        except ValueError:
            raise ValueError(f"Unknown agent role: {role}")
    else:
        role_enum = role

    cls = ROLE_TO_CLASS.get(role_enum) or _REGISTRY.get(role_enum)
    if cls is None:
        raise ValueError(f"No agent registered for role: {role_enum}")
    logger.debug("agent_factory_instantiate", role=role_enum.value, cls=cls.__name__)
    return cls()


def list_agents() -> Dict[str, dict]:
    out: Dict[str, dict] = {}
    for role, cls in ROLE_TO_CLASS.items():
        out[role.value] = {
            "role": role.value,
            "class": cls.__name__,
            "model_profile": getattr(cls, "model_profile", None),
            "tool_allowlist": list(getattr(cls, "tool_allowlist", [])),
            "soul_path": getattr(cls, "soul_path", None),
        }
    return out


__all__ = [
    "Agent",
    "Tool",
    "OrchestratorAgent",
    "ContentWeb2Agent",
    "ContentWeb3Agent",
    "FootballAnalystAgent",
    "EditorReviewerAgent",
    "SecurityAuditorAgent",
    "KnowledgeCrystallizerAgent",
    "StudyPartnerAgent",
    "PersonalAssistantAgent",
    "get_agent",
    "list_agents",
]
