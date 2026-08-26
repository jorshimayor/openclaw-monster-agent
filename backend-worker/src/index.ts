import { Container, getContainer } from "@cloudflare/containers";

/**
 * Cloudflare Containers Durable Object — wraps the FastAPI Python backend.
 *
 * The container is a full Docker image (python:3.12-slim + uvicorn) built
 * from containers/backend/Dockerfile; the Worker routes HTTP traffic here.
 *
 * ROUTING: a single named instance via getContainer() — deliberately NOT
 * round-robin. The FastAPI backend keeps task state in process memory
 * (_TASK_STORE), so random load-balancing across instances made tasks
 * intermittently 404 (verified in production: alternating 200/404 on the
 * same task id). One instance = consistent state. If tasks ever move to
 * Postgres, this can go back to getRandom().
 *
 * Instance sizing:
 *   - type: basic  → 1/4 vCPU + 1 GiB memory + 4 GiB disk
 *   - sleepAfter   → scale to zero after 15 minutes idle (task state is
 *     lost on sleep — known limitation until tasks persist to Postgres)
 */
export class BackendContainer extends Container<Env> {
  defaultPort = 8000;
  sleepAfter = "15m";
  enableInternet = true;

  constructor(ctx: ConstructorParameters<typeof Container<Env>>[0], env: Env) {
    super(ctx, env);
    // Supported v0.3.x pattern: set envVars in the constructor so the
    // container process inherits runtime secrets on every (re)start.
    this.envVars = buildEnvVars(env);
  }
}

type Env = {
  BACKEND_CONTAINER: DurableObjectNamespace<BackendContainer>;
  // All secrets below come from `npx wrangler secret put` for the backend worker
  DATABASE_URL: string;
  NVIDIA_NIM_API_KEY: string;
  GROQ_API_KEY: string;
  GITHUB_TOKEN: string;
  NOTION_TOKEN: string;
  NOTION_DB_ID: string;
  SLACK_BOT_TOKEN: string;
  SLACK_USER_TOKEN: string;
  // Personal Assistant Agent → Telegram shim (3 secrets, CRITICAL)
  TELEGRAM_BOT_TOKEN: string;
  TELEGRAM_CHAT_ID: string;
  TELEGRAM_ADMIN_IDS: string;
  GOOGLE_WORKSPACE_CLIENT_ID: string;
  GOOGLE_WORKSPACE_CLIENT_SECRET: string;
  GOOGLE_WORKSPACE_REFRESH_TOKEN: string;
  GOOGLE_WORKSPACE_SUBJECT_EMAIL: string;
  NVIDIA_NIM_BASE_URL?: string;
  SLACK_CHANNEL?: string;
  TELEGRAM_WEBHOOK_SECRET?: string;
  PUBLIC_APP_URL?: string;
  NAG_ENABLED?: string;
  USER_TIMEZONE_OFFSET_HOURS?: string;
  LLM_FALLBACK_ORDER?: string;
  LOG_LEVEL?: string;
  BACKEND_CORS_ORIGINS?: string;
};

function buildEnvVars(env: Env): Record<string, string> {
  return {
    DATABASE_URL: env.DATABASE_URL ?? "",
    NVIDIA_NIM_API_KEY: env.NVIDIA_NIM_API_KEY ?? "",
    GROQ_API_KEY: env.GROQ_API_KEY ?? "",
    GITHUB_TOKEN: env.GITHUB_TOKEN ?? "",
    NOTION_TOKEN: env.NOTION_TOKEN ?? "",
    NOTION_DB_ID: env.NOTION_DB_ID ?? "",
    SLACK_BOT_TOKEN: env.SLACK_BOT_TOKEN ?? "",
    SLACK_USER_TOKEN: env.SLACK_USER_TOKEN ?? "",
    TELEGRAM_BOT_TOKEN: env.TELEGRAM_BOT_TOKEN ?? "",
    TELEGRAM_CHAT_ID: env.TELEGRAM_CHAT_ID ?? "",
    TELEGRAM_ADMIN_IDS: env.TELEGRAM_ADMIN_IDS ?? "",
    GOOGLE_WORKSPACE_CLIENT_ID: env.GOOGLE_WORKSPACE_CLIENT_ID ?? "",
    GOOGLE_WORKSPACE_CLIENT_SECRET: env.GOOGLE_WORKSPACE_CLIENT_SECRET ?? "",
    GOOGLE_WORKSPACE_REFRESH_TOKEN: env.GOOGLE_WORKSPACE_REFRESH_TOKEN ?? "",
    GOOGLE_WORKSPACE_SUBJECT_EMAIL: env.GOOGLE_WORKSPACE_SUBJECT_EMAIL ?? "",
    NVIDIA_NIM_BASE_URL:
      env.NVIDIA_NIM_BASE_URL ?? "https://integrate.api.nvidia.com/v1",
    SLACK_CHANNEL: env.SLACK_CHANNEL ?? "#agent-updates",
    TELEGRAM_WEBHOOK_SECRET: env.TELEGRAM_WEBHOOK_SECRET ?? "",
    PUBLIC_APP_URL:
      env.PUBLIC_APP_URL ?? "https://monster-agent-frontend-2dn.pages.dev",
    NAG_ENABLED: env.NAG_ENABLED ?? "true",
    USER_TIMEZONE_OFFSET_HOURS: env.USER_TIMEZONE_OFFSET_HOURS ?? "1",
    LLM_FALLBACK_ORDER: env.LLM_FALLBACK_ORDER ?? '["nvidia_nim","groq"]',
    LOG_LEVEL: env.LOG_LEVEL ?? "INFO",
    BACKEND_CORS_ORIGINS:
      env.BACKEND_CORS_ORIGINS ??
      '["http://localhost:3000","http://localhost:8080"]',
    PYTHONUNBUFFERED: "1",
  };
}

const CORS_HEADERS: Record<string, string> = {
  "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,PATCH,OPTIONS",
  "Access-Control-Allow-Headers":
    "Authorization,Content-Type,Accept,Accept-Language,Range,X-Requested-With",
};

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // CORS preflight handled in the Worker so Pages-origin changes never
    // require a container rebuild.
    if (request.method === "OPTIONS") {
      const origin = request.headers.get("origin") ?? "*";
      return new Response(null, {
        status: 204,
        headers: {
          ...CORS_HEADERS,
          "Access-Control-Allow-Origin": origin,
          "Access-Control-Max-Age": "86400",
          Vary: "Origin",
        },
      });
    }

    // Single named instance — see class docblock for why.
    const stub = getContainer(env.BACKEND_CONTAINER, "backend-primary");
    const resp = await stub.fetch(request);

    const origin = request.headers.get("origin") ?? "*";
    const headers = new Headers(resp.headers);
    if (!headers.has("Access-Control-Allow-Origin")) {
      headers.set("Access-Control-Allow-Origin", origin);
      headers.set(
        "Access-Control-Allow-Methods",
        CORS_HEADERS["Access-Control-Allow-Methods"]
      );
      headers.set(
        "Access-Control-Allow-Headers",
        CORS_HEADERS["Access-Control-Allow-Headers"]
      );
      headers.set("Vary", "Origin");
    }
    return new Response(resp.body, { status: resp.status, headers });
  },

  /**
   * Scheduled tasks — the assistant works unprompted. Each cron submits a
   * task into the normal pipeline; results reach Telegram through the
   * personal-assistant bus (task-completed alerts). Crons are UTC.
   */
  async scheduled(event: ScheduledController, env: Env): Promise<void> {
    const stub = getContainer(env.BACKEND_CONTAINER, "backend-primary");
    // Submit, then poll until the task reaches a terminal state (or ~13 min).
    // The polling is not just observability: the container sleeps after 15
    // idle minutes and a background pipeline generates NO requests, so an
    // unwatched scheduled task can die mid-run — or complete but never get
    // its notification out. Each poll resets the idle clock.
    const submit = async (description: string): Promise<void> => {
      const created = await stub.fetch(
        new Request("http://container/api/tasks", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ description }),
        })
      );
      const task = (await created.json().catch(() => null)) as { id?: string } | null;
      if (!task?.id) return;
      for (let i = 0; i < 26; i++) {
        await new Promise((r) => setTimeout(r, 30_000));
        try {
          const res = await stub.fetch(new Request(`http://container/api/tasks/${task.id}`));
          const t = (await res.json().catch(() => null)) as { status?: string } | null;
          if (t?.status && ["COMPLETED", "FAILED", "CANCELLED"].includes(t.status)) {
            // one grace poll so the notification worker finishes sending
            await new Promise((r) => setTimeout(r, 15_000));
            await stub.fetch(new Request("http://container/api/health")).catch(() => {});
            return;
          }
        } catch {
          /* transient — keep polling */
        }
      }
    };

    // Every 10 minutes: run one reminder round and pick up replies. This is
    // what makes the assistant persistent — the container sleeps after 15
    // idle minutes and an in-process loop dies with it, so the reminder clock
    // has to live out here. `drain` is the no-webhook fallback for inbound
    // replies; with a webhook registered it just returns 0 updates.
    if (event.cron === "*/10 * * * *") {
      const hit = async (path: string): Promise<void> => {
        try {
          const r = await stub.fetch(
            new Request(`http://container${path}`, { method: "POST" })
          );
          if (!r.ok) console.error(`cron ${path} -> ${r.status}`);
        } catch (err) {
          console.error(`cron ${path} failed`, err);
        }
      };
      await hit("/api/commitments/tick");
      await hit("/api/telegram/drain");
      return;
    }

    switch (event.cron) {
      // Saturday 07:00 UTC = 08:00 WAT — weekly market RESEARCH digest
      // (educational research only — explicitly not investment advice)
      case "0 7 * * 6": {
        const facts: string[] = [];
        const grab = async (label: string, url: string, pick: (j: any) => string) => {
          try {
            const r = await fetch(url, { headers: { "User-Agent": "openclaw-digest/1.0" } });
            if (r.ok) facts.push(`${label}: ${pick(await r.json())}`);
          } catch {
            /* a missing source is fine — the prompt forbids inventing numbers */
          }
        };
        await grab("FX (per 1 USD)", "https://open.er-api.com/v6/latest/USD", (j) =>
          `NGN ${j.rates?.NGN} · EUR ${j.rates?.EUR} · GBP ${j.rates?.GBP} (as of ${j.time_last_update_utc})`
        );
        await grab(
          "Crypto (USD)",
          "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum&vs_currencies=usd&include_24hr_change=true",
          (j) =>
            `BTC $${j.bitcoin?.usd} (${j.bitcoin?.usd_24h_change?.toFixed(1)}% 24h) · ETH $${j.ethereum?.usd} (${j.ethereum?.usd_24h_change?.toFixed(1)}% 24h)`
        );
        await submit(
          "Weekly market research digest (scheduled — RESEARCH ONLY, NOT investment advice; I am not " +
            "seeking recommendations and none should be given). Write a scannable digest for a reader in " +
            "Lagos covering: 1) global markets — the week's major themes in US/European equities and rates, " +
            "2) Nigerian markets — naira/FX picture, NGX and Nigerian macro (inflation, MPC) described " +
            "QUALITATIVELY with pointers to ngxgroup.com and cbn.gov.ng for current figures, 3) crypto, " +
            "4) three things to watch next week. HARD RULES: never invent a price, rate, or figure — the " +
            "ONLY numbers you may quote are in the verified data below or figures you are certain of with " +
            "their date; anything else say 'check source'. End with: 'Research digest — not investment " +
            "advice.'\n\nVerified data fetched just now:\n" +
            (facts.length ? facts.map((f) => `- ${f}`).join("\n") : "- (live sources unavailable this run — write the digest fully qualitatively)")
        );
        break;
      }
      // Monday 06:00 UTC = 07:00 WAT — week planning brief
      case "0 6 * * 1":
        await submit(
          "Weekly planning (scheduled): produce a concrete day-by-day plan for this week. " +
            "I'm a software engineer in Lagos (WAT) building fieldtilt, a football data & publishing " +
            "platform, as portfolio evidence for football-industry jobs. Structure: the one mandatory " +
            "BUILD task, content to publish on X/LinkedIn, outreach, and evening/weekend time slots " +
            "around a day job. Check my Google Calendar for conflicts if available. End with the top " +
            "3 priorities for Monday."
        );
        break;
      // Daily 05:30 UTC = 06:30 WAT — morning brief
      case "30 5 * * *":
        await submit(
          "Morning brief (scheduled): summarize today in under 200 words — my Google Calendar events " +
            "for today if available, the single most important task to move forward, and one reminder " +
            "from my current week plan. Keep it scannable; it lands on Telegram."
        );
        break;
    }
  },
};
