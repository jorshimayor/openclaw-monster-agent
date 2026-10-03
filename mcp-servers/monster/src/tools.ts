/**
 * What another agent can do to the Monster bot.
 *
 * Deliberately not a mirror of all 29 endpoints. An MCP server is a contract,
 * and every tool here is one another agent has a real reason to call. The
 * destructive ones — delete, purge, drop — are left off on purpose: a sibling
 * bot has no business erasing an accountability record, and anything that
 * needs them can be added once there is a reason.
 */

import { z } from "zod";

import type { MonsterClient } from "./client.js";

export type Tool = {
  name: string;
  description: string;
  schema: z.ZodTypeAny;
  handler: (client: MonsterClient, args: any) => Promise<unknown>;
};

export const TOOLS: Tool[] = [
  {
    name: "get_today",
    description:
      "What today looks like: the day's themes, time blocks, and everything due. " +
      "Start here when you need to know what the human is supposed to be doing.",
    schema: z.object({
      date: z.string().optional().describe("YYYY-MM-DD; defaults to today"),
    }),
    handler: (client, { date }) =>
      client.request("GET", `/api/day${date ? `?date=${encodeURIComponent(date)}` : ""}`),
  },
  {
    name: "list_commitments",
    description:
      "Commitments on the ledger. A commitment is something the human has been " +
      "held to; it cannot be closed without an artifact.",
    schema: z.object({
      status: z
        .enum(["proposed", "open", "done", "dropped"])
        .optional()
        .describe("omit for all"),
      limit: z.number().int().min(1).max(500).optional(),
    }),
    handler: (client, { status, limit }) => {
      const params = new URLSearchParams();
      if (status) params.set("status", status);
      if (limit) params.set("limit", String(limit));
      const query = params.toString();
      return client.request("GET", `/api/commitments${query ? `?${query}` : ""}`);
    },
  },
  {
    name: "create_commitment",
    description:
      "File something the human must do. It will be chased until closed with an " +
      "artifact, so do not file vague or speculative work — it becomes a reminder " +
      "that cannot be satisfied.",
    schema: z.object({
      title: z.string().min(8).describe("what has to be done, concretely"),
      detail: z.string().optional(),
      due_in_minutes: z.number().int().min(0).optional(),
      day: z.string().optional().describe('"today", "tomorrow", or a weekday'),
      time_of_day: z.string().optional().describe('"morning", "evening", or a clock time'),
    }),
    handler: (client, args) => client.request("POST", "/api/commitments", args),
  },
  {
    name: "close_commitment",
    description:
      "Close a commitment with proof. Requires an artifact: a URL, or at least " +
      "40 characters of real substance. An acknowledgement like 'done' is " +
      "rejected with a 422 — that is the whole mechanism, not a validation quirk.",
    schema: z.object({
      ref: z.string().describe("the full uuid or the 8-character short id"),
      artifact_url: z.string().url().optional(),
      artifact_text: z.string().optional().describe("what was produced, not that it was"),
    }),
    handler: (client, { ref, ...body }) =>
      client.request("POST", `/api/commitments/${encodeURIComponent(ref)}/done`, body),
  },
  {
    name: "get_fellowship_status",
    description:
      "Where the human is in the 48-week Flow Research fellowship: the week, the " +
      "anchor paper, the lab, and what is due this week.",
    schema: z.object({}),
    handler: async (client) => {
      const day = (await client.request<any>("GET", "/api/day")) ?? {};
      return day.fellowship ?? { enabled: false };
    },
  },
  {
    name: "list_tasks",
    description: "Research tasks the agent team has run or is running.",
    schema: z.object({ limit: z.number().int().min(1).max(100).optional() }),
    handler: (client, { limit }) =>
      client.request("GET", `/api/tasks${limit ? `?limit=${limit}` : ""}`),
  },
  {
    name: "create_task",
    description:
      "Hand the agent team a piece of research. This runs a multi-agent pipeline " +
      "and costs model credits, so send a real question rather than a ping.",
    schema: z.object({
      description: z.string().min(12).describe("the research question"),
      priority: z.enum(["low", "normal", "high"]).optional(),
    }),
    handler: (client, args) => client.request("POST", "/api/tasks", args),
  },
  {
    name: "suggest_study",
    description:
      "Recommend something the human should learn next. This is the tool to " +
      "reach for when you notice a gap — a concept their code keeps working " +
      "around, a bug class they missed, an interview topic they have not " +
      "covered.\n\n" +
      "It does NOT create a reminder. Suggestions queue until the human " +
      "promotes them, so you cannot fill their day with work they never " +
      "agreed to. That means you can suggest freely; it also means a " +
      "suggestion with a weak rationale will simply be ignored.\n\n" +
      "The rationale is required and is the whole value. 'Learn Rust' is " +
      "noise. 'Your CCTP adapter retries on a non-idempotent path — read the " +
      "idempotency-key section before the next corridor' is a recommendation.",
    schema: z.object({
      topic: z.string().min(6).max(300).describe("what to learn, specifically"),
      rationale: z
        .string()
        .min(20)
        .describe("why this, why now — reference what you actually observed"),
      url: z.string().url().optional().describe("where to learn it"),
      track: z
        .enum(["build", "audit", "interview", "write", "fundamentals"])
        .default("fundamentals")
        .describe("which part of their work this serves"),
      priority: z.number().int().min(1).max(5).default(3).describe("1 highest"),
      est_minutes: z.number().int().min(5).max(600).optional(),
      suggested_by: z.string().max(80).describe("your name, so a bad source can be ignored"),
    }),
    handler: (client, args) => client.request("POST", "/api/study/queue", args),
  },
  {
    name: "list_study_queue",
    description:
      "What has already been suggested. Check before suggesting, so the queue " +
      "does not fill with the same idea from four agents.",
    schema: z.object({
      status: z.enum(["queued", "promoted", "dismissed", "all"]).default("queued"),
      limit: z.number().int().min(1).max(300).optional(),
    }),
    handler: (client, { status, limit }) => {
      const params = new URLSearchParams({ status });
      if (limit) params.set("limit", String(limit));
      return client.request("GET", `/api/study/queue?${params}`);
    },
  },
  {
    name: "notify",
    description:
      "Send the human a message through their Telegram and Slack channels. This " +
      "reaches a real person's phone — use it for things that warrant an " +
      "interruption, not status chatter.",
    schema: z.object({
      title: z.string().max(120),
      message: z.string().min(1).max(3000),
    }),
    handler: (client, args) => client.request("POST", "/api/notify/send", args),
  },
];

export const TOOLS_BY_NAME = new Map(TOOLS.map((t) => [t.name, t]));
