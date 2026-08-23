# Monster Agent · Backend (Python / FastAPI)

## Local Dev Quick Start

### Requirements

- **Python 3.12** for the local `.venv` — this matches production (`python:3.12-slim`, see `containers/backend/Dockerfile`). `pyproject.toml` allows `^3.11`, but keep the venv on 3.12 so local behavior matches the container. Rebuild it with e.g. `uv venv --python 3.12 .venv && uv pip install --no-build -r requirements.txt pytest 'pytest-asyncio>=0.24,<0.25' 'respx==0.21.*'`.
- **poetry** (recommended) **OR** `pip`)

### Install

```bash
cd backend

# Option A: poetry
poetry install

# Option B: pip (editable install)
pip install -e .
```

### Configure

```bash
cp .env.example .env
# Open .env and fill each token (see docs/mcp_setup.md for each integration)
```

Required for basic usage (pipeline to just pipeline):

- At least **one** LLM key (`NVIDIA_NIM_API_KEY` **or** `GROQ_API_KEY` **or** `GOOGLE_API_KEY`).

### Run

```bash
cd backend
python3 -m uvicorn src.api.main:app --reload --port 8000
```

Server runs at **<http://localhost:8000>**.

### Health Check

```bash
curl http://localhost:8000/api/health
# {"status":"ok"}
```

### Test LLM Connectivity

```bash
curl -X POST http://localhost:8000/api/llm/test \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Hello Monster Agent"}'
```

Expected:

```json
{
  "provider": "groq",
  "model": "llama-3.1-8b-instant",
  "response": "... LLM reply ..."
}
```

If that provider fails check your keys — the fallback chain will try Groq then Gemini.

### Run Tests

```bash
pytest backend/tests -v
```

Run just unit tests:

```bash
pytest backend/tests/unit -v
```

Run just integration tests:

```bash
pytest backend/tests/integration -v
```

### Project Layout

```
backend/
├── src/
│   ├── agents/            # 8 agent classes + souls/ markdown personas
│   ├── api/             # FastAPI routes: main.py, routes/{tasks, agents knowledge mcp
│   ├── core/            # config.py types.py logging.py
│   ├── knowledge/       # memory (semantic lessons) + store (SQLite crystals) + extractor
│   ├── llm/            # router.py (LLMRouter + providers/ models
│   ├── mcp/            # registry.py manager.py servers/
│   ├── orchestration/  # pipeline.py PipelineExecutor + patterns.py steps.py graph_builder.py
│   └── souls/          # soul markdown per agent
└── tests/
    ├── unit/          # unit tests (orchestration llm knowledge mcp
    └── integration/  # mcp manager integration tests
```

