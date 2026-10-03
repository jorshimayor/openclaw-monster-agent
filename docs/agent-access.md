# Letting other bots in

Two halves: a gate, and a door. The gate is Cloudflare Access on the API; the
door is an MCP server other agents speak to.

## Where this started

The API was open. Not loosely protected — open:

```bash
curl https://monster-agent-backend.<account>.workers.dev/api/commitments
```

returned the commitment ledger with no credential of any kind. CORS did not
help, because CORS restrains browsers and a bot is not a browser. Twenty-nine
mutating endpoints were reachable, including `POST /api/notify/send` (sends you
a Telegram message as your own bot), `POST /api/agents/{role}/invoke` (runs
your agents on your credits) and `POST /api/commitments/purge`.

## The gate: Cloudflare Access

Access authenticates at the edge. A human signs in; a bot presents a **service
token**. Either way Access injects a signed JWT, and
[`backend-worker/src/access.ts`](../backend-worker/src/access.ts) verifies it
before the request reaches the container — signature, audience, issuer and
expiry. It verifies rather than trusting the header's presence, because an
unverified header is a header anyone can set.

### Enforcement is off until you turn it on

With `ACCESS_TEAM_DOMAIN` and `ACCESS_AUD` unset, the Worker passes everything
through exactly as before. That is deliberate: enforcing by default would have
locked the live site out the moment this deployed, before the Access
application existed.

Every response carries `X-Access-Enforcement: off|enforce`, so the question
"is it actually protected?" is answered by looking:

```bash
curl -sI https://monster-agent-backend.<account>.workers.dev/api/health | grep -i access-enforcement
```

### Turning it on

These are dashboard steps; nothing here can do them for you.

1. **Zero Trust → Access → Applications → Add → Self-hosted.** Domain is your
   Worker hostname. Note the **AUD tag** it gives you.
2. **Policy 1 — you.** Action *Allow*, rule *Emails* → your address.
3. **Policy 2 — bots.** Action *Service Auth*, rule *Service Token* → the
   tokens you issue in step 4.
4. **Access → Service Auth → Create Service Token**, one per bot. The secret is
   shown **once**.
5. Set the two variables and deploy:

   ```bash
   cd backend-worker
   npx wrangler secret put ACCESS_TEAM_DOMAIN   # yourteam.cloudflareaccess.com
   npx wrangler secret put ACCESS_AUD           # the AUD tag from step 1
   npx wrangler deploy
   ```

6. Confirm the header now says `enforce`, and that a bare `curl` gets a 401.

### What must keep working

- **The Telegram webhook.** Telegram cannot complete an Access login, so
  `/api/telegram/webhook` is on the Worker's bypass list. It is not
  unauthenticated — it checks its own secret-token header in FastAPI. Add a
  **Bypass** policy for that path in Access too, or inbound messages stop.
- **`/api/health`.** Bypassed so liveness checks keep working.
- **Cron.** The Worker's scheduled handler calls the container through the
  Durable Object stub, not the public hostname, so it never meets Access.
- **The frontend.** It calls this API from the browser. Put the Pages site
  behind the same Access application, or sign in once and the cookie carries.
- **`fieldtilt`, or anything else already calling `/api/notify/send`.** The
  docstring on that endpoint says sibling systems use it. Every one of them
  needs a service token before you enforce, or they go silent — and they will
  go silent without erroring anywhere you are looking.

## The door: an MCP server

[`mcp-servers/monster`](../mcp-servers/monster) exposes the bot as MCP tools,
so another agent discovers what it can do instead of being handed a URL and a
credential. The service token stays in the server's environment and never
reaches the calling agent.

```json
{
  "mcpServers": {
    "monster": {
      "command": "node",
      "args": ["/absolute/path/to/mcp-servers/monster/dist/index.js"],
      "env": {
        "MONSTER_API_BASE_URL": "https://monster-agent-backend.<account>.workers.dev",
        "MONSTER_ACCESS_CLIENT_ID": "...",
        "MONSTER_ACCESS_CLIENT_SECRET": "..."
      }
    }
  }
}
```

Eight tools: `get_today`, `list_commitments`, `create_commitment`,
`close_commitment`, `get_fellowship_status`, `list_tasks`, `create_task`,
`notify`.

It is not a mirror of the API. `delete`, `purge` and `drop` are left off
deliberately — a sibling bot has no business erasing an accountability record,
and they can be added when there is a reason. Arguments are validated before
they leave the process, so a malformed call never reaches the API and never
costs a container wake.

`close_commitment` obeys the same rule everything else does: a URL, or 40+
characters of substance, or a 422. Another agent cannot close your week by
asserting that it is closed.

## What is still open

- **Enforcement is off** until you do the dashboard steps above. Until then
  this document describes a gate that is not yet shut.
- **No per-token scopes.** Any service token on the policy can call anything,
  including `notify`. Separate Access applications per path prefix would fix
  it; one token is fine while there is one bot.
- **No rate limiting.** Access stops strangers, not a misbehaving bot you let in.
- **The MCP server is stdio only.** Another agent has to be able to run the
  process. A remote transport would let bots connect over the network and is
  the obvious next step if you need one.
