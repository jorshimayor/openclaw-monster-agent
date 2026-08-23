from __future__ import annotations

from enum import Enum
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, ConfigDict


class AgentRole(str, Enum):
    PERSONAL_ASSISTANT = "PERSONAL_ASSISTANT"
    ORCHESTRATOR = "ORCHESTRATOR"
    CONTENT_WEB2 = "CONTENT_WEB2"
    CONTENT_WEB3 = "CONTENT_WEB3"
    FOOTBALL = "FOOTBALL"
    EDITOR = "EDITOR"
    SECURITY = "SECURITY"
    KNOWLEDGE = "KNOWLEDGE"
    STUDY = "STUDY"


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class PipelineStep(str, Enum):
    COMPLEXITY_CHECK = "COMPLEXITY_CHECK"
    PATTERN_MATCH = "PATTERN_MATCH"
    EXPERIENCE_RECALL = "EXPERIENCE_RECALL"
    TEAM_ASSEMBLY = "TEAM_ASSEMBLY"
    PROMPT_INJECTION = "PROMPT_INJECTION"
    PARALLEL_EXECUTION = "PARALLEL_EXECUTION"
    VERIFIER = "VERIFIER"
    QUALITY_GATE = "QUALITY_GATE"
    FIX_REVALIDATE = "FIX_REVALIDATE"
    SYNTHESIZER = "SYNTHESIZER"
    POST_TASK_REFLECTION = "POST_TASK_REFLECTION"


class Task(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    id: UUID = Field(default_factory=uuid4)
    description: str
    status: TaskStatus = TaskStatus.PENDING
    step: Optional[PipelineStep] = None
    outputs: Dict[str, Any] = Field(default_factory=dict)


class AgentResult(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    agent_role: AgentRole
    output: str
    confidence: float = Field(ge=0.0, le=1.0, default=0.85)
    errors: Optional[List[str]] = None


class KnowledgeCrystals(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    id: UUID = Field(default_factory=uuid4)
    entities: List[str] = Field(default_factory=list)
    strategies: List[str] = Field(default_factory=list)
    pitfalls: List[str] = Field(default_factory=list)
    frameworks: List[str] = Field(default_factory=list)
    source_task_id: UUID
    created_at: datetime = Field(default_factory=datetime.utcnow)


class AgentEventPriority(str, Enum):
    P0_CRITICAL = "P0_CRITICAL"
    P1_ACTION = "P1_ACTION"
    P2_UPDATE = "P2_UPDATE"
    P3_INFO = "P3_INFO"


class AgentEventKind(str, Enum):
    TASK_CREATED = "TASK_CREATED"
    TASK_STARTED = "TASK_STARTED"
    PIPELINE_STEP = "PIPELINE_STEP"
    AGENT_STEP_OUTPUT = "AGENT_STEP_OUTPUT"
    TASK_COMPLETED = "TASK_COMPLETED"
    TASK_FAILED = "TASK_FAILED"
    TASK_CANCELLED = "TASK_CANCELLED"
    INTEGRATION_DOWN = "INTEGRATION_DOWN"
    INTEGRATION_DEGRADED = "INTEGRATION_DEGRADED"
    KNOWLEDGE_CRYSTAL = "KNOWLEDGE_CRYSTAL"
    MANUAL_NOTIFY = "MANUAL_NOTIFY"


class AgentBusEvent(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    id: UUID = Field(default_factory=uuid4)
    kind: AgentEventKind
    priority: AgentEventPriority = AgentEventPriority.P2_UPDATE
    task_id: Optional[UUID] = None
    source_agent_role: Optional[AgentRole] = None
    integration: Optional[str] = None
    title: str
    summary: str
    details: Dict[str, Any] = Field(default_factory=dict)
    action_items: List[str] = Field(default_factory=list)
    external_links: Dict[str, str] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
