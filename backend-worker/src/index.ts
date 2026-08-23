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
};
