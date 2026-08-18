export type AgentRole =
  | "orchestrator"
  | "content_web2"
  | "content_web3"
  | "security_auditor"
  | "knowledge_crystallizer"
  | "editor_reviewer"
  | "study_partner"
  | "football_analyst";

export type TaskStatus = "queued" | "running" | "completed" | "failed" | "reworking";

export type PipelineStep =
  | "complexity"
  | "pattern"
  | "experience"
  | "team"
  | "prompt"
  | "execute"
  | "verify"
  | "quality_gate"
  | "fix"
  | "synthesize"
  | "reflect";

export interface ToolCall {
  name: string;
  success: boolean;
  result?: unknown;
  error?: string;
}

export interface AgentAction {
  id: string;
  type: "write" | "query" | "analyze" | "report" | "plan_step" | "other";
  description: string;
  metadata?: Record<string, unknown>;
}

export interface AgentResult {
  agent_role: AgentRole;
  status: "success" | "partial" | "failed";
  output: unknown;
  summary?: string;
  confidence: number;
  errors?: string[];
  actions?: AgentAction[];
  references?: string[];
  metadata?: {
    latency_ms?: number;
    tokens_in?: number;
    tokens_out?: number;
    tool_calls?: ToolCall[];
    model?: string;
  };
}

export interface Task {
  id: string;
  description: string;
  status: TaskStatus;
  currentStep?: PipelineStep;
  outputs?: AgentResult[];
  createdAt: string;
  updatedAt?: string;
  error?: string;
  finalReport?: string;
}

export interface Agent {
  role: AgentRole;
  displayName: string;
  description: string;
  tags: string[];
  status: string;
  modelProfile: string;
  toolsCount: number;
}

export const AGENTS: Agent[] = [
  {
    role: "orchestrator",
    displayName: "ORCHESTRATOR",
    description: "Builds the 11-step pipeline plan and routes tasks across specialist agents with step-by-step execution orchestration.",
    tags: ["planning", "routing", "meta"],
    status: "online",
    modelProfile: "strong_reasoning",
    toolsCount: 0
  },
  {
    role: "content_web2",
    displayName: "CONTENT · WEB2",
    description: "Writes technical blogs, docs, tutorials, SaaS content. Can optionally read GitHub repos to enrich references.",
    tags: ["writing", "blog", "github", "saas"],
    status: "online",
    modelProfile: "content_writer",
    toolsCount: 3
  },
  {
    role: "content_web3",
    displayName: "CONTENT · WEB3",
    description: "Draft audit summaries, protocol explainers, DeFi education, Web3 content with audit PR references.",
    tags: ["web3", "defi", "audit", "writing"],
    status: "online",
    modelProfile: "content_writer",
    toolsCount: 4
  },
  {
    role: "security_auditor",
    displayName: "SECURITY AUDITOR",
    description: "Static & dynamic smart contract audit. Pulls real repo code via GitHub for realistic review.",
    tags: ["security", "solidity", "audit", "web3"],
    status: "online",
    modelProfile: "auditor",
    toolsCount: 3
  },
  {
    role: "knowledge_crystallizer",
    displayName: "KNOWLEDGE CRYSTALLIZER",
    description: "Extracts strategies, pitfalls, frameworks, entities from text. Optionally persists to Notion.",
    tags: ["extract", "notion", "rag", "summary"],
    status: "online",
    modelProfile: "extractor",
    toolsCount: 2
  },
  {
    role: "editor_reviewer",
    displayName: "EDITOR / REVIEWER",
    description: "Reviews content, technical writing, code PRs. Logs writes to Google Workspace docs when available.",
    tags: ["review", "edit", "docs"],
    status: "online",
    modelProfile: "reviewer",
    toolsCount: 3
  },
  {
    role: "study_partner",
    displayName: "STUDY PARTNER",
    description: "Personalized study plans, curriculum, learning pathways. Optionally saves plans to Notion.",
    tags: ["learning", "plan", "notion", "study"],
    status: "online",
    modelProfile: "tutor",
    toolsCount: 2
  },
  {
    role: "football_analyst",
    displayName: "FOOTBALL ANALYST",
    description: "Tactical matchup analysis, stats, formations, in-game adjustments. Writes to Sheets when available.",
    tags: ["sports", "tactics", "stats", "analytics"],
    status: "online",
    modelProfile: "analyst",
    toolsCount: 2
  }
];

export interface KnowledgeCrystal {
  id: string;
  category: "entities" | "strategies" | "pitfalls" | "frameworks";
  title: string;
  content: string;
  sourceTaskId?: string;
  createdAt: string;
}

export interface McpServerStatus {
  name: string;
  status: "healthy" | "degraded" | "down";
  toolsAvailable: number;
  lastProbe?: string;
}
