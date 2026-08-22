import { Container, getRandom } from "@cloudflare/containers";

/**
 * Cloudflare Containers Durable Object — wraps the FastAPI Python backend.
 *
 * The actual container is a full Docker image (python:3.12-slim + uvicorn)
 * built from containers/backend/Dockerfile. Cloudflare's wrangler containers
 * image registry holds the built image; the worker routes HTTP traffic here.
 *
 * Instance sizing:
 *   - type: basic   → 1/4 vCPU + 1 GiB memory + 4 GiB disk.
 *   - sleepAfter:   → scale to zero after 15 minutes idle
 *   - NUM_INSTANCES → round-robin across N containers via getRandom()
 */
export class BackendContainer extends Container {
  defaultPort = 8000;
  sleepAfter = "15m";
  enableInternet = true;
}

const NUM_INSTANCES = 2;

type Env = {
  BACKEND_CONTAINER: DurableObjectNamespace;
  // All secrets below come from `npx wrangler secret put` for the backend worker
  DATABASE_URL: string;
  NVIDIA_NIM_API_KEY: string;
  GROQ_API_KEY: string;
  GITHUB_TOKEN: string;
  NOTION_TOKEN: string;
  NOTION_DB_ID: string;
  SLACK_BOT_TOKEN: string;
  SLACK_USER_TOKEN: string;
  HASHNODE_TOKEN: string;
  HASHNODE_PUBLICATION_ID: string;
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

/**
 * Attach all secrets as container env vars on startup. Cloudflare Containers
 * invokes the start() with runtime env vars; the Python uvicorn process
 * inherits these directly via container's Linux process environment.
 */
function buildEnvVars(env: Env): Record<string, string> {
  return {
    DATABASE_URL: env.DATABASE_URL,
    NVIDIA_NIM_API_KEY: env.NVIDIA_NIM_API_KEY ?? "",
    GROQ_API_KEY: env.GROQ_API_KEY ?? "",
    GITHUB_TOKEN: env.GITHUB_TOKEN ?? "",
    NOTION_TOKEN: env.NOTION_TOKEN ?? "",
    NOTION_DB_ID: env.NOTION_DB_ID ?? "",
    SLACK_BOT_TOKEN: env.SLACK_BOT_TOKEN ?? "",
    SLACK_USER_TOKEN: env.SLACK_USER_TOKEN ?? "",
    HASHNODE_TOKEN: env.HASHNODE_TOKEN ?? "",
    HASHNODE_PUBLICATION_ID: env.HASHNODE_PUBLICATION_ID ?? "",
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
      '["http://localhost:3000","http://localhost:8080","*"]',
    PYTHONUNBUFFERED: "1",
  };
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // Lightweight global CORS preflight handled in Worker (so users don't need
    // a container rebuild when Pages origins change). Actual FastAPI response
    // also carries CORS headers if we've set BACKEND_CORS_ORIGINS above.
    if (request.method === "OPTIONS") {
      const origin = request.headers.get("origin") ?? "";
      return new Response(null, {
        status: 204,
        headers: {
          "Access-Control-Allow-Origin": origin || "*",
          "Access-Control-Allow-Methods":
            "GET,POST,PUT,DELETE,PATCH,OPTIONS",
          "Access-Control-Allow-Headers":
            "Authorization,Content-Type,Accept,Accept-Language,Range,X-Requested-With",
          "Access-Control-Max-Age": "86400",
          Vary: "Origin",
        },
      });
    }

    // Pick a container instance — round-robin via getRandom helper and
    // ensure env vars + internet are wired in on first start.
    const containerNamespace = env.BACKEND_CONTAINER;
    const containerStub = await getRandom(
      containerNamespace as unknown as ReturnType<typeof getRandom> extends never
        ? never
        : any,
      NUM_INSTANCES
    );

    // Cloudflare Containers package's getRandom returns a Durable Object stub
    // of Container class; we cast through unknown to fetch. On first use the
    // container's defaultStartAndWaitForPorts fires, runs Docker image and
    // attaches env vars we configured in the Container class. Env vars are
    // injected by overriding envVars in the constructor via Container class:
    const containerStubTyped = containerStub as {
      fetch: (r: Request) => Promise<Response>;
    };
    void buildEnvVars(env);

    // We need runtime env vars attached to container. In v0.3.x of
    // @cloudflare/containers this is done via `Container.envVars` in the DO
    // class (static/class-level config). But we want per-deployment secrets,
    // so we use `startAndWaitForPorts` with env vars if this is the first
    // request hitting a container ID. We do this via a helper:
    const started: boolean =
      (
        containerStub as unknown as {
          startAndWaitForPorts?: (a: {
            startOptions?: { envVars?: Record<string, string> };
          }) => Promise<void>;
        }
      ).startAndWaitForPorts !== undefined;
    if (started) {
      try {
        await (
          containerStub as unknown as {
            startAndWaitForPorts: (a: {
              startOptions: { envVars: Record<string, string> };
            }) => Promise<void>;
          }
        ).startAndWaitForPorts({
          startOptions: { envVars: buildEnvVars(env) },
        });
      } catch {
        // startAndWaitForPorts is best-effort: already-running containers
        // throw on repeated calls; ignore and continue fetch.
      }
    }

    const resp = await containerStubTyped.fetch(request);

    const origin = request.headers.get("origin") ?? "*";
    const headers = new Headers(resp.headers);
    if (!headers.has("Access-Control-Allow-Origin")) {
      headers.set("Access-Control-Allow-Origin", origin);
      headers.set(
        "Access-Control-Allow-Methods",
        "GET,POST,PUT,DELETE,PATCH,OPTIONS"
      );
      headers.set(
        "Access-Control-Allow-Headers",
        "Authorization,Content-Type,Accept,Accept-Language,Range,X-Requested-With"
      );
      headers.set("Vary", "Origin");
    }
    return new Response(resp.body, { status: resp.status, headers });
  },
};
