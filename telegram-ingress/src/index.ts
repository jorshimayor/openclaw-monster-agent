/**
 * Telegram ingress.
 *
 * Cloudflare Access protects the whole of monster-agent-backend, and Access
 * cannot be scoped to a path when the destination is a Worker. Telegram cannot
 * sign in to Access and cannot send a service token, so a webhook pointed at
 * the protected Worker would be 403'd at the edge forever.
 *
 * This Worker is therefore deliberately NOT behind Access. It is not a hole in
 * the wall, because it is not a second front door: it serves exactly one method
 * on exactly one path, verifies Telegram's own secret-token header before
 * anything else happens, and forwards to the same container instance the main
 * Worker uses. Everything else gets a 404 that reveals nothing.
 *
 * The alternative was dropping the webhook and relying on the ten-minute cron
 * drain, which works — but a bot that chases you is a bot you reply to, and ten
 * minutes between "here is the artifact" and the nagging stopping is the part
 * you would feel.
 */

export type Env = {
  // Cross-script binding to the Durable Object defined in monster-agent-backend.
  // This Worker does not define the class; it borrows the namespace.
  BACKEND_CONTAINER: DurableObjectNamespace;
  TELEGRAM_WEBHOOK_SECRET?: string;
};

/**
 * The same instance name the main Worker passes to getContainer(), which is
 * idFromName() underneath. A different name would be a different container
 * with different in-process task state — the bug would look like messages
 * landing in a parallel universe.
 */
const CONTAINER_INSTANCE = "backend-primary";

const WEBHOOK_PATH = "/api/telegram/webhook";

/** Constant-time compare, so a wrong secret cannot be guessed a byte at a time. */
function secretsMatch(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // One path, one method. A 404 for everything else, rather than a 405 that
    // would confirm the path exists.
    if (url.pathname !== WEBHOOK_PATH || request.method !== "POST") {
      return new Response("not found", { status: 404 });
    }

    const expected = env.TELEGRAM_WEBHOOK_SECRET;
    if (!expected) {
      // Refuse rather than forward. An ingress with no secret configured is an
      // open relay into the container, and failing loudly here is how that gets
      // noticed on the first request instead of in a log nobody reads.
      return new Response("ingress misconfigured: no webhook secret", { status: 503 });
    }

    const presented = request.headers.get("X-Telegram-Bot-Api-Secret-Token") ?? "";
    if (!secretsMatch(presented, expected)) {
      // Checked before touching the container, so a flood of junk cannot wake
      // it or cost anything.
      return new Response("forbidden", { status: 403 });
    }

    const id = env.BACKEND_CONTAINER.idFromName(CONTAINER_INSTANCE);
    const stub = env.BACKEND_CONTAINER.get(id);
    return stub.fetch(new Request(`http://container${WEBHOOK_PATH}`, request));
  },
};
