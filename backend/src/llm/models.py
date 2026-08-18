from __future__ import annotations

from typing import Dict, List

from pydantic import BaseModel, Field

from ..core.types import AgentRole


class ModelProfile(BaseModel):
    name: str
    provider: str
    context_window: int
    cost_per_1k_input: float = Field(ge=0.0, default=0.0)
    cost_per_1k_output: float = Field(ge=0.0, default=0.0)


MODEL_PROFILES: Dict[str, ModelProfile] = {
    "nvidia/llama-3.1-70b-instruct": ModelProfile(
        name="meta/llama-3.1-70b-instruct",
        provider="nvidia_nim",
        context_window=131_072,
        cost_per_1k_input=0.0003,
        cost_per_1k_output=0.0008,
    ),
    "nvidia/mistral-nemo-12b-instruct": ModelProfile(
        name="mistralai/mistral-nemo-12b-instruct",
        provider="nvidia_nim",
        context_window=128_000,
        cost_per_1k_input=0.00015,
        cost_per_1k_output=0.00015,
    ),
    "nvidia/nemotron-super-49b": ModelProfile(
        name="nvidia/llama-3.3-nemotron-super-49b-v1.5",
        provider="nvidia_nim",
        context_window=131_072,
        cost_per_1k_input=0.0003,
        cost_per_1k_output=0.0008,
    ),
    "groq/llama-3.1-8b-instant": ModelProfile(
        name="llama-3.1-8b-instant",
        provider="groq",
        context_window=131_072,
        cost_per_1k_input=0.0,
        cost_per_1k_output=0.0,
    ),
    "groq/llama-3.3-70b-versatile": ModelProfile(
        name="llama-3.3-70b-versatile",
        provider="groq",
        context_window=131_072,
        cost_per_1k_input=0.00059,
        cost_per_1k_output=0.00079,
    ),
    "groq/gpt-oss-120b": ModelProfile(
        name="openai/gpt-oss-120b",
        provider="groq",
        context_window=131_072,
        cost_per_1k_input=0.00015,
        cost_per_1k_output=0.00060,
    ),
    "groq/gpt-oss-20b": ModelProfile(
        name="openai/gpt-oss-20b",
        provider="groq",
        context_window=131_072,
        cost_per_1k_input=0.000075,
        cost_per_1k_output=0.00030,
    ),
}


AGENT_MODEL_MAP: Dict[AgentRole, List[str]] = {
    AgentRole.ORCHESTRATOR: [
        "groq/llama-3.1-8b-instant",
        "nvidia/llama-3.1-70b-instruct",
        "groq/gpt-oss-20b",
        "nvidia/nemotron-super-49b",
    ],
    AgentRole.CONTENT_WEB2: [
        "groq/llama-3.1-8b-instant",
        "nvidia/mistral-nemo-12b-instruct",
        "groq/gpt-oss-20b",
        "nvidia/nemotron-super-49b",
    ],
    AgentRole.CONTENT_WEB3: [
        "groq/gpt-oss-120b",
        "nvidia/llama-3.1-70b-instruct",
        "groq/llama-3.1-8b-instant",
        "nvidia/nemotron-super-49b",
    ],
    AgentRole.FOOTBALL: [
        "groq/llama-3.1-8b-instant",
        "nvidia/mistral-nemo-12b-instruct",
        "groq/gpt-oss-20b",
        "nvidia/nemotron-super-49b",
    ],
    AgentRole.EDITOR: [
        "groq/llama-3.1-8b-instant",
        "nvidia/llama-3.1-70b-instruct",
        "groq/gpt-oss-120b",
        "nvidia/nemotron-super-49b",
    ],
    AgentRole.SECURITY: [
        "groq/gpt-oss-120b",
        "nvidia/llama-3.1-70b-instruct",
        "groq/llama-3.1-8b-instant",
        "nvidia/nemotron-super-49b",
    ],
    AgentRole.KNOWLEDGE: [
        "groq/llama-3.1-8b-instant",
        "nvidia/mistral-nemo-12b-instruct",
        "groq/gpt-oss-20b",
        "nvidia/nemotron-super-49b",
    ],
    AgentRole.STUDY: [
        "groq/llama-3.1-8b-instant",
        "nvidia/mistral-nemo-12b-instruct",
        "groq/gpt-oss-20b",
        "nvidia/llama-3.1-70b-instruct",
    ],
}
