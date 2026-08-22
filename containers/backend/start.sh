#!/usr/bin/env bash
set -euo pipefail

# Cloudflare Containers start script — launches uvicorn for FastAPI backend.
# All secrets come from the Worker's envVars block (see wrangler.jsonc for backend),
# which Cloudflare Containers inject as environment variables at container start.
#
# We also tolerate a .env file if someone mounts it locally (docker run),
# preferring existing env vars (Worker-injected) above .env contents.

if [ -f /.dockerenv ] && [ -f /app/.env ]; then
  set -a
  # shellcheck disable=SC1091
  source /app/.env
  set +a
fi

exec uvicorn src.api.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --workers 1 \
  --loop uvloop \
  --http h11 \
  --log-level info \
  --timeout-keep-alive 75 \
  --forwarded-allow-ips '*' \
  --proxy-headers
