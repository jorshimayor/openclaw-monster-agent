import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

export function formatDate(date: Date | string | undefined | null): string {
  if (date === undefined || date === null || date === "") return "—";
  const d = typeof date === "string" ? new Date(date) : date;
  // Invalid/missing dates render as a dash instead of crashing the page
  // (production tasks from the API have no top-level createdAt).
  if (Number.isNaN(d.getTime())) return "—";
  return d.toISOString().replace("T", " ").slice(0, 19);
}

export function truncate(s: string, n: number = 80): string {
  if (s.length <= n) return s;
  return s.slice(0, n - 3) + "...";
}

/**
 * The backend emits pipeline steps as its own enum ("PARALLEL_EXECUTION");
 * the UI keys them lowercase and short ("execute"). Without this map the
 * rail highlighted nothing, because no backend value ever matched a key.
 */
const STEP_ALIASES: Record<string, string> = {
  COMPLEXITY_CHECK: "complexity",
  PATTERN_MATCH: "pattern",
  EXPERIENCE_RECALL: "experience",
  TEAM_ASSEMBLY: "team",
  PROMPT_INJECTION: "prompt",
  PARALLEL_EXECUTION: "execute",
  VERIFIER: "verify",
  QUALITY_GATE: "quality_gate",
  FIX_REVALIDATE: "fix",
  SYNTHESIZER: "synthesize",
  POST_TASK_REFLECTION: "reflect"
};

export function normalizePipelineStep(step: unknown): string | undefined {
  if (typeof step !== "string" || !step) return undefined;
  return STEP_ALIASES[step.toUpperCase()] ?? step.toLowerCase();
}
