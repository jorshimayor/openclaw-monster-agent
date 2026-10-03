/**
 * HTTP client for the Monster Agent API.
 *
 * Carries the Cloudflare Access service token on every request. The token
 * lives in this process's environment and never reaches the calling agent,
 * which is the point of putting an MCP server in front of the API rather than
 * handing another bot a URL and a credential.
 */

export class MonsterApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly body: string,
  ) {
    super(message);
    this.name = "MonsterApiError";
  }
}

export type ClientConfig = {
  baseUrl: string;
  clientId?: string;
  clientSecret?: string;
  timeoutMs?: number;
};

export class MonsterClient {
  private readonly baseUrl: string;
  private readonly headers: Record<string, string>;
  private readonly timeoutMs: number;

  constructor(config: ClientConfig) {
    this.baseUrl = config.baseUrl.replace(/\/+$/, "");
    this.timeoutMs = config.timeoutMs ?? 30_000;
    this.headers = { "Content-Type": "application/json" };
    if (config.clientId && config.clientSecret) {
      this.headers["CF-Access-Client-Id"] = config.clientId;
      this.headers["CF-Access-Client-Secret"] = config.clientSecret;
    }
  }

  get authenticated(): boolean {
    return "CF-Access-Client-Id" in this.headers;
  }

  async request<T = unknown>(
    method: "GET" | "POST" | "DELETE",
    path: string,
    body?: unknown,
  ): Promise<T> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeoutMs);
    try {
      const response = await fetch(`${this.baseUrl}${path}`, {
        method,
        headers: this.headers,
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: controller.signal,
      });
      const text = await response.text();
      if (!response.ok) {
        // 401/403 here almost always means the service token is missing or is
        // not on the Access policy, so say that rather than echoing a bare code.
        const hint =
          response.status === 401 || response.status === 403
            ? this.authenticated
              ? " — the service token is set but not allowed by the Access policy"
              : " — no service token is set; see MONSTER_ACCESS_CLIENT_ID"
            : "";
        throw new MonsterApiError(
          `${method} ${path} failed: ${response.status}${hint}`,
          response.status,
          text.slice(0, 600),
        );
      }
      return (text ? JSON.parse(text) : null) as T;
    } finally {
      clearTimeout(timer);
    }
  }
}
