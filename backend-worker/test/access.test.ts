/**
 * Access verification, with real signatures.
 *
 * The forgery cases are the point. A verifier that accepts a token it should
 * not is worse than no verifier, because the X-Access-Enforcement header then
 * says "enforce" while the door stands open.
 */

import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { isBypassed, verifyAccess } from "../src/access";

const TEAM = "team.cloudflareaccess.com";
const AUD = "aud-tag-for-this-app";

let keyPair: CryptoKeyPair;
let otherPair: CryptoKeyPair;
let jwks: { keys: any[] };

function b64url(bytes: Uint8Array | string): string {
  const raw =
    typeof bytes === "string"
      ? bytes
      : String.fromCharCode(...Array.from(bytes));
  return btoa(raw).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

async function sign(
  payload: Record<string, unknown>,
  opts: { kid?: string; alg?: string; key?: CryptoKey } = {},
): Promise<string> {
  const header = { alg: opts.alg ?? "RS256", kid: opts.kid ?? "key-1", typ: "JWT" };
  const signingInput = `${b64url(JSON.stringify(header))}.${b64url(JSON.stringify(payload))}`;
  const signature = await crypto.subtle.sign(
    "RSASSA-PKCS1-v1_5",
    opts.key ?? keyPair.privateKey,
    new TextEncoder().encode(signingInput),
  );
  return `${signingInput}.${b64url(new Uint8Array(signature))}`;
}

function claims(extra: Record<string, unknown> = {}) {
  const now = Math.floor(Date.now() / 1000);
  return {
    aud: [AUD],
    iss: `https://${TEAM}`,
    exp: now + 600,
    iat: now,
    email: "datumlabss@gmail.com",
    ...extra,
  };
}

function req(token?: string, path = "/api/commitments"): Request {
  return new Request(`https://backend.workers.dev${path}`, {
    headers: token ? { "Cf-Access-Jwt-Assertion": token } : {},
  });
}

const config = { teamDomain: TEAM, aud: AUD };

beforeAll(async () => {
  const algorithm = {
    name: "RSASSA-PKCS1-v1_5",
    modulusLength: 2048,
    publicExponent: new Uint8Array([1, 0, 1]),
    hash: "SHA-256",
  };
  keyPair = await crypto.subtle.generateKey(algorithm, true, ["sign", "verify"]);
  otherPair = await crypto.subtle.generateKey(algorithm, true, ["sign", "verify"]);
  const pub = await crypto.subtle.exportKey("jwk", keyPair.publicKey);
  jwks = { keys: [{ ...pub, kid: "key-1", alg: "RS256" }] };

  vi.stubGlobal("fetch", async (url: any) => {
    if (String(url).includes("/cdn-cgi/access/certs")) {
      return new Response(JSON.stringify(jwks), { status: 200 });
    }
    throw new Error(`unexpected fetch ${url}`);
  });
});

afterEach(() => vi.clearAllMocks());

describe("enforcement is off until configured", () => {
  it("passes everything through when both variables are unset", async () => {
    const result = await verifyAccess(req(), {});
    expect(result).toEqual({ ok: true, mode: "off" });
  });

  it("is still off with only one of the two set", async () => {
    expect((await verifyAccess(req(), { teamDomain: TEAM })).mode).toBe("off");
    expect((await verifyAccess(req(), { aud: AUD })).mode).toBe("off");
  });
});

describe("a valid token", () => {
  it("is accepted and names who it is", async () => {
    const result = await verifyAccess(req(await sign(claims())), config);
    expect(result).toMatchObject({ ok: true, mode: "enforce", serviceToken: false });
  });

  it("is recognised as a service token when it has a common_name and no email", async () => {
    const token = await sign(claims({ email: undefined, common_name: "bot-client-id" }));
    const result = await verifyAccess(req(token), config);
    expect(result).toMatchObject({ ok: true, serviceToken: true, subject: "bot-client-id" });
  });

  it("is read from the cookie too, for a browser session", async () => {
    const token = await sign(claims());
    const request = new Request("https://backend.workers.dev/api/day", {
      headers: { Cookie: `other=1; CF_Authorization=${token}` },
    });
    expect((await verifyAccess(request, config)).ok).toBe(true);
  });
});

describe("forgeries are refused", () => {
  it("refuses a request with no token at all", async () => {
    const result = await verifyAccess(req(), config);
    expect(result).toMatchObject({ ok: false, status: 401 });
  });

  it("refuses a token signed by the wrong key", async () => {
    const token = await sign(claims(), { key: otherPair.privateKey });
    expect(await verifyAccess(req(token), config)).toMatchObject({
      ok: false,
      reason: "bad signature",
    });
  });

  it("refuses alg=none rather than reading the algorithm off the token", async () => {
    const header = b64url(JSON.stringify({ alg: "none", kid: "key-1" }));
    const body = b64url(JSON.stringify(claims()));
    const result = await verifyAccess(req(`${header}.${body}.`), config);
    expect(result).toMatchObject({ ok: false, status: 401 });
  });

  it("refuses a tampered payload", async () => {
    const token = await sign(claims());
    const [h, , s] = token.split(".");
    const swapped = b64url(JSON.stringify(claims({ email: "someone@else.com" })));
    expect(await verifyAccess(req(`${h}.${swapped}.${s}`), config)).toMatchObject({
      ok: false,
      reason: "bad signature",
    });
  });

  it("refuses a valid token issued for a different Access application", async () => {
    const token = await sign(claims({ aud: ["a-different-apps-aud"] }));
    expect(await verifyAccess(req(token), config)).toMatchObject({ ok: false, status: 403 });
  });

  it("refuses a token from another team's issuer", async () => {
    const token = await sign(claims({ iss: "https://attacker.cloudflareaccess.com" }));
    expect(await verifyAccess(req(token), config)).toMatchObject({ ok: false, status: 403 });
  });

  it("refuses an expired token", async () => {
    const token = await sign(claims({ exp: Math.floor(Date.now() / 1000) - 10 }));
    expect(await verifyAccess(req(token), config)).toMatchObject({ ok: false, reason: "token expired" });
  });

  it("refuses a token signed with an unknown key id", async () => {
    const token = await sign(claims(), { kid: "rotated-away" });
    expect(await verifyAccess(req(token), config)).toMatchObject({
      ok: false,
      reason: "unknown signing key",
    });
  });
});

describe("the bypass list", () => {
  it("covers the telegram webhook, which cannot complete an Access login", () => {
    expect(isBypassed("/api/telegram/webhook")).toBe(true);
    expect(isBypassed("/api/health")).toBe(true);
  });

  it("covers the agent card, so a refused agent can read how to get in", () => {
    expect(isBypassed("/api/agent-card")).toBe(true);
    expect(isBypassed("/.well-known/agent-card.json")).toBe(true);
  });

  it("covers nothing else", () => {
    for (const path of [
      "/api/commitments",
      "/api/notify/send",
      "/api/agents/researcher/invoke",
      "/api/tasks/123",
      "/api/telegram/drain",
      "/api/telegram/webhook/register",
    ]) {
      expect(isBypassed(path)).toBe(false);
    }
  });

  it("lets a bypassed path through with no token", async () => {
    const result = await verifyAccess(req(undefined, "/api/health"), config);
    expect(result).toMatchObject({ ok: true, subject: "bypass" });
  });
});
