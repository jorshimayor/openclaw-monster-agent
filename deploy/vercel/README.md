# Monster Agent · Vercel Frontend Deployment

## Stack
- **Frontend**: Next.js 15 + React 19 (Turbopack) → **Vercel Hobby (FREE)**
- **Backend**: FastAPI (Python/Poetry) → **Render Free Tier Web Service** (or your own)
- **Database**: Postgres → **Neon Free Tier** (0.5 GB storage, 1 GB RAM, autoscales)
- **CDN/Edge**: Frontend automatically gets Vercel Edge Network; optionally put Cloudflare in front
- **DB Acceleration** (optional free): Cloudflare Hyperdrive in front of Neon (10M queries/mo free)

---

## 1. Frontend — Deploy to Vercel

```bash
# 1. Install Vercel CLI
npm i -g vercel

# 2. Login
vercel login

# 3. Link project (run from repo root)
vercel link --project monster-agent-frontend --scope jorshimayor

# 4. Configure env vars
vercel env add NEXT_PUBLIC_API_BASE_URL
#  → enter: https://monster-agent-backend.onrender.com  (your Render backend URL)
vercel env add NEXT_PUBLIC_API_BASE_URL --environment production
vercel env add NEXT_PUBLIC_API_BASE_URL --environment preview

# 5. Deploy (prod)
vercel --prod
```

The root-level [vercel.json](file:///Users/Apple/Code/zc-ai-assistant/vercel.json) configures:
```
framework:   nextjs
rootDir:     frontend
build:       npm run build
regions:     iad1 (N. Virginia — cheap + low-latency to Render Oregon)
```

### Free-tier limits
- 100 GB bandwidth/mo
- 6,000 Build Minutes / month
- Serverless Functions: 10s max duration (frontend API routes only; our Python backend lives on Render)
- Preview deployments: unlimited

---

## 2. Backend — Deploy to Render (Free)

Use the IaC blueprint at [render.yaml](file:///Users/Apple/Code/zc-ai-assistant/deploy/render/render.yaml):

1. Push `main` to GitHub
2. Render Dashboard → **Blueprints** → **New Blueprint Instance**
3. Select repo → branch `main` → pick `deploy/render/render.yaml`
4. Apply
5. Go to the new `monster-agent-backend` service → **Environment** → add the `sync: false` secrets
6. The service will auto-redeploy. Hit `https://monster-agent-backend.onrender.com/api/health` to verify.

### Idle cold-start workaround (free tier)
Render free web services spin down after 15 min idle. To keep them warm for "always-on" feel on the cheap:
- Use **UptimeRobot** (free) to ping `/api/health` every 5 minutes

---

## 3. Database — Neon (Free)

```bash
# Install neonctl
npm exec --yes neonctl@latest -- auth login        # browser OAuth → sign up / in

# Create project + branch
npm exec --yes neonctl@latest -- projects create monster-agent --region aws-us-east-2

# Get pooled DATABASE_URL (use pooled for serverless, direct for migrations)
npm exec --yes neonctl@latest -- connection-string --pooled
# → postgresql://...?sslmode=require&options=endpoint%3Dep-<pooler-id>

# Apply initial schema (via direct connection string)
npm exec --yes neonctl@latest -- connection-string
# → paste as DATABASE_URL in:
psql "$DIRECT_DATABASE_URL" -f backend/migrations/0001_initial_schema.sql
```

**Paste the pooled DATABASE_URL into Render → Environment → `DATABASE_URL`.**

### Neon Free Tier limits
- 0.5 GB storage
- 1 GB RAM per branch
- 10 active connections on shared compute
- Auto-suspend after 5 minutes idle (wakes in ~500 ms)
- Unlimited branches (great for staging/PR previews)

---

## 4. Cloudflare Acceleration (Optional, Free)

### Option A: Pages — deploy frontend there instead of Vercel
```bash
cd frontend
npm install
NEXT_PUBLIC_API_BASE_URL=https://backend.example.com npm run build
# Use @cloudflare/next-on-pages to adapt:
npx @cloudflare/next-on-pages
cd ..
npx wrangler pages deploy frontend/.vercel/output/static --project-name monster-agent-frontend
```

### Option B: Hyperdrive — accelerate Neon Postgres queries from edge functions
```bash
npx wrangler hyperdrive create monster-agent-neon \
  --connection-string "postgresql://user:pass@host.neon.tech/db?sslmode=require"
# → prints HYPERDRIVE_ID; add to wrangler.jsonc bindings
```

---

## 5. Google Workspace — Credential Setup

1. **Create project** → https://console.cloud.google.com/
2. **Enable APIs** (APIs & Services → Enable APIs):
   - Google Calendar API
   - Google Docs API
   - Google Sheets API
   - Google Drive API
   - Gmail API
3. **OAuth Consent Screen**:
   - User Type: Internal (Workspace) OR External (Testing mode for personal gmail)
   - Add scopes: `calendar`, `documents`, `spreadsheets`, `drive.file`, `gmail.send`, `gmail.readonly`
   - Add your email as test user (External mode only)
4. **Create OAuth Credentials** → Credentials → Create Credentials → OAuth client ID:
   - Application type: **Desktop app** (for local refresh-token generation)
   - Download JSON as `client_secret.json`
5. **Generate REFRESH_TOKEN**:
   ```bash
   cd backend
   poetry install
   poetry run python -c "
   from google_auth_oauthlib.flow import InstalledAppFlow
   SCOPES = [
       'https://www.googleapis.com/auth/calendar',
       'https://www.googleapis.com/auth/documents',
       'https://www.googleapis.com/auth/spreadsheets',
       'https://www.googleapis.com/auth/drive.file',
       'https://www.googleapis.com/auth/gmail.send',
       'https://www.googleapis.com/auth/gmail.readonly'
   ]
   flow = InstalledAppFlow.from_client_secrets_file('client_secret.json', SCOPES)
   creds = flow.run_local_server(port=0)
   print('CLIENT_ID:', flow.client_config['client_id'])
   print('CLIENT_SECRET:', flow.client_config['client_secret'])
   print('REFRESH_TOKEN:', creds.refresh_token)
   "
   ```
6. Paste into Render → Environment:
   - `GOOGLE_WORKSPACE_CLIENT_ID`
   - `GOOGLE_WORKSPACE_CLIENT_SECRET`
   - `GOOGLE_WORKSPACE_REFRESH_TOKEN`
   - `GOOGLE_WORKSPACE_SUBJECT_EMAIL` (the email you want to send/read mail as)

---

## 6. Production CORS

When you know your final frontend URLs, update Render env var `BACKEND_CORS_ORIGINS`:

```json
["http://localhost:3000","http://localhost:8080","https://<YOUR_VERCEL_APP>.vercel.app","https://<YOUR_CF_PAGES>.pages.dev","https://your-custom-domain.com"]
```

Then trigger a manual deploy (or push to `main`) in Render.
