# Monster Agent · Backend on Cloudflare Containers
#
# Container image runs uvicorn with our FastAPI app, identical code to
# backend/src. Dockerfile is in this directory because wrangler containers
# expect the Dockerfile path (with optional ./ prefix) inside the repo tree.

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Install system libs for asyncpg wheels + Rust crypto (cryptography), curl for health,
# and Node.js + npm — the MCP servers (github/notion/slack/google_workspace) are spawned
# via `npx`; without node they all report "down" (verified in production via /api/mcp/doctor).
RUN apt-get update -y && \
    apt-get install -y --no-install-recommends build-essential libssl-dev pkg-config curl nodejs npm && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy pinned deps first for better cache layer hits
COPY backend/requirements.txt ./requirements.txt
RUN pip install --upgrade pip setuptools wheel && \
    pip install -r requirements.txt

# Copy the FastAPI source + container entrypoint start script
COPY backend/src/ ./src/
COPY containers/backend/start.sh ./start.sh
RUN chmod +x ./start.sh

# Default container port Cloudflare Containers Worker forwards to
EXPOSE 8000

CMD ["./start.sh"]
