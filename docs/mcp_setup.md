# MCP Integration Setup

Per-integration setup guide for the 5 MCP servers. All env vars go into `backend/.env`.

## 1. GitHub MCP

**Purpose**: Repository read, PR/issue queries, code search. Used by SECURITY agent (audit) and CONTENT_WEB3 (link repos).

1. **Create a Personal Access Token (classic)**:
   - Go to https://github.com/settings/tokens → **Generate new token (classic)**.
   - Note: Fine-grained PAT also works; classic is simpler for all-repo access.
2. **Scopes**:
   - ✅ `repo` (Full control of private repositories) — required to read private repos.
   - For public-only repos you can use `public_repo` subset.
3. **Set env vars** in `backend/.env`:
   ```
   GITHUB_TOKEN=ghp_yourtokenhere
   ```
4. **Doctor probe** (once backend is running):
   ```bash
   curl http://localhost:8000/api/mcp/doctor | jq '.servers[] | select(.name=="github")'
   ```
   Or if you have `openclaw` CLI installed:
   ```bash
   openclaw mcp doctor github --probe
   ```
   Expected: `status: "healthy"`.

---

## 2. Notion MCP

**Purpose**: Knowledge base reads/writes. Used by almost every agent for KB lookup.

1. **Create a Notion integration**:
   - Go to https://www.notion.so/my-integrations → **New integration**.
   - Name: "Monster Agent".
   - Workspace: select your workspace.
   - **Capabilities**: check `Read content`, `Insert content`, `Update content`.
2. **Share your database / pages with the integration**:
   - Open your knowledge base Notion page → `...` (top right) → **+ Add connections** → select "Monster Agent".
   - Do the same for each Database you want the agent to use (e.g. Lessons KB, Tasks DB).
3. **Copy the Database ID**:
   - Open the target DB in full-page view. URL format:
     `https://www.notion.so/<workspace>/<DB_ID>?v=...`
   - DB_ID is the 32-char hex string (with hyphens optional).
4. **Set env vars**:
   ```
   NOTION_TOKEN=secret_yourtokenhere
   NOTION_DB_ID=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```
5. **Doctor probe**:
   ```bash
   curl http://localhost:8000/api/mcp/doctor | jq '.servers[] | select(.name=="notion")'
   ```
   Expected: `status: "healthy"`, `database_accessible: true`.

---

## 3. Google Workspace MCP

**Purpose**: Google Docs, Sheets, Drive reads/writes. Used by EDITOR (docs) and FOOTBALL (sheets for stats).

### Option A: OAuth (interactive, recommended for dev)

1. **Create project + OAuth credentials**:
   - Go to https://console.cloud.google.com/projectcreate → New Project.
   - Go to **APIs & Services → OAuth consent screen**:
     - User type: **External** (with a single-user test it still works fine).
     - Add scopes: `.../auth/documents`, `.../auth/spreadsheets`, `.../auth/drive.readonly`.
     - Add your email to **Test users**.
     - Publishing status: leave in **Testing** (no review needed for you).
   - Go to **APIs & Services → Credentials → Create Credentials → OAuth client ID**:
     - Application type: **Desktop app** or **Web application**.
     - Save the Client ID and Client Secret.
2. **Enable APIs**:
   - https://console.cloud.google.com/apis/library/docs.googleapis.com → Enable.
   - https://console.cloud.google.com/apis/library/sheets.googleapis.com → Enable.
   - https://console.cloud.google.com/apis/library/drive.googleapis.com → Enable.
3. **Set env vars**:
   ```
   GOOGLE_WORKSPACE_CLIENT_ID=xxxxxxxxxxxx-xxxx.apps.googleusercontent.com
   GOOGLE_WORKSPACE_CLIENT_SECRET=GOCSPX-xxxxxx
   ```
4. On first MCP invocation the Manager will guide you through OAuth flow (open URL → paste code).

### Option B: Service Account (headless, for Render deploy)

1. IAM → Service Accounts → Create → Add JSON key → download.
2. Share target Drive folders/docs with the service account email.
3. Store the JSON key contents as a Render secret env var (or file on disk).

---

## 4. Slack MCP

**Purpose**: Send task-complete notifications, pipeline step events to a channel.

1. **Create a Slack App**:
   - Go to https://api.slack.com/apps → **Create New App → From scratch**.
   - App Name: "Monster Agent", pick your workspace.
2. **Pick your token type** (you mentioned having two — use this table to decide):

| Token type | Prefix | Created at | Common scopes | When to use it |
|-----------|--------|-----------|---------------|----------------|
| **Bot User OAuth Token** (RECOMMENDED) | `xoxb-` | **OAuth & Permissions → OAuth Tokens for Your Workspace** | `chat:write`, `channels:read`, `groups:read` | Bot acts as its own user (e.g. `@Monster Agent`). Cleanest permissions model. **Set this as `SLACK_BOT_TOKEN`.** |
| User OAuth Token | `xoxp-` | **OAuth & Permissions → OAuth Tokens for Your Workspace**, under *User* section | Depends on scopes you grant | Acts as **you** (posts under your name, sees everything you see). Good for DMs or private channels the bot isn't invited to. **Set as `SLACK_USER_TOKEN` (optional).** |

3. **If using Bot Token (xoxb-) — add scopes & install**:
   - OAuth & Permissions → Scopes → **Bot Token Scopes**:
     - ✅ `chat:write` — send messages to channels.
     - ✅ `channels:read` — list channels (for doctor check).
   - **Install to Workspace** → Authorize.
   - Copy the **Bot User OAuth Token** (starts with `xoxb-`).
4. **Invite the bot to your channel** in Slack:
   ```
   /invite @Monster Agent
   ```
5. **Set env vars**:
   ```
   # Set the one you want to use as primary. If both are set, SLACK_BOT_TOKEN wins.
   SLACK_BOT_TOKEN=xoxb-xxxxxxxxxx
   SLACK_USER_TOKEN=xoxp-xxxxxxxxxx   # optional
   SLACK_CHANNEL=#agent-updates
   ```
6. **Doctor probe**:
   ```bash
   curl http://localhost:8000/api/mcp/doctor | jq '.servers[] | select(.name=="slack")'
   ```
   Expected: `status: "healthy"`, `channel_found: true`.

7. **Token selection logic in code** (`backend/src/mcp/servers/slack.py`):
   - Step 1: If `SLACK_BOT_TOKEN` non-empty → use it.
   - Step 2: Else if `SLACK_USER_TOKEN` non-empty → use it.
   - Step 3: Else → no-op (tools gracefully handle missing token).
   - Both tokens are ALSO forwarded to the shim as separate env vars in case a future tool needs to mix-and-match (e.g. bot sends messages, user token lists private channels).

---

## 5. Hashnode MCP

**Purpose**: Draft and publish blog posts. Used by CONTENT_WEB2 and CONTENT_WEB3.

**Note**: Hashnode MCP lives in a separate TypeScript subproject at `mcp-servers/hashnode/` because Hashnode's official SDK is Node-first. The Python `mcp/servers/hashnode.py` wraps the built JS bundle.

1. **Create a Hashnode Personal Access Token**:
   - Go to https://engineer.hashnode.com/settings/personal-access-tokens → **Generate New Token**.
   - Give it a name, copy the token (shown once).
2. **Find your Publication ID**:
   - Open your Hashnode blog (e.g. `https://<user>.hashnode.dev`).
   - Go to **Dashboard → Blog → Settings** — URL contains the ID, or use:
     ```bash
     curl -X POST https://gql.hashnode.com \
       -H "Authorization: <YOUR_TOKEN>" \
       -H "Content-Type: application/json" \
       -d '{"query":"{me{publications{_id title}}}"}'
     ```
3. **Build the Hashnode MCP server** (TypeScript):
   ```bash
   cd mcp-servers/hashnode
   npm install
   npm run build
   ```
   Verify `mcp-servers/hashnode/dist/index.js` exists.
4. **Set env vars** (both places — the TS bundle uses its own, Python wrapper also uses them):
   - `backend/.env`:
     ```
     HASHNODE_TOKEN=yourhashnodepat
     HASHNODE_PUBLICATION_ID=6xxxxx...
     ```
   - `mcp-servers/hashnode/.env` (copied from `.env.example`):
     ```
     HASHNODE_TOKEN=yourhashnodepat
     HASHNODE_PUBLICATION_ID=6xxxxx...
     LOG_LEVEL=info
     ```
5. **Doctor probe**:
   ```bash
   curl http://localhost:8000/api/mcp/doctor | jq '.servers[] | select(.name=="hashnode")'
   ```
   Expected: `status: "healthy"`, `publication_valid: true`.

---

## Doctor Verification Flow

Run the full MCP health check after setting all up:

```bash
curl -s http://localhost:8000/api/mcp/doctor | jq .
```

Expected output:
```json
{
  "overall": "healthy",
  "checked_at": "2025-...",
  "servers": [
    { "name": "github",         "status": "healthy", "latency_ms": 42 },
    { "name": "notion",         "status": "healthy", "latency_ms": 120 },
    { "name": "google_workspace", "status": "healthy", "latency_ms": 180 },
    { "name": "slack",          "status": "healthy", "latency_ms": 90 },
    { "name": "hashnode",       "status": "healthy", "latency_ms": 110 }
  ],
  "healthy_count": 5,
  "total_count": 5
}
```

All 5 healthy = you're good to run the pipeline with full MCP tool access.
