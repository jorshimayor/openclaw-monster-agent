# Monster Agent · 100% Cloudflare stack (Pages + Containers, FREE tier)

> **Architecture: Frontend on Cloudflare Pages · Backend on Cloudflare Containers (via Worker)**
>
> Zero Vercel, zero Render. Everything runs on Cloudflare's global edge network.
>
> ✅ Verified in repo:
> - Neon Postgres `monster-agent` (aws-us-east-2, PG 18.6) connected
> - DB schema LIVE (tasks + knowledge_crystals tables)
> - Frontend `npm run build` → `npx @cloudflare/next-on-pages` **Build completed in 1.33s**
> - Container Dockerfile + backend Worker scaffolded + dependencies installed
> - Google Workspace: 10 tools wired (Calendar / Docs / Sheets / Gmail send+list+read)
> - GitHub main: pushed

---

## Stack (all on Cloudflare)

| Layer | Host | Runtime | Free limits |
|---|---|---|---|
| 🎯 **Frontend** (Next.js 15 / React 19) | **Cloudflare Pages** | Edge Runtime (Workers) | Unlimited bandwidth, 500 builds/month |
| ⚙️ **Backend API** (FastAPI + Python) | **Cloudflare Containers** + Worker reverse proxy | Docker (python:3.12-slim) | Usage-based billing, 15m idle = scale-to-zero ($0 most months for dev) |
| 🗄️ **Database** (Postgres 18.6) | **Neon Free** | Serverless | 0.5 GB, autowakes ~500 ms |
| ⚡ **DB cache (optional)** | **Cloudflare Hyperdrive** | Edge cache | 10,000,000 queries/month FREE → P95 50 ms |
| 📅 **Google Workspace** | Your account | OAuth refresh token | Whatever your Workspace plan includes |

### Architecture diagram

```
┌──────────────────────┐       ┌──────────────────────────────┐       ┌───────────────────────┐
│ Cloudflare Pages     │──────▶│ Backend Worker (TS @ Worker) │──────▶│  Cloudflare Container │
│  *.pages.dev         │       │  CORS · load-balance · DO    │       │  uvicorn + FastAPI    │
│  @cloudflare/next-…  │       │  BACKEND_CONTAINER binding  │       │  ↘ Neon / Hyperdrive  │
└──────────────────────┘       └──────────────────────────────┘       └───────────────────────┘
     (repo-root wrangler.jsonc)        (backend-worker/)                   (containers/backend/)
```

---

## Prerequisites (your machine)

1. **Cloudflare account** — free tier works.
2. **Docker Desktop** running (for `wrangler containers build`, which calls `docker`).
3. **A real Terminal.app window** — Trae sandbox blocks `~/Library/Preferences/.wrangler` auth paths.

---

## ① BACKEND — Cloudflare Containers (5–10 minutes)

### Step 1. Install deps + auth

```bash
cd /Users/Apple/Code/zc-ai-assistant/backend-worker
npm install --legacy-peer-deps         # already done in this repo

# ⚠️  IMPORTANT — run this EXACT LINE with NO flags, one command per paste.
# Do NOT use --scopes (fails on some wrangler versions). OAuth dialog shows checkboxes,
# check Workers Write, Pages Write, Account Write, KV/R2/D1 Write, Zone Read → Accept.
npx wrangler login
```

### Step 2. Store all secrets as encrypted Worker secrets

Run **each** line once (Cloudflare prompts interactively for the value — never paste secret values directly into shell history):

```bash
# Mandatory — values from backend/.env, keep exact casing:
npx wrangler secret put DATABASE_URL
#   ← paste Neon pooled URL: postgresql+asyncpg://neondb_owner:...@ep-tiny-math-ay0wdkeo-pooler.c-5.us-east-2.aws.neon.tech/neondb?sslmode=require
#   OR paste Hyperdrive URL (after step ③): *.hyperdrive.local?sslmode=require

npx wrangler secret put NVIDIA_NIM_API_KEY
npx wrangler secret put GROQ_API_KEY
npx wrangler secret put GITHUB_TOKEN
npx wrangler secret put NOTION_TOKEN
npx wrangler secret put NOTION_DB_ID                    # use printf '' | npx wrangler secret put NOTION_DB_ID  if blank
npx wrangler secret put SLACK_BOT_TOKEN
npx wrangler secret put SLACK_USER_TOKEN               # (optional) blank via printf '' | ...

# ⚠️  RETIRED: Hashnode API now requires Pro. Skip these 2 secrets:
# npx wrangler secret put HASHNODE_TOKEN
# npx wrangler secret put HASHNODE_PUBLICATION_ID

# Google Workspace — all 4 together (see step ④ to obtain):
npx wrangler secret put GOOGLE_WORKSPACE_CLIENT_ID
npx wrangler secret put GOOGLE_WORKSPACE_CLIENT_SECRET
npx wrangler secret put GOOGLE_WORKSPACE_REFRESH_TOKEN
npx wrangler secret put GOOGLE_WORKSPACE_SUBJECT_EMAIL

# Personal Assistant Agent Telegram notifications (3 secrets → 15 total, see section ⑤):
npx wrangler secret put TELEGRAM_BOT_TOKEN
npx wrangler secret put TELEGRAM_CHAT_ID
npx wrangler secret put TELEGRAM_ADMIN_IDS
```

Non-secret defaults (safe defaults, override only if you need different values) — already set in `backend-worker/wrangler.jsonc` `vars`:

| Key | Default |
|---|---|
| NVIDIA_NIM_BASE_URL | `https://integrate.api.nvidia.com/v1` |
| SLACK_CHANNEL | `#agent-updates` |
| LLM_FALLBACK_ORDER | `["nvidia_nim","groq"]` |
| LOG_LEVEL | `INFO` |
| BACKEND_CORS_ORIGINS | `["http://localhost:3000","http://localhost:8080","*"]` |

To change non-secret defaults after deploy:
```bash
# Edit vars in backend-worker/wrangler.jsonc then re-deploy:
cd backend-worker && npx wrangler deploy
```

### Step 3. Build container image + push + deploy Worker (one command)

```bash
cd /Users/Apple/Code/zc-ai-assistant/backend-worker
npm run container:deploy
#  → builds Docker image (calls docker build with context=repo root)
#  → pushes image to Cloudflare managed registry
#  → deploys Backend Worker + registers Durable Object + Container binding
```

**Expected success output:**
```
📦 Built image monster-agent-backend:latest
📤 Pushed to Cloudflare registry
🌩️  wrangler 4.125.0
...
✨ Compiled Worker successfully
✅ Published monster-agent-backend (xxxx)
     https://monster-agent-backend.YOUR_ACCOUNT_PREFIX.workers.dev   ← 🎯 COPY THIS URL
```

### Step 4. Verify backend live

First request can take 10–20 s because Cloudflare boots the Docker container (cold start). Subsequent requests within 15 minutes return in ~200 ms.

```bash
curl -sS https://monster-agent-backend.YOUR_ACCOUNT_PREFIX.workers.dev/api/health \
     | python3 -m json.tool
# Expected:
#   {
#     "status": "ok",
#     "version": "1.0.0",
#     "db_ok": true    (or false until Neon wakes)
#   }
```

If `db_ok` is false the very first curl, wait 5–10 seconds and retry (Neon free-tier autowake; Hyperdrive eliminates this step if you use it).

---

## ② FRONTEND — Cloudflare Pages (3 minutes)

### Step 1. Point frontend at your backend

Replace the **placeholder** URL in these two locations:

1. **Build-time env var** (for `next-on-pages` bundle):
```bash
export NEXT_PUBLIC_API_BASE_URL=https://monster-agent-backend.YOUR_ACCOUNT_PREFIX.workers.dev
```

2. **`wrangler.jsonc`** at repo root — edit all 4 occurrences of the placeholder:
```
"NEXT_PUBLIC_API_BASE_URL":
    "https://monster-agent-backend.workers.account-prefix.workers.dev"
                                    ^^^^^^^^^^^^^^^^^^^^^ → replace with YOUR_ACCOUNT_PREFIX
```

### Step 2. Build + deploy Pages

```bash
cd /Users/Apple/Code/zc-ai-assistant/frontend
export NEXT_PUBLIC_API_BASE_URL=https://monster-agent-backend.YOUR_ACCOUNT_PREFIX.workers.dev

npm run build
#   Expected: 6 ○ static + ƒ /tasks/[id] dynamic

npx @cloudflare/next-on-pages
#   Expected last line: "⚡️ Build completed in X.XXs"

cd ..
npx wrangler pages deploy frontend/.vercel/output/static \
  --project-name monster-agent-frontend \
  --branch main
```

Prints your Pages URL:
```
✨ Deployment complete!
🔍 https://monster-agent-frontend-xxxx.pages.dev  ← 🎯 YOUR LIVE UI
```

### Step 3. Tighten CORS (recommended)

Your backend currently accepts origins `["localhost...", "*"]`. Once you know the real Pages URL and any custom domains, tighten it:

```bash
# Edit backend-worker/wrangler.jsonc → vars.BACKEND_CORS_ORIGINS:
#   '["https://monster-agent-frontend-xxxx.pages.dev", "http://localhost:3000"]'
# Then re-deploy backend Worker:
cd backend-worker && npx wrangler deploy
```

---

## ③ [OPT] Hyperdrive — drop Neon latency 10× (FREE 10M q/mo)

Cloudflare Hyperdrive caches Neon connection pool + query result cache at the edge.

```bash
cd /Users/Apple/Code/zc-ai-assistant
npx wrangler hyperdrive create monster-agent-neon \
  --connection-string "PASTE_NEON_POOLED_DATABASE_URL_HERE"
```

Output:
```
✅ Created hyperdrive config 'monster-agent-neon' with id='abcd1234-hyperdrive'
   Access via: postgresql://user:pwd@abcd1234-hyperdrive.hyperdrive.local/neondb?sslmode=require
```

Replace the backend `DATABASE_URL` secret with the printed `hyperdrive.local` URL:

```bash
cd backend-worker
npx wrangler secret put DATABASE_URL   # paste hyperdrive URL here
npx wrangler deploy    # reboots Worker; containers pick up new env on next (re)start
```

---

## ④ Google Workspace — Calendar / Docs / Sheets / Gmail (10 minutes)

### One-time OAuth credential setup

1. https://console.cloud.google.com → new project.
2. **APIs & Services → Enable APIs** — enable each:
   - Google Calendar API
   - Google Docs API
   - Google Sheets API
   - Google Drive API
   - Gmail API
3. **OAuth Consent Screen**:
   - User Type: **External** (for `@gmail.com`) · **Internal** (Workspace domain)
   - Scopes → paste exactly these 6:
     ```
     https://www.googleapis.com/auth/calendar
     https://www.googleapis.com/auth/documents
     https://www.googleapis.com/auth/spreadsheets
     https://www.googleapis.com/auth/drive.file
     https://www.googleapis.com/auth/gmail.send
     https://www.googleapis.com/auth/gmail.readonly
     ```
   - **Test users** → add your real email (the one you'll use in monster-agent).
4. **Credentials → Create Credentials → OAuth client ID**:
   - Application type: **Desktop app**
   - Download JSON → save as `backend/client_secret.json`.

### Generate refresh_token (run on your Mac, once)

```bash
cd /Users/Apple/Code/zc-ai-assistant/backend
source .venv/bin/activate 2>/dev/null || python3 -m venv .venv && source .venv/bin/activate
pip install -q 'google-auth-oauthlib>=1.2' 'google-api-python-client>=2.150' python-dotenv

python3 <<'PY'
from google_auth_oauthlib.flow import InstalledAppFlow
SCOPES = [
  "https://www.googleapis.com/auth/calendar",
  "https://www.googleapis.com/auth/documents",
  "https://www.googleapis.com/auth/spreadsheets",
  "https://www.googleapis.com/auth/drive.file",
  "https://www.googleapis.com/auth/gmail.send",
  "https://www.googleapis.com/auth/gmail.readonly",
]
flow = InstalledAppFlow.from_client_secrets_file("client_secret.json", SCOPES)
creds = flow.run_local_server(port=0)
print("\n>>> PASTE THESE 4 INTO 'npx wrangler secret put' COMMANDS (backend-worker dir):")
print("GOOGLE_WORKSPACE_CLIENT_ID       =", flow.client_config["client_id"])
print("GOOGLE_WORKSPACE_CLIENT_SECRET   =", flow.client_config["client_secret"])
print("GOOGLE_WORKSPACE_REFRESH_TOKEN   =", creds.refresh_token)
print("GOOGLE_WORKSPACE_SUBJECT_EMAIL   = <your-email@domain.com>")
PY
```

### Store values as encrypted Worker secrets (back in Terminal):

```bash
cd /Users/Apple/Code/zc-ai-assistant/backend-worker
npx wrangler secret put GOOGLE_WORKSPACE_CLIENT_ID
npx wrangler secret put GOOGLE_WORKSPACE_CLIENT_SECRET
npx wrangler secret put GOOGLE_WORKSPACE_REFRESH_TOKEN
npx wrangler secret put GOOGLE_WORKSPACE_SUBJECT_EMAIL
npx wrangler deploy
```

### Smoke test Google tools locally (optional)

With your 4 values still in `backend/.env`:
```bash
cd backend && .venv/bin/python <<'PY'
import asyncio, os, pathlib, sys
sys.path.insert(0, str(pathlib.Path(".").resolve() / "src"))
from dotenv import load_dotenv; load_dotenv(".env")
from src.mcp.servers.google_workspace import GoogleWorkspaceMcpServer
s = GoogleWorkspaceMcpServer(
    client_id=os.environ["GOOGLE_WORKSPACE_CLIENT_ID"],
    client_secret=os.environ["GOOGLE_WORKSPACE_CLIENT_SECRET"],
    refresh_token=os.environ["GOOGLE_WORKSPACE_REFRESH_TOKEN"],
    subject_email=os.environ["GOOGLE_WORKSPACE_SUBJECT_EMAIL"],
)
tools = s.exposed_tools()
print(f"✅ {len(tools)} Google tools exposed:", [t.name for t in tools])
async def main():
    r = await s.invoke_direct("list_emails", {"max_results": 3})
    if isinstance(r, list):
        print("✅ list_emails returned:", len(r), "emails")
        if r:
            print("   sample subject:", (r[0].get("subject") or r[0].get("snippet"))[:80])
asyncio.run(main())
PY
```

---

## ⑤ Telegram — Personal Assistant Agent (10 minutes, RECOMMENDED)

All task and integration updates flow through exactly one channel: a Personal Assistant
agent running in-process that routes everything to **Telegram**. No agent ever contacts
Slack/email/etc directly — that's the P.A.'s exclusive job. This gives you a single,
rate-limited, priority-tiered stream you can mute or audit from your phone.

### Priority tiers you'll see

| Tier | Icon | Sound | Pin | Rate limit | Examples |
|---|---|---|---|---|---|
| 🔴 **P0 CRITICAL** | 🔴 | 🔔 loud | ✅ auto-pin | unlimited | Task crashed, integration DOWN, DB down |
| 🟠 **P1 ACTION** | 🟠 | 🔔 | ❌ | 3 / 15 min | Integration DEGRADED, manual approvals |
| 🟡 **P2 UPDATE** | 🟡 | silent push | ❌ | 12 / hr | Task created/completed, new knowledge crystal |
| 🔵 **P3 INFO** | 🔵 | never | ❌ | digest only | Routine per-step pipeline progress |

When P.A. decides Telegram spam is starting, it silently drops events into the next
hourly digest instead. Target: ≤ 3 Telegram messages/day + 1 end-of-day digest =
**mission success**. 30 messages/day = **mission failure** (use `/mute 4h`).

### Admin commands you can send to the bot in Telegram

- `/mute 4h` — suppress P2/P3 for 4 hours (P0/P1 always alert)
- `/mute P2` — permanently suppress P2 tier until `/unmute P2`
- `/unmute` / `/unmute P2` — restore
- `/digest` — send rolling summary right now

### Step 1. Create the bot via BotFather (3 clicks)

1. Open <https://t.me/BotFather> in Telegram.
2. Send: `/newbot`
3. Answer BotFather's prompts (friendly name, username ending in `bot`).
4. BotFather replies with an HTTP API token that looks like:
   ```
   1234567890:ABCdefGhIjkLmnOpQrStUvWxYz0123456789
   ```
   **This is `TELEGRAM_BOT_TOKEN`.** Copy it.

### Step 2. Get your private chat id (so bot DMs *you*, not a stranger)

1. BotFather also printed a link: `t.me/<your_bot_username>`. Open it.
2. Click **START** at the bottom (required — bots can't message you first).
3. Send any message to your bot, e.g. "hello monster agent".
4. Visit this URL in a browser:
   ```
   https://api.telegram.org/bot<REPLACE_WITH_BOT_TOKEN>/getUpdates
   ```
5. Look for `result[0].message.chat.id` — it's a **positive integer** for a private DM
   (group/channel ids are negative or `@channelname`). Example output:
   ```json
   {"ok":true,"result":[{"update_id":1234,
     "message":{"message_id":1,"chat":{"id":987654321,"first_name":"You","type":"private"},
                "text":"hello monster agent"}}]}
   ```
6. **`987654321` = `TELEGRAM_CHAT_ID`.** Copy it.

### Step 3. Admin ids

- **`TELEGRAM_ADMIN_IDS`** = comma-separated list of Telegram numeric user IDs who are
  allowed to run `/mute`, `/unmute`, `/digest`. For a single-person deployment it's
  just your own chat id again:
  ```
  TELEGRAM_ADMIN_IDS=987654321
  ```
- For a team, append: `TELEGRAM_ADMIN_IDS=987654321,1122334455`

### Step 4. Save as Worker secrets + redeploy (already listed above in ① Step 2)

```bash
cd /Users/Apple/Code/zc-ai-assistant/backend-worker
npx wrangler secret put TELEGRAM_BOT_TOKEN
npx wrangler secret put TELEGRAM_CHAT_ID
npx wrangler secret put TELEGRAM_ADMIN_IDS
npx wrangler secret list   # expect 17 rows
npx wrangler deploy       # restart container with new env
```

### Step 5. Smoke test Telegram end-to-end (after backend is live)

```bash
# Trigger a task → you should see a 🟡 P2 "Task created" alert in ~10 s.
curl -sSX POST https://monster-agent-backend.YOUR_ACCOUNT_PREFIX.workers.dev/api/tasks \
  -H 'Content-Type: application/json' \
  -d '{"description":"Smoke test: list 3 low-risk things a personal AI assistant could automate for me today and rank by ROI"}'

# Expected in your Telegram DMs (within ~15 s after task creation):
#   🟡 [P2 · UPDATE]  Task created  ·  id=7a3f…
#     Smoke test: list 3 low-risk…
#
# ~90 s later (after pipeline finishes):
#   🟡 [P2 · UPDATE]  Task completed  ·  confidence=96 %
#     1. Sort Gmail inbox  2. Calendar block  3. Crystalize last week's notes
#     → /view full report  → /share doc  → /crystalize
```

**Emergency spam kill switch** — if P.A. misbehaves and spams you:
1. Send `/mute 8h` in Telegram (immediate).
2. Or blank out the token + redeploy (stops Telegram cold):
   ```bash
   printf '' | npx wrangler secret put TELEGRAM_BOT_TOKEN
   npx wrangler deploy
   ```
   Events still accumulate in the P.A. digest buffer until you re-enable.

---

## ⑥ Dashboard URLs

Open these daily:

| URL | Purpose |
|---|---|
| `https://monster-agent-frontend-xxxx.pages.dev` | 🎯 Main UI (Cloudflare Pages) |
| `https://monster-agent-backend.xxxx.workers.dev/api/health` | Backend health → `db_ok:true` |
| https://dash.cloudflare.com → Pages → monster-agent-frontend | Pages: deploys, env, custom domains |
| https://dash.cloudflare.com → Workers & Pages → monster-agent-backend | Backend Worker: secrets, logs, Containers tab (SSH, list instances), Metrics |
| https://dash.cloudflare.com → Hyperdrive → monster-agent-neon | Hyperdrive: queries served, latency, hit rate |
| https://console.neon.tech/app/projects/super-rain-76741199 | Neon DB: query editor, branches, autoscaling |

---

## Appendix A: Deployed files (what we changed for Cloudflare-only)

### Backend (Cloudflare Containers + Worker proxy)
- **[containers/backend/Dockerfile](file:///Users/Apple/Code/zc-ai-assistant/containers/backend/Dockerfile)** — `python:3.12-slim` image, pip install `backend/requirements.txt`, uvicorn listens on 0.0.0.0:8000
- **[containers/backend/start.sh](file:///Users/Apple/Code/zc-ai-assistant/containers/backend/start.sh)** — uvicorn entrypoint, loads `.env` if present for local dev
- **[backend-worker/src/index.ts](file:///Users/Apple/Code/zc-ai-assistant/backend-worker/src/index.ts)** — Worker entrypoint: CORS, getRandom() load-balances across 2 container DOs, forwards all HTTP to container port 8000, injects env vars on first start
- **[backend-worker/package.json](file:///Users/Apple/Code/zc-ai-assistant/backend-worker/package.json)** — `@cloudflare/containers ^0.3.7` + `wrangler ^4.125` + scripts: `deploy`, `container:build`, `container:push`, `container:deploy`
- **[backend-worker/wrangler.jsonc](file:///Users/Apple/Code/zc-ai-assistant/backend-worker/wrangler.jsonc)** — `containers[{ name, class_name, image, image_build_context, instance_type:basic, max_instances:4 }]` + `exports.BACKEND_CONTAINER` durable-object export w/ `container:monster-agent-api` + migration
- **[backend-worker/tsconfig.json](file:///Users/Apple/Code/zc-ai-assistant/backend-worker/tsconfig.json)** — strict TS with `@cloudflare/workers-types`

### Frontend (Cloudflare Pages)
- **[wrangler.jsonc](file:///Users/Apple/Code/zc-ai-assistant/wrangler.jsonc)** — Pages config: `pages_build_output_dir: frontend/.vercel/output/static`, `vars.NEXT_PUBLIC_API_BASE_URL` points to backend worker, env.production + env.preview (Pages-only named envs)
- **[frontend/.npmrc](file:///Users/Apple/Code/zc-ai-assistant/frontend/.npmrc)** — `legacy-peer-deps=true` (avoids next-on-pages peer pin lag)
- **[frontend/package.json](file:///Users/Apple/Code/zc-ai-assistant/frontend/package.json)** — devDeps `wrangler` + `@cloudflare/next-on-pages`
- **[frontend/src/app/tasks/[id]/page.tsx](file:///Users/Apple/Code/zc-ai-assistant/frontend/src/app/tasks/[id]/page.tsx#L3)** — `export const runtime = "edge"` (mandatory for next-on-pages dynamic routes)

### Retired Vercel files (deleted)
- `backend/vercel.json` — previously configured Vercel @vercel/python runtime + rewrites
- `backend/api/index.py` — Mangum ASGI→Lambda entrypoint (Vercel-specific)
- `deploy/render/*` — all Render artifacts (deleted in prior commit)

---

## Appendix B: Troubleshooting

| Symptom | Fix |
|---|---|
| Sandbox: `EPERM open /Users/Apple/Library/Preferences/.wrangler/...` | Trae sandbox blocks Library paths. Run commands in **real Terminal.app**. |
| Backend first request /api/health times out (10–20 s) | Expected for first container cold start. Retry. Later requests < 500 ms for 15 min window. |
| `db_ok: false` first try | Neon's free tier auto-suspends. Retry after 5–10 s or enable Hyperdrive (step ③). |
| Neon SSL `CERTIFICATE_VERIFY_FAILED` locally | Already fixed in [db.py](file:///Users/Apple/Code/zc-ai-assistant/backend/src/core/db.py#L18-L57) engine builder via `certifi` CA bundle. Container image installs `certifi`. |
| `asyncpg` PG enum error `invalid input value for enum taskstatus: "pending"` | Permanently fixed — `tasks.status` now TEXT + Python `@validates` coercion. |
| `@cloudflare/next-on-pages` peer-dep conflict | Fixed by `frontend/.npmrc` `legacy-peer-deps=true`. |
| `/tasks/[id]` route ERROR: not configured for Edge Runtime | Already applied to [tasks/[id]/page.tsx](file:///Users/Apple/Code/zc-ai-assistant/frontend/src/app/tasks/[id]/page.tsx#L3) — rerun `npm run build` before next-on-pages. |
| Google Workspace OAuth `access_denied` | Confirm 6 scopes in consent screen + your email in **Test users** (External apps). |
| Browser CORS `Access-Control-Allow-Origin` error | Tighten `BACKEND_CORS_ORIGINS` in `backend-worker/wrangler.jsonc` → include your real Pages origin → `npx wrangler deploy`. Worker OPTIONS handler mirrors origin for you in the interim. |
| Docker daemon not running during `npm run container:deploy` | Start Docker Desktop; wrangler containers build requires `docker` on $PATH. |
| `getRandom` errors / `Durable Object not found` | Run migration once: `cd backend-worker && npx wrangler deploy`. Migration registers `BackendContainer` class as `new_sqlite_classes`. |

---

## Appendix C: 10 Exposed Google Workspace tools

Server: [google_workspace.py](file:///Users/Apple/Code/zc-ai-assistant/backend/src/mcp/servers/google_workspace.py)

| Tool | Inputs | Purpose |
|---|---|---|
| `create_doc` | `title`, `content?`, `folder_id?` | New Google Doc with optional text content |
| `read_doc` | `doc_id` | Read the full contents of any Google Doc |
| `append_to_doc` | `doc_id`, `content` | Append plain text to a doc |
| `read_calendar` | `time_min`, `time_max`, `calendar_id?`, `max_results?` | List calendar events in an RFC3339 window |
| `create_calendar_event` | `summary`, `start_time`, `end_time`, `description?`, `attendees?`, `calendar_id?` | Insert a new calendar event |
| `write_sheet` | `spreadsheet_id`, `range`, `values[][]` | Write 2D array to `Sheet1!A1:C10` range |
| `read_sheet` | `spreadsheet_id`, `range` | Read 2D values from any Sheets range |
| **`send_email`** | `to`, `subject`, `body_text`, `cc?`, `bcc?` | Send email via Gmail as `subject_email` |
| **`list_emails`** | `max_results?`, `query?` | List Gmail metadata (id, from, subject, date, snippet) |
| **`read_email`** | `message_id`, `format?="full"` | Read Gmail body → `{ plain, html, headers, parts[] }` from multipart payload |

All 10 tools callable from the agent, **and** directly via `await GoogleWorkspaceMcpServer(...).invoke_direct(tool, kwargs)`.
