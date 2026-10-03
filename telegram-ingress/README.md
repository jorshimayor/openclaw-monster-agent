# monster-telegram-ingress

One path, one method, no Access.

Cloudflare Access protects the whole of `monster-agent-backend`, and
Access-for-Workers cannot be scoped to a path. Telegram can neither sign in nor
send a service token, so its webhook needs somewhere to land that is not behind
Access. This is that somewhere.

It is not a second front door. It serves only `POST /api/telegram/webhook`,
verifies Telegram's `X-Telegram-Bot-Api-Secret-Token` in constant time before
touching the container, and 404s everything else — including a GET on the
webhook path, which would otherwise confirm it exists. With no secret
configured it returns 503 rather than forwarding, because an ingress without a
secret is an open relay.

```bash
npm install
npx wrangler secret put TELEGRAM_WEBHOOK_SECRET   # same value as the backend
npx wrangler deploy
```

Deploy `monster-agent-backend` first — the Durable Object class this binds to
lives there, and it forwards to the same `backend-primary` instance so task
state is shared.

Full context: [`docs/agent-access.md`](../docs/agent-access.md).
