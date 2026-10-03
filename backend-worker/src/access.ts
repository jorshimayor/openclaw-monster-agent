/**
 * Cloudflare Access verification.
 *
 * Access sits in front of this Worker and, on an allowed request, injects a
 * signed JWT in `Cf-Access-Jwt-Assertion`. A human gets one after signing in;
 * a bot gets one by presenting a service token (`CF-Access-Client-Id` and
 * `CF-Access-Client-Secret`), which Access exchanges at the edge.
 *
 * The Worker verifies that JWT itself rather than trusting the header's
 * presence. Without verification, anything that can reach the Worker directly
 * can forge the header and walk straight in — the header is only trustworthy
 * because of the signature on it.
 *
 * Enforcement is OFF until ACCESS_AUD and ACCESS_TEAM_DOMAIN are set. That is
 * deliberate: shipping this with enforcement on by default would have locked
 * the live site out the moment it deployed, before the Access app existed. The
 * mode is reported on every response in `X-Access-Enforcement` so "I thought it
 * was on" is answerable by looking.
 */

export type AccessConfig = {
  teamDomain?: string;
  aud?: string;
};

export type AccessResult =
  | { ok: true; mode: "off" }
  | { ok: true; mode: "enforce"; subject: string; serviceToken: boolean }
  | { ok: false; mode: "enforce"; status: number; reason: string };

/**
 * Paths that must stay reachable without an Access session.
 *
 * Telegram signs its webhook with its own secret-token header and cannot
 * complete an Access login, so putting it behind Access would silently kill
 * every inbound message. It is not unauthenticated — it is authenticated by a
 * different mechanism, checked in FastAPI.
 */
const BYPASS = [
  /^\/api\/telegram\/webhook\/?$/,
  /^\/api\/health\/?$/,
  // An agent that cannot authenticate is exactly the one that needs to read
  // how. Gating the instructions behind the gate they describe is a dead end.
  /^\/api\/agent-card\/?$/,
  /^\/\.well-known\/agent-card\.json$/,
];

/** Where a refused caller is told to look. */
export const AGENT_CARD_PATH = "/api/agent-card";

export function isBypassed(pathname: string): boolean {
  return BYPASS.some((re) => re.test(pathname));
}

type Jwk = { kid: string; kty: string; alg?: string; n: string; e: string };

// Keys rotate, so they are cached briefly rather than for the life of the
// isolate — long enough to avoid a fetch per request, short enough to pick up
// a rotation without a redeploy.
const KEY_TTL_MS = 10 * 60 * 1000;
let keyCache: { domain: string; fetchedAt: number; keys: Map<string, CryptoKey> } | null = null;

async function publicKeys(teamDomain: string): Promise<Map<string, CryptoKey>> {
  const now = Date.now();
  if (keyCache && keyCache.domain === teamDomain && now - keyCache.fetchedAt < KEY_TTL_MS) {
    return keyCache.keys;
  }
  const url = `https://${teamDomain}/cdn-cgi/access/certs`;
  const response = await fetch(url, { cf: { cacheTtl: 300 } } as RequestInit);
  if (!response.ok) {
    throw new Error(`access certs ${response.status} from ${url}`);
  }
  const body = (await response.json()) as { keys?: Jwk[] };
  const keys = new Map<string, CryptoKey>();
  for (const jwk of body.keys ?? []) {
    const key = await crypto.subtle.importKey(
      "jwk",
      { kty: jwk.kty, n: jwk.n, e: jwk.e, alg: "RS256", ext: true },
      { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
      false,
      ["verify"],
    );
    keys.set(jwk.kid, key);
  }
  keyCache = { domain: teamDomain, fetchedAt: now, keys };
  return keys;
}

function b64urlToBytes(value: string): Uint8Array<ArrayBuffer> {
  const padded = value.replace(/-/g, "+").replace(/_/g, "/");
  const binary = atob(padded + "=".repeat((4 - (padded.length % 4)) % 4));
  const out = new Uint8Array(new ArrayBuffer(binary.length));
  for (let i = 0; i < binary.length; i++) out[i] = binary.charCodeAt(i);
  return out;
}

function decodeJson(segment: string): any {
  return JSON.parse(new TextDecoder().decode(b64urlToBytes(segment)));
}

export async function verifyAccess(request: Request, config: AccessConfig): Promise<AccessResult> {
  const { teamDomain, aud } = config;
  if (!teamDomain || !aud) {
    return { ok: true, mode: "off" };
  }

  const url = new URL(request.url);
  if (isBypassed(url.pathname)) {
    return { ok: true, mode: "enforce", subject: "bypass", serviceToken: false };
  }

  const token =
    request.headers.get("Cf-Access-Jwt-Assertion") ??
    (request.headers.get("Cookie") ?? "").match(/(?:^|;\s*)CF_Authorization=([^;]+)/)?.[1];
  if (!token) {
    return {
      ok: false,
      mode: "enforce",
      status: 401,
      reason: "no Access token — sign in, or send CF-Access-Client-Id/Secret",
    };
  }

  const parts = token.split(".");
  if (parts.length !== 3) {
    return { ok: false, mode: "enforce", status: 401, reason: "malformed Access token" };
  }

  let header: any;
  let payload: any;
  try {
    header = decodeJson(parts[0]);
    payload = decodeJson(parts[1]);
  } catch {
    return { ok: false, mode: "enforce", status: 401, reason: "undecodable Access token" };
  }

  if (header.alg !== "RS256") {
    // "none" and HMAC confusion are the classic JWT forgeries; the algorithm
    // is pinned rather than read from the token it is meant to protect.
    return { ok: false, mode: "enforce", status: 401, reason: `unexpected alg ${header.alg}` };
  }

  const keys = await publicKeys(teamDomain);
  const key = header.kid ? keys.get(header.kid) : undefined;
  if (!key) {
    return { ok: false, mode: "enforce", status: 401, reason: "unknown signing key" };
  }

  const valid = await crypto.subtle.verify(
    "RSASSA-PKCS1-v1_5",
    key,
    b64urlToBytes(parts[2]),
    new TextEncoder().encode(`${parts[0]}.${parts[1]}`),
  );
  if (!valid) {
    return { ok: false, mode: "enforce", status: 401, reason: "bad signature" };
  }

  const audiences: string[] = Array.isArray(payload.aud) ? payload.aud : [payload.aud];
  if (!audiences.includes(aud)) {
    // A valid token for a DIFFERENT Access application in the same account
    // would otherwise be accepted here.
    return { ok: false, mode: "enforce", status: 403, reason: "token is for another application" };
  }
  if (payload.iss !== `https://${teamDomain}`) {
    return { ok: false, mode: "enforce", status: 403, reason: "wrong issuer" };
  }

  const now = Math.floor(Date.now() / 1000);
  if (typeof payload.exp === "number" && payload.exp < now) {
    return { ok: false, mode: "enforce", status: 401, reason: "token expired" };
  }
  if (typeof payload.nbf === "number" && payload.nbf > now + 60) {
    return { ok: false, mode: "enforce", status: 401, reason: "token not yet valid" };
  }

  // A service token has no email; Access puts the client id in common_name.
  const serviceToken = !payload.email && Boolean(payload.common_name);
  return {
    ok: true,
    mode: "enforce",
    subject: payload.email ?? payload.common_name ?? "unknown",
    serviceToken,
  };
}
