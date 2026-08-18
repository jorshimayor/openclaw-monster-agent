# Render Deployment · Monster Agent Backend

Deploy the Python FastAPI backend to Render's Free Tier.

## Setup

1. **Create a Render account** at [render.com](https://render.com/) (free).

2. **Create a Blueprint** from this repository:
   - Go to Render Dashboard → **Blueprints** → **New Blueprint Instance**.
   - Connect your GitHub / GitLab repo.
   - Set **Branch** to `main`.
   - Set **Blueprint File Path** to `deploy/render/render.yaml`.
   - Click **Apply**.

3. **Fill environment variables** in the Render dashboard:
   - After the Blueprint creates the service, go to the service → **Environment**.
   - Fill each secret token (click the eye icon to edit):
     - `NVIDIA_NIM_API_KEY` — https://build.nvidia.com/explore/discover
     - `GROQ_API_KEY` — https://console.groq.com/keys
     - `GOOGLE_API_KEY` — https://aistudio.google.com/app/apikey
     - `GITHUB_TOKEN` — https://github.com/settings/tokens (classic, `repo` scope)
     - `NOTION_TOKEN` — https://www.notion.so/my-integrations
     - `NOTION_DB_ID` — your Notion knowledge base DB ID
     - `SLACK_TOKEN` — https://api.slack.com/apps → Bot User OAuth Token
     - `SLACK_CHANNEL` — default `#agent-updates`
     - `GOOGLE_WORKSPACE_CLIENT_ID` / `GOOGLE_WORKSPACE_CLIENT_SECRET` — https://console.cloud.google.com/apis/credentials
     - `HASHNODE_TOKEN` / `HASHNODE_PUBLICATION_ID` — https://engineer.hashnode.com/settings/personal-access-tokens
   - Update `BACKEND_CORS_ORIGINS` to include your Vercel frontend domain once deployed.

4. **Verify**: Once deployed, open `https://<your-service>.onrender.com/api/health`. It should return `{"status":"ok"}`.

## Free Tier Notes

- Render Free Web Service: **512 MB RAM**, **750 hours / month** (sleeps after 15 min idle).
- Cold start after sleep ~10-30s. For production, upgrade to **Starter** ($7/mo) or **Pro**.
