/**
 * The ingress is the one thing deliberately outside Access, so what it refuses
 * matters more than what it accepts.
 */

import { describe, expect, it, vi } from "vitest";

import worker, { type Env } from "../src/index";

const SECRET = "a-long-telegram-webhook-secret";

// null means "not configured" — distinct from omitting the argument, which
// takes the default. Passing undefined would silently take the default too,
// which is how the misconfigured-ingress test first passed against a 200.
function makeEnv(secret: string | null = SECRET) {
  const containerFetch = vi.fn(
    async (_request: Request) => new Response('{"ok":true}', { status: 200 }),
  );
  const get = vi.fn(() => ({ fetch: containerFetch }));
  const idFromName = vi.fn((name: string) => ({ name }));
  const env = {
    BACKEND_CONTAINER: { idFromName, get },
    TELEGRAM_WEBHOOK_SECRET: secret ?? undefined,
  } as unknown as Env;
  return { env, containerFetch, get, idFromName };
}

function post(path = "/api/telegram/webhook", secret?: string, method = "POST") {
  return new Request(`https://ingress.workers.dev${path}`, {
    method,
    headers: secret === undefined ? {} : { "X-Telegram-Bot-Api-Secret-Token": secret },
    body: method === "POST" ? JSON.stringify({ update_id: 1 }) : undefined,
  });
}

describe("a genuine Telegram update", () => {
  it("is forwarded to the container", async () => {
    const { env, containerFetch } = makeEnv();
    const response = await worker.fetch(post(undefined, SECRET), env);
    expect(response.status).toBe(200);
    expect(containerFetch).toHaveBeenCalledOnce();
  });

  it("goes to the SAME container instance the main Worker uses", async () => {
    // A different instance name means a different container with different
    // in-process state, which would look like messages vanishing.
    const { env, idFromName } = makeEnv();
    await worker.fetch(post(undefined, SECRET), env);
    expect(idFromName).toHaveBeenCalledWith("backend-primary");
  });

  it("reaches the webhook path on the container", async () => {
    const { env, containerFetch } = makeEnv();
    await worker.fetch(post(undefined, SECRET), env);
    const forwarded = containerFetch.mock.calls[0]![0] as unknown as Request;
    expect(new URL(forwarded.url).pathname).toBe("/api/telegram/webhook");
    expect(forwarded.method).toBe("POST");
  });
});

describe("everything else is refused without touching the container", () => {
  it("rejects a wrong secret", async () => {
    const { env, containerFetch } = makeEnv();
    const response = await worker.fetch(post(undefined, "wrong-secret-entirely"), env);
    expect(response.status).toBe(403);
    expect(containerFetch).not.toHaveBeenCalled();
  });

  it("rejects a missing secret", async () => {
    const { env, containerFetch } = makeEnv();
    expect((await worker.fetch(post(), env)).status).toBe(403);
    expect(containerFetch).not.toHaveBeenCalled();
  });

  it("rejects a secret that is a prefix of the real one", async () => {
    const { env } = makeEnv();
    const response = await worker.fetch(post(undefined, SECRET.slice(0, -1)), env);
    expect(response.status).toBe(403);
  });

  it("404s every other path, including the rest of the API", async () => {
    const { env, containerFetch } = makeEnv();
    for (const path of [
      "/api/commitments",
      "/api/notify/send",
      "/api/telegram/drain",
      "/api/telegram/webhook/register",
      "/",
    ]) {
      const response = await worker.fetch(post(path, SECRET), env);
      expect(response.status, path).toBe(404);
    }
    expect(containerFetch).not.toHaveBeenCalled();
  });

  it("404s a GET on the webhook path rather than 405, which would confirm it exists", async () => {
    const { env } = makeEnv();
    const response = await worker.fetch(post("/api/telegram/webhook", SECRET, "GET"), env);
    expect(response.status).toBe(404);
  });

  it("refuses to forward at all when no secret is configured", async () => {
    // Otherwise this is an open relay into the container.
    const { env, containerFetch } = makeEnv(null);
    const response = await worker.fetch(post(undefined, SECRET), env);
    expect(response.status).toBe(503);
    expect(containerFetch).not.toHaveBeenCalled();
  });
});
