# Monster Agent · Full Production Stack Playbook (all FREE tier, today)

> **You are fully ready TODAY.** Everything below uses FREE tiers only. No credit card needed for Neon/Vercel Hobby/Render Free/Cloudflare Free.
>
> **Done already (verified live, no action needed):**
> - ✅ Neon Postgres created: `monster-agent` (region `aws-us-east-2`, PG 18.6), DB schema **live** (tables created + verified via Python smoke test)
> - ✅ Neon pooled `DATABASE_URL` injected into `backend/.env`
> - ✅ GitHub `main` pushed: Blueprint IaC, DB layer, Google Workspace direct 10-tool client, Vercel + wrangler configs
> - ✅ Render Blueprint **validated**: `render blueprints validate deploy/render/render.yaml` → `valid: true`
> - ✅ Backend modules smoke-tested against live Neon (tables OK, store bootstrap OK, SSL via certifi OK)
> - ✅ CORS origins pre-whitelisted: `localhost:3000, localhost:8080, https://your-frontend.vercel.app, https://your-frontend.pages.dev`

---

## Stack
| Layer | Host | Plan | Cold Start |
|---|---|---|---|
| Frontend (Next.js 15 / React 19) | **Vercel Hobby** ✅ RECOMMENDED | FREE | 0 ms (cached) |
| *[opt]* Frontend fallback | **Cloudflare Pages** | FREE | ~50 ms |
| Backend (FastAPI / Python 3.11+ / Poetry) | **Render Web Service Free** | FREE | ~5–30 s |
| Database (Postgres 18.6, serverless) | **Neon Free** | FREE | ~500 ms autowake |
| *[opt]* DB edge cache | **Cloudflare Hyperdrive** | FREE (10M q/mo) | ~20 ms |
| Calendar/Docs/Sheets/Gmail | **Google Workspace** | your existing account | — |

---

## 1. BACKEND — Render (5 minutes)

Render Blueprint has **already been validated** against this repo.

**Steps in Render Dashboard** (https://dashboard.render.com/blueprints):

1. Click **New Blueprint Instance**
2. Repo: `jorshimayor/openclaw-monster-agent` · branch: `main`
3. Blueprint path: `deploy/render/render.yaml`
4. Service Name (auto): `monster-agent-backend`
5. Click **Apply**

### 1b. Paste the 17 Env Vars (critical)

Go to Render → `monster-agent-backend` → **Environment** → **Add Environment Variable**:

- **Secrets** (sync:false — paste the **real values** from your local `backend/.env`):

| Key | Value | Where from |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://neondb_owner:...@ep-tiny-math-ay0wdkeo-pooler.c-5.us-east-2.aws.neon.tech/neondb?sslmode=require` | `backend/.env` (copy exact) |
| `NVIDIA_NIM_API_KEY` | your nvapi… key | `backend/.env` |
| `GROQ_API_KEY` | your gsk_… key | `backend/.env` |
| `GITHUB_TOKEN` | your ghp_… key | `backend/.env` |
| `NOTION_TOKEN` | your ntn_… key | `backend/.env` |
| `NOTION_DB_ID` | (if used) | `backend/.env` |
| `SLACK_BOT_TOKEN` | your xoxb-… token | `backend/.env` |
| `SLACK_USER_TOKEN` | (if used) | `backend/.env` |
| `HASHNODE_TOKEN` | (if used) | `backend/.env` |
| `HASHNODE_PUBLICATION_ID` | (if used) | `backend/.env` |
| `GOOGLE_WORKSPACE_CLIENT_ID` | `….apps.googleusercontent.com` | See Step 4 below |
| `GOOGLE_WORKSPACE_CLIENT_SECRET` | OAuth secret | See Step 4 |
| `GOOGLE_WORKSPACE_REFRESH_TOKEN` | `1//…` | See Step 4 |
| `GOOGLE_WORKSPACE_SUBJECT_EMAIL` | `you@yourdomain.com` | the email for calendar/docs/email |

- **Values (already set by Blueprint — confirm they look right):**

| Key | Default |
|---|---|
| `NVIDIA_NIM_BASE_URL` | `https://integrate.api.nvidia.com/v1` |
| `SLACK_CHANNEL` | `#agent-updates` |
| `LLM_FALLBACK_ORDER` | `["nvidia_nim","groq"]` |
| `LOG_LEVEL` | `INFO` |
| `PYTHONUNBUFFERED` | `1` |
| `BACKEND_CORS_ORIGINS` | `["http://localhost:3000","http://localhost:8080","https://your-frontend.vercel.app","https://your-frontend.pages.dev"]` |

> **IMPORTANT:** After you deploy Vercel (Step 2), **add your real Vercel URL to `BACKEND_CORS_ORIGINS`**, e.g.:
> ```
> ["http://localhost:3000","http://localhost:8080","https://monster-agent-frontend.vercel.app","https://your-frontend.pages.dev"]
> ```

### 1c. Verify backend is live

Render build = 3–10 minutes. When the badge turns **Live**:

```bash
curl -sS https://monster-agent-backend.onrender.com/api/health | python3 -m json.tool
```

Expected response includes `"db_ok": true`.

---

## 2. FRONTEND — Vercel Hobby (3 minutes)

Run these **OUTSIDE the sandbox** in a normal Terminal (sandbox blocks `~/Library/Application Support/com.vercel.cli/`):

```bash
cd /Users/Apple/Code/zc-ai-assistant

# Login (if not already) — uses browser OAuth
vercel login

# Link to a new project
vercel link --project monster-agent-frontend --scope jorshimayor

# Set backend URL (replace with YOUR Render URL from step 1c)
vercel env add NEXT_PUBLIC_API_BASE_URL
# paste: https://monster-agent-backend.onrender.com
vercel env add NEXT_PUBLIC_API_BASE_URL --environment production
vercel env add NEXT_PUBLIC_API_BASE_URL --environment preview

# Build + deploy production
vercel --prod
```

Output will print a URL like `https://monster-agent-frontend-xxxx.vercel.app`.

> **Paste that URL into Render `BACKEND_CORS_ORIGINS`** (Step 1b above), then Render → Manual Deploy.

### Smoke: CORS works?
Open DevTools → Network tab on the Vercel page → trigger an action. Look for:
- OPTIONS preflight: 204 + `access-control-allow-origin: <your vercel url>`
- GET / POST actual request: 2xx

---

## 3. [OPTIONAL] Cloudflare Pages + Hyperdrive

### 3a. Pages — deploy frontend there (Vercel alternative)
```bash
cd frontend
npm i -D wrangler@latest @cloudflare/next-on-pages
NEXT_PUBLIC_API_BASE_URL=https://monster-agent-backend.onrender.com npm run build
npx @cloudflare/next-on-pages
npx wrangler pages deploy .vercel/output/static --project-name monster-agent-frontend
```
Add the printed `*.pages.dev` URL to Render `BACKEND_CORS_ORIGINS`.

### 3b. Hyperdrive — cache Neon queries at the edge (10M q/mo FREE)
```bash
npx wrangler hyperdrive create monster-agent-neon \
  --connection-string "POST_POOLED_NEON_URL_HERE"
```
Paste the printed `HYPERDRIVE_ID` into `wrangler.jsonc` (already has comments).

---

## 4. Google Workspace — Calendar / Docs / Sheets / Gmail (10 minutes)

### Credential one-time setup:

1. https://console.cloud.google.com/ → new project (or reuse)
2. **APIs & Services → Enable APIs** — enable each:
   - Google Calendar API
   - Google Docs API
   - Google Sheets API
   - Google Drive API
   - Gmail API
3. **OAuth Consent Screen**:
   - User Type: **External** (for personal `@gmail.com`) | **Internal** (for Workspace domain)
   - Scopes → paste these 6:
     ```
     https://www.googleapis.com/auth/calendar
     https://www.googleapis.com/auth/documents
     https://www.googleapis.com/auth/spreadsheets
     https://www.googleapis.com/auth/drive.file
     https://www.googleapis.com/auth/gmail.send
     https://www.googleapis.com/auth/gmail.readonly
     ```
   - Test users → add `obafemijoshua2020@gmail.com` (or your Workspace email)
4. **Credentials → Create Credentials → OAuth client ID**
   - Application type: **Desktop app**
   - Download JSON → save as `backend/client_secret.json`

5. **Generate refresh_token** (run outside sandbox):
```bash
cd /Users/Apple/Code/zc-ai-assistant/backend
pip3 install --quiet google-auth-oauthlib google-auth-httplib2 google-api-python-client python-dotenv

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
print("\n>>> PASTE THESE 4 INTO RENDER ENVIRONMENT:")
print("GOOGLE_WORKSPACE_CLIENT_ID=       ", flow.client_config["client_id"])
print("GOOGLE_WORKSPACE_CLIENT_SECRET=   ", flow.client_config["client_secret"])
print("GOOGLE_WORKSPACE_REFRESH_TOKEN=   ", creds.refresh_token)
print("GOOGLE_WORKSPACE_SUBJECT_EMAIL=   <the email you authenticated as, e.g. obafemijoshua2020@gmail.com>")
PY
```

6. Paste the 4 printed values into:
   - Render → `monster-agent-backend` → Environment (see table in Step 1b)
   - Local `backend/.env` (for `poetry run uvicorn src.api.main:app`)

### Smoke test Google Workspace (direct client, no MCP subprocess needed):
```bash
cd backend
python3 <<'PY'
import asyncio, os, sys, pathlib
HERE = pathlib.Path(".").resolve()
sys.path.insert(0, str(HERE / "src"))
from dotenv import load_dotenv; load_dotenv(".env")
from src.mcp.servers.google_workspace import GoogleWorkspaceMcpServer
s = GoogleWorkspaceMcpServer(
    client_id=os.environ["GOOGLE_WORKSPACE_CLIENT_ID"],
    client_secret=os.environ["GOOGLE_WORKSPACE_CLIENT_SECRET"],
    refresh_token=os.environ["GOOGLE_WORKSPACE_REFRESH_TOKEN"],
    subject_email=os.environ["GOOGLE_WORKSPACE_SUBJECT_EMAIL"],
)
print("Exposed tools:", [t.name for t in s.exposed_tools()])
async def main():
    r = await s.invoke_direct("list_emails", {"max_results": 3})
    print("list_emails sample:", list(r.keys()) if isinstance(r, dict) else r[:1] if isinstance(r,list) else type(r).__name__)
asyncio.run(main())
PY
```

---

## 5. Production CORS finalization

Once you have both URLs:
```
Vercel:    https://monster-agent-frontend-xxxx.vercel.app
[opt] CF:  https://monster-agent-frontend-xxxx.pages.dev
Render:    https://monster-agent-backend.onrender.com
```

Set Render env **`BACKEND_CORS_ORIGINS`** to:
```json
["http://localhost:3000","http://localhost:8080","https://monster-agent-frontend-xxxx.vercel.app","https://monster-agent-frontend-xxxx.pages.dev"]
```

Save → Render triggers a redeploy (2 min).

---

## 6. You are production-ready. Use it.

| URL | What |
|---|---|
| `https://monster-agent-frontend-xxxx.vercel.app` | 🎯 **Main UI for you today** |
| `https://monster-agent-backend.onrender.com/api/health` | Backend health (should show `db_ok:true`) |
| `https://console.neon.tech/app/projects/super-rain-76741199` | Neon DB dashboard |
| `https://vercel.com/jorshimayor/monster-agent-frontend` | Vercel dashboard |
| `https://dashboard.render.com/web/...` | Render backend dashboard |

> **Render free idle workaround** → set UptimeRobot (free) to ping `/api/health` every 5 min.

---

## 7. Troubleshooting

| Symptom | Fix |
|---|---|
| Render deploy → `"cannot simultaneously specify value and sync"` in Blueprint | You're running an older Blueprint. Pull the latest `main` (this commit fixes it: `595f696`). |
| Render build → ModuleNotFoundError: `pybreaker`, `scikit-learn`… | Re-copy paste all 17 env vars; confirm `DATABASE_URL` starts with `postgresql+asyncpg://`; check `PYTHONUNBUFFERED=1`. |
| Neon → `SSL: CERTIFICATE_VERIFY_FAILED` on local macOS | DB engine already loads `certifi.where()` CA bundle — confirm `certifi` is installed. |
| Neon → `invalid input value for enum taskstatus` | Impossible now (column is TEXT + Python validator). Drop old `task_status_enum` PG type if it exists. |
| Vercel CLI → `err: value out of range (1)` when running `vercel link` | The sandbox blocks `~/Library/Application Support/com.vercel.cli/`. Run the vercel commands **outside sandbox** in a normal Terminal.app window. |
| Render Blueprint → `"repo is required for git-based services"` | Fixed in this Blueprint commit (added `repo:` field to `render.yaml`). |
| Google → `access_denied` on OAuth consent | Confirm you added the 6 scopes AND added your email to Test Users in the consent screen. |
| CORS error in browser → `No 'Access-Control-Allow-Origin' header` | Add your real Vercel/Pages URL to Render env `BACKEND_CORS_ORIGINS`. Save → triggers redeploy (2 min). |

---

## Appendix: Exposed Google Workspace tools

Your MCP backend exposes these 10 tools via `_DirectGoogleClient` (fallback, no subprocess required):

| Tool | Purpose |
|---|---|
| `create_doc(title, content, folder_id?)` | Create Google Doc with optional body |
| `read_doc(doc_id)` | Read full contents of a Google Doc |
| `append_to_doc(doc_id, content)` | Append text to end of a Google Doc |
| `read_calendar(time_min, time_max, calendar_id?=primary, max_results?=50)` | List calendar events in RFC3339 window |
| `create_calendar_event(summary, start_time, end_time, description?, attendees?, calendar_id?)` | Insert calendar event |
| `write_sheet(spreadsheet_id, range, values)` | Write 2D array to `Sheet1!A1:C10` style range |
| `read_sheet(spreadsheet_id, range)` | Read values from a Sheets range |
| **`send_email(to, subject, body_text, cc?, bcc?)`** | Send email via Gmail as `subject_email` |
| **`list_emails(max_results?=20, query?)`** | List Gmail messages (metadata: id, threadId, from, subject, date) |
| **`read_email(message_id, format?="full")`** | Read Gmail body (plain + html extracted) |

These are wired through the agent AND are callable directly via `await server.invoke_direct(tool_name, kwargs)` in Python.
