# Vercel Deployment · Monster Agent Frontend

Deploy the Next.js command-center frontend to Vercel Hobby (free).

## Setup

1. **Import repo to Vercel**:
   - Go to [vercel.com/new](https://vercel.com/new).
   - Import your Monster Agent repo.

2. **Configure Project Settings**:
   - In **Project Settings → General → Root Directory**, set it to `./frontend`.
   - Framework Preset should auto-detect **Next.js**.

3. **Set environment variables**:
   - Go to **Project Settings → Environment Variables**.
   - Add:
     - `NEXT_PUBLIC_API_BASE_URL` = your Render backend URL, e.g. `https://monster-agent-backend.onrender.com`
   - Redeploy after adding env vars.

4. **Deploy**: Click **Deploy**. Vercel will build the Next.js app and give you a `*.vercel.app` domain.

## Troubleshooting CORS

If you see CORS errors in the browser console:
- Copy your Vercel app domain (e.g. `https://monster-agent.vercel.app`).
- Go to Render → backend service → **Environment** → `BACKEND_CORS_ORIGINS`.
- Append the domain to the JSON array:
  ```
  ["http://localhost:3000","http://localhost:8080","https://monster-agent.vercel.app"]
  ```
- Save and **Manual Deploy** the backend to pick up the change.
