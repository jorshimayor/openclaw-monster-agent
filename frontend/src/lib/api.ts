import { createParser, type ParsedEvent, type ReconnectInterval } from "eventsource-parser";
import { normalizePipelineStep } from "./utils";
import type {
  AgentRole,
  AgentResult,
  Commitment,
  KnowledgeCrystal,
  McpServerStatus,
  Task
} from "./types";

export interface AgentDetail {
  role: AgentRole;
  displayName?: string;
  description?: string;
  status?: string;
  model_profile?: string;
  tool_allowlist?: string[];
  soul_file?: string;
  healthy: boolean;
  last_run?: string | null;
}

export interface AgentSummary {
  role: string;
  status: string;
  description: string;
  model_profile: string;
  tool_allowlist: string[];
  soul_file: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  meta?: Record<string, any>;
  created_at: string | null;
}

export interface ChatAction {
  type: string;
  id?: string;
  title?: string;
  due?: string;
  candidates?: string[];
}

export interface DayBlock {
  start: string;
  label: string;
  duration: string;
  raw_time: string;
  done: boolean;
}

export interface DayThemes {
  daily: string[];
  cycled: string | null;
  upcoming: { date: string; theme: string }[];
}

export interface DayItem extends Commitment {
  local_time: string;
}

export interface DayView {
  date: string;
  weekday: string;
  now_local: string;
  blocks: DayBlock[];
  block_error: string | null;
  items: DayItem[];
  themes: DayThemes;
}

export interface ResourceItem {
  title: string;
  url: string;
  note: string;
  meta?: { language?: string | null; stars?: number | null; updated?: string | null };
}

export interface ResourceGroup {
  key: string;
  name: string;
  source: "sheet" | "github" | "curated";
  items: ResourceItem[];
  error: string | null;
}

export interface StudyResources {
  groups: ResourceGroup[];
  total: number;
  failed: string[];
  cached: boolean;
}

export interface CommitmentStats {
  open: number;
  overdue: number;
  done: number;
  dropped: number;
  total: number;
}

export interface CommitmentsHealth {
  db_backed: boolean;
  memory_fallback_allowed: boolean;
  nag: {
    started: boolean;
    worker_alive: boolean;
    last_tick: string | null;
    last_tick_sent: number;
    quiet_hours?: {
      enabled: boolean;
      window: string;
      active_now: boolean;
      resumes_at: string | null;
    };
  };
  stats: CommitmentStats;
}

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
    this.name = "ApiError";
  }
}

/** FastAPI puts the human-readable reason in `detail` — surface it instead of
 *  a bare status code, because the artifact rejection copy lives there. */
async function failure(res: Response, label: string): Promise<ApiError> {
  let detail = "";
  try {
    const body = await res.json();
    detail = typeof body?.detail === "string" ? body.detail : JSON.stringify(body?.detail ?? "");
  } catch {
    /* non-JSON error body */
  }
  return new ApiError(detail || `${label} failed: ${res.status}`, res.status);
}

export interface KnowledgeQueryHit {
  crystal: KnowledgeCrystal;
  score: number;
}

export class ApiClient {
  constructor(private baseUrl: string) {}

  async health() {
    const res = await fetch(`${this.baseUrl}/api/health`, {
      headers: { Accept: "application/json" },
      cache: "no-store"
    });
    if (!res.ok) throw new Error(`Health check failed: ${res.status}`);
    return res.json();
  }

  async llmTest(prompt: string) {
    const res = await fetch(`${this.baseUrl}/api/llm/test`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ prompt }),
      cache: "no-store"
    });
    if (!res.ok) throw new Error(`LLM test failed: ${res.status}`);
    return res.json();
  }

  async listTasks(skip = 0, limit = 50): Promise<Task[]> {
    const qs = `?skip=${skip}&limit=${limit}`;
    const res = await fetch(`${this.baseUrl}/api/tasks${qs}`, {
      headers: { Accept: "application/json" },
      cache: "no-store"
    });
    if (!res.ok) throw new Error(`listTasks failed: ${res.status}`);
    const data = await res.json();
    return Array.isArray(data) ? data.map(normalizeTask) : [];
  }

  async getTask(id: string): Promise<Task> {
    const res = await fetch(`${this.baseUrl}/api/tasks/${id}`, {
      headers: { Accept: "application/json" },
      cache: "no-store"
    });
    if (!res.ok) throw new Error(`getTask failed: ${res.status}`);
    return normalizeTask(await res.json());
  }

  async submitTask(description: string): Promise<Task> {
    const res = await fetch(`${this.baseUrl}/api/tasks`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ description }),
      cache: "no-store"
    });
    if (!res.ok) throw new Error(`submitTask failed: ${res.status}`);
    return normalizeTask(await res.json());
  }

  async countTasks(): Promise<number> {
    const res = await fetch(`${this.baseUrl}/api/tasks/count`, {
      headers: { Accept: "application/json" },
      cache: "no-store"
    });
    if (!res.ok) throw await failure(res, "countTasks");
    return Number((await res.json())?.total ?? 0);
  }

  async deleteTask(id: string): Promise<{ deleted: boolean; commitments_removed: number }> {
    const res = await fetch(`${this.baseUrl}/api/tasks/${id}`, {
      method: "DELETE",
      headers: { Accept: "application/json" },
      cache: "no-store"
    });
    if (!res.ok) throw await failure(res, "deleteTask");
    return res.json();
  }

  async listKnowledge(category?: string, limit = 50): Promise<KnowledgeCrystal[]> {
    const params = new URLSearchParams();
    if (category) params.set("category", category);
    params.set("limit", String(limit));
    const res = await fetch(`${this.baseUrl}/api/knowledge?${params.toString()}`, {
      headers: { Accept: "application/json" },
      cache: "no-store"
    });
    if (!res.ok) throw new Error(`listKnowledge failed: ${res.status}`);
    const raw = await res.json();
    return (raw || []).map((r: any) => this._mapKnowledgeCrystal(r));
  }

  async getKnowledge(id: string): Promise<KnowledgeCrystal> {
    const res = await fetch(`${this.baseUrl}/api/knowledge/${id}`, {
      headers: { Accept: "application/json" },
      cache: "no-store"
    });
    if (!res.ok) throw new Error(`getKnowledge failed: ${res.status}`);
    const raw = await res.json();
    return this._mapKnowledgeCrystal(raw);
  }

  async deleteKnowledge(id: string): Promise<{ success: boolean; id: string }> {
    const res = await fetch(`${this.baseUrl}/api/knowledge/${id}`, {
      method: "DELETE",
      headers: { Accept: "application/json" },
      cache: "no-store"
    });
    if (!res.ok) throw new Error(`deleteKnowledge failed: ${res.status}`);
    return res.json();
  }

  async queryKnowledge(query: string, top_k = 10): Promise<KnowledgeQueryHit[]> {
    const res = await fetch(`${this.baseUrl}/api/knowledge/query`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ query, top_k }),
      cache: "no-store"
    });
    if (!res.ok) throw new Error(`queryKnowledge failed: ${res.status}`);
    const data = await res.json();
    const results = data?.results || [];
    return results.map((r: any) => ({
      crystal: this._mapKnowledgeCrystal(r.crystal),
      score: Number(r.score || 0)
    }));
  }

  async syncKnowledge(): Promise<{ queued: number }> {
    const res = await fetch(`${this.baseUrl}/api/knowledge/sync`, {
      method: "POST",
      headers: { Accept: "application/json" },
      cache: "no-store"
    });
    if (!res.ok) throw new Error(`syncKnowledge failed: ${res.status}`);
    return res.json();
  }

  /** `role` is the backend AgentRole value, e.g. "FOOTBALL". */
  async getAgent(role: string): Promise<AgentDetail> {
    const res = await fetch(`${this.baseUrl}/api/agents/${role}`, {
      headers: { Accept: "application/json" },
      cache: "no-store"
    });
    if (!res.ok) throw new Error(`getAgent failed: ${res.status}`);
    return res.json();
  }

  async invokeAgent(role: string, context: object): Promise<AgentResult> {
    const res = await fetch(`${this.baseUrl}/api/agents/${role}/invoke`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ context }),
      cache: "no-store"
    });
    if (!res.ok) throw new Error(`invokeAgent failed: ${res.status}`);
    return res.json();
  }

  async healthDiag(): Promise<Record<string, any>> {
    const res = await fetch(`${this.baseUrl}/api/health/diag`, {
      headers: { Accept: "application/json" },
      cache: "no-store"
    });
    if (!res.ok) throw await failure(res, "healthDiag");
    return res.json();
  }

  async listAgents(): Promise<AgentSummary[]> {
    const res = await fetch(`${this.baseUrl}/api/agents`, {
      headers: { Accept: "application/json" },
      cache: "no-store"
    });
    if (!res.ok) throw await failure(res, "listAgents");
    const data = await res.json();
    return Array.isArray(data) ? data : [];
  }

  async mcpDoctor(): Promise<McpServerStatus[]> {
    const res = await fetch(`${this.baseUrl}/api/mcp/doctor`, {
      headers: { Accept: "application/json" },
      cache: "no-store"
    });
    if (!res.ok) throw await failure(res, "mcpDoctor");
    const raw = await res.json();
    return (Array.isArray(raw) ? raw : []).map((r: any) => ({
      name: String(r.name ?? ""),
      status: (r.status ?? "down") as McpServerStatus["status"],
      toolsAvailable: Number(r.toolsAvailable ?? r.tools_available ?? 0),
      lastProbe: r.lastProbe ?? r.last_probe ?? undefined
    }));
  }

  async mcpProbe(server: string): Promise<Record<string, any>> {
    const res = await fetch(
      `${this.baseUrl}/api/mcp/doctor/${encodeURIComponent(server)}/probe`,
      { headers: { Accept: "application/json" }, cache: "no-store" }
    );
    if (!res.ok) throw await failure(res, "mcpProbe");
    return res.json();
  }

  // ── commitments (the accountability ledger) ──────────────────────────────

  async listCommitments(status?: string): Promise<Commitment[]> {
    const qs = status ? `?status=${encodeURIComponent(status)}` : "";
    const res = await fetch(`${this.baseUrl}/api/commitments${qs}`, {
      headers: { Accept: "application/json" },
      cache: "no-store"
    });
    if (!res.ok) throw await failure(res, "listCommitments");
    const data = await res.json();
    return Array.isArray(data) ? data : [];
  }

  async commitmentsHealth(): Promise<CommitmentsHealth> {
    const res = await fetch(`${this.baseUrl}/api/commitments/health`, {
      headers: { Accept: "application/json" },
      cache: "no-store"
    });
    if (!res.ok) throw await failure(res, "commitmentsHealth");
    return res.json();
  }

  async createCommitment(body: {
    title: string;
    detail?: string;
    due_at?: string;
    due_in_minutes?: number;
    day?: string;
    time_of_day?: string;
  }): Promise<Commitment> {
    const res = await fetch(`${this.baseUrl}/api/commitments`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(body),
      cache: "no-store"
    });
    if (!res.ok) throw await failure(res, "createCommitment");
    return res.json();
  }

  /** Throws ApiError(422) with the rejection reason when the artifact is
   *  too thin — the caller shows that text verbatim. */
  async completeCommitment(
    id: string,
    artifact: { artifact_url?: string; artifact_text?: string }
  ): Promise<Commitment> {
    const res = await fetch(`${this.baseUrl}/api/commitments/${id}/done`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(artifact),
      cache: "no-store"
    });
    if (!res.ok) throw await failure(res, "completeCommitment");
    return res.json();
  }

  async snoozeCommitment(id: string, minutes: number): Promise<Commitment> {
    const res = await fetch(`${this.baseUrl}/api/commitments/${id}/snooze`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ minutes }),
      cache: "no-store"
    });
    if (!res.ok) throw await failure(res, "snoozeCommitment");
    return res.json();
  }

  async dropCommitment(id: string): Promise<Commitment> {
    const res = await fetch(`${this.baseUrl}/api/commitments/${id}/drop`, {
      method: "POST",
      headers: { Accept: "application/json" },
      cache: "no-store"
    });
    if (!res.ok) throw await failure(res, "dropCommitment");
    return res.json();
  }

  async getChat(taskId: string): Promise<{
    messages: ChatMessage[];
    commitments: Commitment[];
  }> {
    const res = await fetch(`${this.baseUrl}/api/tasks/${taskId}/chat`, {
      headers: { Accept: "application/json" },
      cache: "no-store"
    });
    if (!res.ok) throw await failure(res, "getChat");
    return res.json();
  }

  async sendChat(
    taskId: string,
    message: string
  ): Promise<{ reply: string; actions: ChatAction[]; commitments: Commitment[] }> {
    const res = await fetch(`${this.baseUrl}/api/tasks/${taskId}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ message }),
      cache: "no-store"
    });
    if (!res.ok) throw await failure(res, "sendChat");
    return res.json();
  }

  async approveCommitment(id: string): Promise<Commitment> {
    const res = await fetch(`${this.baseUrl}/api/commitments/${id}/approve`, {
      method: "POST",
      headers: { Accept: "application/json" },
      cache: "no-store"
    });
    if (!res.ok) throw await failure(res, "approveCommitment");
    return res.json();
  }

  async deleteCommitment(id: string): Promise<{ deleted: boolean }> {
    const res = await fetch(`${this.baseUrl}/api/commitments/${id}`, {
      method: "DELETE",
      headers: { Accept: "application/json" },
      cache: "no-store"
    });
    if (!res.ok) throw await failure(res, "deleteCommitment");
    return res.json();
  }

  async purgeCommitments(filter: { task_id?: string; status?: string }): Promise<{ deleted: number }> {
    const res = await fetch(`${this.baseUrl}/api/commitments/purge`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(filter),
      cache: "no-store"
    });
    if (!res.ok) throw await failure(res, "purgeCommitments");
    return res.json();
  }

  async syncSchedule(): Promise<Record<string, any>> {
    const res = await fetch(`${this.baseUrl}/api/schedule/sync`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ write_back: true }),
      cache: "no-store"
    });
    if (!res.ok) throw await failure(res, "syncSchedule");
    return res.json();
  }

  async getDay(date?: string): Promise<DayView> {
    const qs = date ? `?date=${encodeURIComponent(date)}` : "";
    const res = await fetch(`${this.baseUrl}/api/day${qs}`, {
      headers: { Accept: "application/json" },
      cache: "no-store"
    });
    if (!res.ok) throw await failure(res, "getDay");
    return res.json();
  }

  async addDayItem(body: {
    title: string;
    at_time?: string;
    date?: string;
    category?: string;
  }): Promise<DayItem> {
    const res = await fetch(`${this.baseUrl}/api/day/items`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(body),
      cache: "no-store"
    });
    if (!res.ok) throw await failure(res, "addDayItem");
    return res.json();
  }

  async setBlockDone(
    slot: string,
    label: string,
    done: boolean,
    date?: string
  ): Promise<{ done: boolean }> {
    const res = await fetch(`${this.baseUrl}/api/day/blocks/done`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ slot, label, done, date }),
      cache: "no-store"
    });
    if (!res.ok) throw await failure(res, "setBlockDone");
    return res.json();
  }

  async moveDayItem(ref: string, at_time: string, date?: string): Promise<DayItem> {
    const res = await fetch(`${this.baseUrl}/api/day/items/${ref}/move`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ at_time, date }),
      cache: "no-store"
    });
    if (!res.ok) throw await failure(res, "moveDayItem");
    return res.json();
  }

  async studyResources(refresh = false): Promise<StudyResources> {
    const res = await fetch(
      `${this.baseUrl}/api/study/resources${refresh ? "?refresh=true" : ""}`,
      { headers: { Accept: "application/json" }, cache: "no-store" }
    );
    if (!res.ok) throw await failure(res, "studyResources");
    return res.json();
  }

  async scheduleState(): Promise<{ sheet_configured: boolean; range: string }> {
    const res = await fetch(`${this.baseUrl}/api/schedule/state`, {
      headers: { Accept: "application/json" },
      cache: "no-store"
    });
    if (!res.ok) throw await failure(res, "scheduleState");
    return res.json();
  }

  async nagCommitment(id: string): Promise<Record<string, any>> {
    const res = await fetch(`${this.baseUrl}/api/commitments/${id}/nag`, {
      method: "POST",
      headers: { Accept: "application/json" },
      cache: "no-store"
    });
    if (!res.ok) throw await failure(res, "nagCommitment");
    return res.json();
  }

  async extractCommitments(taskId: string): Promise<{ filed: number; commitments: Commitment[] }> {
    const res = await fetch(`${this.baseUrl}/api/commitments/extract`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ task_id: taskId }),
      cache: "no-store"
    });
    if (!res.ok) throw await failure(res, "extractCommitments");
    return res.json();
  }

  streamTask(id: string, onEvent: (event: ParsedEvent | ReconnectInterval) => void): () => void {
    const controller = new AbortController();

    (async () => {
      try {
        const res = await fetch(`${this.baseUrl}/api/tasks/${id}/stream`, {
          headers: { Accept: "text/event-stream" },
          signal: controller.signal,
          cache: "no-store"
        });

        if (!res.ok || !res.body) {
          throw new Error(`streamTask failed: ${res.status}`);
        }

        const parser = createParser(onEvent);
        const reader = res.body.getReader();
        const decoder = new TextDecoder();

        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          parser.feed(decoder.decode(value, { stream: true }));
        }
      } catch (err) {
        if ((err as Error).name !== "AbortError") {
          console.error("[streamTask]", err);
        }
      }
    })();

    return () => controller.abort();
  }

  private _mapKnowledgeCrystal(r: any): KnowledgeCrystal {
    const allContent: string[] = [];
    const categories = ["entities", "strategies", "pitfalls", "frameworks"] as const;
    let pickedCategory: KnowledgeCrystal["category"] = "entities";
    let maxLen = 0;
    for (const cat of categories) {
      const items: string[] = Array.isArray(r[cat]) ? r[cat] : [];
      allContent.push(...items);
      if (items.length > maxLen) {
        maxLen = items.length;
        pickedCategory = cat;
      }
    }
    const firstEntity = (r.entities?.[0] as string) || "Knowledge Crystal";
    const title = (firstEntity.length > 80 ? firstEntity.slice(0, 80) + "…" : firstEntity) || "Knowledge Crystal";
    const content = allContent.length > 0
      ? allContent.map((s, i) => `${i + 1}. ${s}`).join("\n")
      : "(no extracted content)";
    return {
      id: String(r.id),
      category: pickedCategory,
      title,
      content,
      sourceTaskId: r.source_task_id ? String(r.source_task_id) : undefined,
      createdAt: r.created_at ? String(r.created_at) : new Date().toISOString()
    };
  }
}

/**
 * Backend tasks are {id, description, status, step, outputs:{…}} — the UI's
 * Task shape (createdAt, currentStep, finalReport) is derived here so pages
 * never touch raw API JSON (a missing createdAt crashed the tasks page the
 * moment production data first loaded).
 */
function normalizeTask(raw: any): Task {
  const outputs =
    raw && typeof raw.outputs === "object" && !Array.isArray(raw.outputs)
      ? raw.outputs
      : {};
  return {
    ...raw,
    id: String(raw?.id ?? ""),
    description: String(raw?.description ?? ""),
    status: raw?.status ?? "QUEUED",
    currentStep: normalizePipelineStep(raw?.currentStep ?? raw?.step) as Task["currentStep"],
    createdAt: raw?.createdAt ?? outputs.created_at ?? "",
    finalReport: raw?.finalReport ?? outputs.final_report ?? undefined,
    error: raw?.error ?? outputs.error ?? undefined
  };
}

const base = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
export const api = new ApiClient(base);
