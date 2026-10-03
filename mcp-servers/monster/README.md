# monster-mcp

Lets another agent talk to the Monster Agent over MCP.

```bash
npm install && npm run build
MONSTER_API_BASE_URL=https://monster-agent-backend.<account>.workers.dev \
MONSTER_ACCESS_CLIENT_ID=... \
MONSTER_ACCESS_CLIENT_SECRET=... \
npm start
```

Eight tools: `get_today`, `list_commitments`, `create_commitment`,
`close_commitment`, `get_fellowship_status`, `list_tasks`, `create_task`,
`notify`.

Without the service token it still runs and still works — which is what the
API allows today — and says so on startup rather than pretending otherwise.

Setup, including the Cloudflare Access steps, is in
[`docs/agent-access.md`](../../docs/agent-access.md).
