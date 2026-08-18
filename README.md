# 🧭 OpenClaw — Monster Agent Orchestration Platform

> **8 specialised AI agents · 11-step deterministic pipeline · pluggable LLMs · pluggable MCP tools · open source (BSD-3).**
>
> Draft, verify, P6-quality-gate, rework, synthesise and crystallise long-running multi-agent tasks — with zero black-box magic. Every LLM call is routed through a provider-fallback circuit-breaker, every task is replayable, and every new lesson is stored in a crystallised knowledge base.

---

| Status | Badges |
|---|---|
| **Version** | `1.0.0` |
| **License** | BSD 3-Clause — see [LICENSE](LICENSE) |
| **Stack (backend)** | Python 3.11+ · FastAPI · Pydantic v2 · Tenacity · SQLite · httpx |
| **Stack (frontend)** | Next.js 15 LTS (15.5.23) · React 19 · TypeScript · Tailwind CSS |
| **Stack (MCP)** | TypeScript · `@modelcontextprotocol/sdk` 1.x · Node ≥ 18 |
| **LLM providers (baked in)** | NVIDIA NIM, Groq, Google Gemini (extensible) |
| **MCP integrations (baked in)** | GitHub, Notion, Google Workspace, Slack, Hashnode |

**Production-validated catalogue (August 2026).** Every model referenced in the default model map is live-verified:
- **Groq** `llama-3.1-8b-instant` → 560 tokens/s free-tier workhorse
- **Groq** `gpt-oss-120b` / `gpt-oss-20b` → reasoning-heavy security/editor
- **NVIDIA NIM** `meta/llama-3.1-70b-instruct` / `mistralai/mistral-nemo-12b-instruct` / `nvidia/llama-3.3-nemotron-super-49b-v1.5` → reasoning heavyweights
- Fallback chains = **4 model candidates per agent role**, each with a per-provider `SimpleCircuitBreaker(fail_max=10, reset=15s)`; model-specific 400 "decommissioned" errors are **not** counted as breaker trips.

---

## 🗂️ Repository layout

```
zc-ai-assistant/
├── backend/                          # FastAPI REST + LLM router + 11-step pipeline
│   ├── src/
│   │   ├── agents/                   # 8 agent classes (base.py + 7 specialists)
│   │   │   └── souls/                # Markdown "soul" prompts that define each agent's character
│   │   ├── api/                      # FastAPI routes: tasks · agents · knowledge · mcp
│   │   │   ├── routes/
│   │   │   └── main.py               # app entry + /api/health + /api/llm/test
│   │   ├── core/                     # Settings (config.py) · types · PrintLogger
│   │   ├── knowledge/                # CrystallizedKnowledgeStore (SQLite) + ExperienceMemory + extractor
│   │   ├── llm/
│   │   │   ├── router.py             # LLMRouter — provider fallback loop + circuit breaker
│   │   │   ├── models.py             # MODEL_PROFILES + AGENT_MODEL_MAP (8 roles × 4 models)
│   │   │   └── providers/            # nvidia_nim · groq · google_gemini
│   │   ├── mcp/                      # McpToolRegistry + McpServerManager + 5 server wrappers
│   │   └── orchestration/            # PipelineExecutor + patterns.py · steps.py · graph_builder.py
│   ├── tests/                        # unit + integration + e2e (pytest)
│   ├── api.http                      # 18-endpoint inventory for VS Code httpYac
│   ├── pyproject.toml                # Poetry deps
│   └── .env.example                  # All env keys, no secrets
│
├── frontend/                         # Next.js 15 (App Router) · Tailwind · Matrix theme
│   ├── src/app/                      # Routes: / · /tasks · /tasks/[id] · /knowledge · /agents · /integrations
│   ├── src/components/               # PipelineRail · LogPanel · dashboard cards · ui/ primitives
│   ├── src/lib/                      # api.ts · types · utils.ts · hydration.ts (SSR-safe dates)
│   └── .env.example
│
├── mcp-servers/hashnode/             # TypeScript standalone Hashnode MCP (draft/publish/read)
│
├── deploy/                           # Deployment recipes
│   ├── render/README.md + render.yaml        # Backend on Render
│   └── vercel/README.md + vercel.json        # Frontend on Vercel
│
├── docs/
│   ├── architecture.md
│   ├── 11_step_pipeline.md
│   ├── llm_fallback_chain.md
│   └── mcp_setup.md
│
├── scripts/verify_project.py
│
├── .gitignore                        # IDE/node_modules/.venv/.env/.trae — ALL secrets excluded
├── LICENSE (BSD-3)
└── README.md
```

---

## 🧬 Architecture at a glance

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          Next.js 15 Frontend (App Router)                   │
│   / (Dashboard) · /tasks · /tasks/[id] · /knowledge · /agents · /integrations│
└────────────────────────────┬────────────────────────────────────────────────┘
                             │ HTTP + SSE (tasks/[id]/stream)
                             ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    FastAPI Backend (uvicorn · Python 3.11+)                  │
│  ┌────────────┐  ┌──────────┐  ┌────────────┐  ┌─────────────┐               │
│  │ /api/tasks │  │ /agents/ │  │ /knowledge │  │   /mcp/*    │               │
│  │ create/list│  │ invoke/* │  │ list/query │  │ doctor/probe│               │
│  │ get/stream │  │ list/one │  │ sync/get/del│  │ list tools │               │
│  └─────┬──────┘  └────┬─────┘  └─────┬──────┘  └──────┬──────┘               │
│        │              │               │                  │                     │
│        ▼              ▼               ▼                  ▼                     │
│  ┌──────────────────────────────────────────────────────────────────┐         │
│  │ PipelineExecutor (orchestration/pipeline.py)                     │         │
│  │  1. complexity → 2. pattern → 3. experience → 4. team →         │         │
│  │  5. prompt → 6. parallel_execute → 7. verify → 8. P6 gate →     │         │
│  │  9. rework → 10. synthesize → 11. reflect/crystallize           │         │
│  └────────────┬─────────────────────────────────────────────────────┘         │
│               │                                                               │
│               ▼                                                               │
│  ┌──────────────────────┐   ┌──────────────────────────────┐                  │
│  │ 8 Specialised Agents │   │      LLMRouter               │                  │
│  │ ORCH·CW2·CW3·FB·ED·  │   │ AGENT_MODEL_MAP (role→4xLLM) │                  │
│  │ SEC·KNOW·STUDY       │   │ 3 providers · breaker(fail=10)│                  │
│  └──────────┬───────────┘   └─────┬────────────┬──────────┘                  │
│             │                     │            │                             │
│             ▼                     ▼            ▼                             │
│  ┌──────────────────┐   ┌────────────┐  ┌────────┐   ┌────────┐              │
│  │  MCP Tool Layer  │   │ NVIDIA NIM │  │  GROQ  │   │ GEMINI │              │
│  │ registry·manager │   │ 3 models   │  │4 models │   │ 1 slot │              │
│  │ 5 servers(wraps) │   └────────────┘  └────────┘   └────────┘              │
│  └────┬─────────────┘                                                        │
│       │                                                                      │
│       ▼                                                                      │
│  ┌──────────────────────────────────────────────────────┐                     │
│  │ Knowledge Layer                                      │                     │
│  │  CrystallizedKnowledgeStore(SQLite)  · categories    │                     │
│  │  ExperienceMemory (keyword-indexed lessons/frames)   │                     │
│  └──────────────────────────────────────────────────────┘                     │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 👥 8 × agent roster

Every agent is a Pydantic `Agent` subclass with a `model_profile` (first-choice pick from the catalog) and a `souls/*.md` prompt. The pipeline dispatches the right agent(s) per workflow pattern.

| # | Agent role | Default LLM #1 | What it does | Soul file |
|---|---|---|---|---|
| 1 | 🧭 **ORCHESTRATOR** | Groq `llama-3.1-8b-instant` (fast 560 tps) | Produces the 11-step plan for every task: complexity, pattern, experience, team, prompt, parallel-execute, verify, P6-gate, rework, synthesis, reflection targets. | `souls/orchestrator.md` |
| 2 | ✍️ **CONTENT_WEB2** | Groq `llama-3.1-8b-instant` | Blogs, tutorials, social threads. Voice: clear, evidence-based. | `souls/content_web2.md` |
| 3 | ⛓️ **CONTENT_WEB3** | Groq `gpt-oss-120b` (reasoning) | Web3 explainers, tokenomics, protocol analysis. Keeps fact-checking tight. | `souls/content_web3.md` |
| 4 | ⚽ **FOOTBALL** | Groq `llama-3.1-8b-instant` | xG, tactics, hot-takes-vs-data. Pulls MCP data when tools attached. | `souls/football_analyst.md` |
| 5 | 🛠️ **EDITOR** | Groq `llama-3.1-8b-instant` | P6 scoring rubric, line edits, structure rewrites, actionability fixes. **Called twice**: once after draft, once after rework. | `souls/editor_reviewer.md` |
| 6 | 🔬 **SECURITY** | Groq `gpt-oss-120b` | Solidity/Rust/JS code auditing, CVSS triage, severity-only condensed reports. | `souls/security_auditor.md` |
| 7 | 🧠 **KNOWLEDGE** | Groq `llama-3.1-8b-instant` | Runs the final step 11 *Crystallize*. Extracts entities, pitfalls, frameworks, strategies into SQLite. | `souls/knowledge_crystallizer.md` |
| 8 | 👤 **STUDY** | Groq `llama-3.1-8b-instant` | Long-form topic mastery: study plans, quizzes, active-recall frames, analogy generation. | `souls/study_partner.md` |

---

## 🪜 11 × step pipeline (always runs, always deterministic)

See [`docs/11_step_pipeline.md`](docs/11_step_pipeline.md) for verbatim output signatures and state shape. Short version:

| Step | Name | Owner | Output stored in Task.step_outputs |
|---|---|---|---|
| 1 | **Complexity classification** | Heuristic classifier (zero LLM) | `"SINGLE_AGENT" | "MULTI_AGENT" | "COMPLEX_MULTI_WAVE"` — based on length + keywords |
| 2 | **Pattern matching** | Heuristic keyword → WorkflowPattern enum | PatternMatchState(pattern_id, confidence, matched_keywords). LLM never runs here. |
| 3 | **Experience recall** | `ExperienceMemory` (keyword + category index) | Hypothetical prior lessons → injected into step 5 prompt. |
| 4 | **Team assembly** | Graph builder | Waves of agent instances + tool list + model picks. Deterministic by pattern. |
| 5 | **Prompt injection** | Role prompts + souls + pattern plan | Final LLM prompt template per agent. |
| 6 | **Parallel execution** | `asyncio.gather` per wave | 1..N × `AgentResult` (role, output, confidence, errors) |
| 7 | **Verifier** | Literal checks + EDITOR scoring pass | Pass/fail plus gap list. |
| 8 | **P6 quality gate** | 6-axis scoring (accuracy, structure, depth, tone, actionability) | Reject < threshold → rework, else → synthesize. |
| 9 | **Rework** (conditional) | Original agent + EDITOR gap list applied as diff | Second draft. Loop once, then escalate. |
| 10 | **Synthesizer** | ORCHESTRATOR | Unified report, citations, glossary. |
| 11 | **Reflection + crystallize** | STUDY (lessons) + KNOWLEDGE (SQLite insert) | Knowledge crystals + new entries in ExperienceMemory. |

---

## 🔌 Built-in MCP servers (Model Context Protocol)

All are **opt-in** — pipeline runs without them, but you get richer tool-use if you add the keys.
See [`docs/mcp_setup.md`](docs/mcp_setup.md) for token scopes + redirect URLs.

| MCP server | Tools | Category in `/api/mcp/doctor` |
|---|---|---|
| GitHub | Issues, PRs, file read, repo search | `github-mcp` |
| Notion | Page read/create, query db, block append | `notion-mcp` |
| Google Workspace | Drive file list, Docs read, Gmail send (optional scope) | `google-workspace-mcp` |
| Slack | Post message, list channels, search history | `slack-mcp` |
| Hashnode | Draft story, publish, read-by-tag (Node standalone in `mcp-servers/hashnode/`) | `hashnode-mcp` |

---

## 🌐 LLM provider catalogue (August 2026 verified)

See [`backend/src/llm/models.py`](backend/src/llm/models.py#L18-L68) for context window + cost-per-1k.

| Key | Provider | Model name | Context | Typical use |
|---|---|---|---|---|
| `nvidia/llama-3.1-70b-instruct` | NVIDIA NIM | `meta/llama-3.1-70b-instruct` | 131 072 | Fallback heavyweight #1 |
| `nvidia/mistral-nemo-12b-instruct` | NVIDIA NIM | `mistralai/mistral-nemo-12b-instruct` | 131 072 | Fast cheap mid-weight |
| `nvidia/nemotron-super-49b` | NVIDIA NIM | `nvidia/llama-3.3-nemotron-super-49b-v1.5` | 131 072 | Final 4th fallback (slowest, strongest) |
| `groq/llama-3.1-8b-instant` | Groq | `llama-3.1-8b-instant` | 131 072 | Workhorse #1 for all fast roles |
| `groq/llama-3.3-70b-versatile` | Groq | `llama-3.3-70b-versatile` | 131 072 | Strong generic reasoning |
| `groq/gpt-oss-120b` | Groq | `openai/gpt-oss-120b` | 131 072 | SECURITY / CONTENT_WEB3 |
| `groq/gpt-oss-20b` | Groq | `openai/gpt-oss-20b` | 131 072 | CONTENT_WEB2 / FOOTBALL / KNOWLEDGE / STUDY |
| `google/gemini-2.0-flash` | Google Gemini | `gemini-2.0-flash` | — | Optional 5th provider |

Every role maps to **exactly 4 model keys** in `AGENT_MODEL_MAP`, so a single dead model or breaker-open never leaves a role with zero candidates.

---

## 🚀 Quick start (3 terminals, 5 minutes)

### 0. Prerequisites

| Tool | Min version | Why |
|---|---|---|
| Python | 3.11+ (3.14 OK) | Backend runtime |
| Poetry **or** pip | 1.8+ / 24+ | Dependency install |
| Node.js | 20.9+ (for Next 15) | Frontend + Hashnode MCP |
| npm | 10+ | Frontend package manager |
| **At least one** API key | — | `NVIDIA_NIM_API_KEY` or `GROQ_API_KEY` or `GOOGLE_API_KEY` |

### 1. Backend

```bash
cd backend

# 1a. Install deps
#     Poetry (recommended):
poetry install
#     OR pip editable:
python3 -m venv .venv && source .venv/bin/activate && pip install -e .

# 1b. Environment
cp .env.example .env
#     …edit .env, paste at least one LLM key. MCP keys are optional.

# 1c. Run (auto-reload)
python3 -m uvicorn src.api.main:app --reload --port 8000
```

Smoke test the boot:

```bash
curl http://localhost:8000/api/health
# {"status":"ok"}

curl -X POST http://localhost:8000/api/llm/test \
  -H "Content-Type: application/json" \
  -d '{"prompt":"What is the capital of France? One sentence."}'
```

Expected: `{ "provider": "groq" | "nvidia_nim", "model": "…", "response": "…Paris." }` in < 15 s (Groq) or < 90 s (49B nemotron).

### 2. Frontend (Next.js 15 LTS)

Next 15 **defaults to Turbopack** in dev (faster HMR). No extra flag needed.

```bash
cd frontend

# 2a. Install
npm install
#   If you see ERESOLVE eslint peer conflicts (common when upgrading), use:
#   npm install --legacy-peer-deps

# 2b. Environment — point NEXT_PUBLIC backend URL
cp .env.example .env.local
#   .env.local contains:   NEXT_PUBLIC_API_BASE=http://localhost:8000

# 2c. Dev server
npm run dev
#   Visit http://localhost:3000
```

Optional production build to verify no regressions:
```bash
npm run build   # note: src/app/agents/page.tsx imports @/components/ui/dialog
                # which does not exist yet — omit that page from build or
                # add the dialog shadcn component; see docs for status.
```

### 3. (Optional) MCP servers

Only Hashnode is a **standalone** `mcp-servers/hashnode/` package. The other 4 MCPs are in-process Python wrappers (`backend/src/mcp/servers/*.py`) and start automatically if their env keys are present.

```bash
# Hashnode MCP (optional — standalone)
cd mcp-servers/hashnode
cp .env.example .env
#     paste HASHNODE_TOKEN + HASHNODE_PUBLICATION_ID
npm install && npm run build
npm start   # stdio transport — backend auto-launches via settings.MCP_HASHNODE_CMD
```

### 4. VS Code full-endpoint inventory

Open [`backend/api.http`](backend/api.http#L1-L367) in VS Code with the `anweber.vscode-httpyac` extension installed. It contains **18 requests** covering every route with realistic bodies. Walk them in order (1a → 2h → 5a) to validate end-to-end function:

| Region in `api.http` | Tests |
|---|---|
| 1a / 1b | Health + LLM probe |
| 1c / 1d | LLM short + large |
| 2a → 2g | Agents list + 6 invoke routes |
| 3a → 3g | Tasks: create · list · get · stream · cancel |
| 4a → 4e | Knowledge: list · query · sync · get · delete |
| 5a → 5e | MCP: doctor · 4 probes |

---

## 🧪 Tests

```bash
# Backend unit tests
cd backend
pytest tests/unit -v

# Integration (MCP manager, needs no keys)
pytest tests/integration -v

# E2E REST smoke (needs backend running on :8000)
pytest tests/e2e -v
```

Unit tests cover:
- `orchestration/steps.py`: complexity classifier · pattern matcher · team assembly
- `llm/router.py`: provider fallback ordering
- `mcp/hashnode_wrapper`: tool contract
- `knowledge/store_and_memory`: SQLite crystals round-trip

---

## 🛳️ Deployment

Recipes are fully written in [`deploy/`](deploy/README.md):

| Target | What's deployed | Recipe |
|---|---|---|
| **Render (backend)** | FastAPI on port 8000, auto-SSL, env from secrets panel | [`deploy/render/render.yaml`](deploy/render/render.yaml) |
| **Vercel (frontend)** | Next 15 App Router, env: `NEXT_PUBLIC_API_BASE` | [`deploy/vercel/vercel.json`](deploy/vercel/vercel.json) |
| Docker (self-host) | `docker compose up -d` → two services | See `deploy/README.md` |
| Fly.io / Railway | Adapt `deploy/render/render.yaml` procfile patterns | See `deploy/README.md` |

---

## 🪪 License

**BSD 3-Clause "New" or "Revised" License.** See [LICENSE](LICENSE). TL;DR:
- ✅ Commercial use OK
- ✅ Modification OK
- ✅ Distribution OK
- ✅ Private use OK
- ❌ Liability accepted by you only
- ❌ Don't use authors' names to endorse

## 🤝 Contributing

1. Fork → branch → commit.
2. Add a test when you add behaviour (pytest for backend, Vitest for MCP TypeScript).
3. Backend: ensure `py_compile` passes on all edited files + `pytest tests/unit`.
4. Frontend: run `npm run lint` and `npx tsc --noEmit`.
5. Open PR against `main`.

## 🛟 Support

Open a GitHub issue. Include:
- Backend version (`git rev-parse HEAD`)
- Which LLM provider(s) are configured
- Log snippet from uvicorn with the failing route path
- If frontend: browser + Next version

---

## 💡 Why "OpenClaw"?

A **claw** is the appendage a monster uses to grab and hold the problem. **Open** because every part of the grab-plan-execute-verify-crystallize loop is inspectable, replayable, and yours. No closed SaaS plan-step wrappers. No proprietary "agentic magic." You can read the 11 steps, map them to code, and swap any agent, any LLM, any MCP server, any knowledge store — without tearing out an orchestrator black box.

Enjoy it. Build monster things. 🧭
