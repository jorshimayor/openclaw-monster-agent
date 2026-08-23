import { createParser, type ParsedEvent, type ReconnectInterval } from "eventsource-parser";
import type { AgentRole, AgentResult, KnowledgeCrystal, Task } from "./types";

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

  async listTasks(): Promise<Task[]> {
    const res = await fetch(`${this.baseUrl}/api/tasks`, {
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

  async getAgent(role: AgentRole): Promise<AgentDetail> {
    const res = await fetch(`${this.baseUrl}/api/agents/${role}`, {
      headers: { Accept: "application/json" },
      cache: "no-store"
    });
    if (!res.ok) throw new Error(`getAgent failed: ${res.status}`);
    return res.json();
  }

  async invokeAgent(role: AgentRole, context: object): Promise<AgentResult> {
    const res = await fetch(`${this.baseUrl}/api/agents/${role}/invoke`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ context }),
      cache: "no-store"
    });
    if (!res.ok) throw new Error(`invokeAgent failed: ${res.status}`);
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
    currentStep: raw?.currentStep ?? raw?.step ?? undefined,
    createdAt: raw?.createdAt ?? outputs.created_at ?? "",
    finalReport: raw?.finalReport ?? outputs.final_report ?? undefined,
    error: raw?.error ?? outputs.error ?? undefined
  };
}

const base = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
export const api = new ApiClient(base);
