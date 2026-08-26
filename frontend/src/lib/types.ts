/**
 * The backend's AgentRole vocabulary ("ORCHESTRATOR", "FOOTBALL", …) — see
 * core/types.py. Deliberately a string, not a union: this file used to declare
 * a lowercase long-form union ("football_analyst") that no backend value ever
 * matched, so every agent_role comparison silently failed.
 */
export type AgentRole = string;

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

/**
 * Presentation metadata ONLY — icon, blurb, tags. The roster itself (which
 * agents exist, whether they're healthy, which model/tools each has) comes
 * from GET /api/agents at runtime. A hardcoded list here once claimed
 * "8 / 8 ONLINE" on a dead backend.
 *
 * Keys are the backend's own AgentRole values (see core/types.py).
 */
export const AGENT_PRESENTATION: Record<
  string,
  { displayName: string; tags: string[]; emoji: string }
> = {
  ORCHESTRATOR: { displayName: "ORCHESTRATOR", tags: ["planning", "routing", "meta"], emoji: "🧭" },
  CONTENT_WEB2: { displayName: "CONTENT · WEB2", tags: ["writing", "blog", "saas"], emoji: "✍️" },
  CONTENT_WEB3: { displayName: "CONTENT · WEB3", tags: ["web3", "defi", "audit"], emoji: "⛓️" },
  SECURITY: { displayName: "SECURITY AUDITOR", tags: ["security", "solidity", "audit"], emoji: "🔬" },
  KNOWLEDGE: { displayName: "KNOWLEDGE CRYSTALLIZER", tags: ["extract", "rag", "summary"], emoji: "🧠" },
  EDITOR: { displayName: "EDITOR / REVIEWER", tags: ["review", "edit", "docs"], emoji: "🛠️" },
  STUDY: { displayName: "STUDY PARTNER", tags: ["learning", "plan", "study"], emoji: "👤" },
  FOOTBALL: { displayName: "FOOTBALL ANALYST", tags: ["sports", "tactics", "stats"], emoji: "⚽" },
  PERSONAL_ASSISTANT: {
    displayName: "PERSONAL ASSISTANT",
    tags: ["notify", "chase", "telegram"],
    emoji: "📣"
  }
};

export function agentPresentation(role: string) {
  return (
    AGENT_PRESENTATION[role] ?? {
      displayName: role.replace(/_/g, " "),
      tags: [],
      emoji: "◎"
    }
  );
}

export type CommitmentStatus = "open" | "done" | "dropped";

/** One thing the user owes. Mirrors the backend commitments row. */
export interface Commitment {
  id: string;
  short_id: string;
  title: string;
  detail?: string | null;
  source: string;
  task_id?: string | null;
  status: CommitmentStatus;
  due_at: string | null;
  nag_interval_sec: number;
  nag_count: number;
  escalation: number;
  last_nagged_at: string | null;
  snooze_until: string | null;
  artifact_kind?: string | null;
  artifact_url?: string | null;
  artifact_text?: string | null;
  completed_at: string | null;
  created_at: string | null;
  overdue_sec: number;
}

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
