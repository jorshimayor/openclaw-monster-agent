# Monster Agent · Architecture

## System Overview

```
┌───────────────────────────────────────────────────────────────────────┐
│                          Next.js Frontend                             │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌───────────────────┐  │
│  │ Tasks UI   │ │ Agents UI  │ │ Knowledge  │ │ Integrations UI   │  │
│  └─────┬──────┘ └─────┬──────┘ └─────┬──────┘ └────────┬──────────┘  │
│        └───────────────┴──────────────┴─────────────────┘             │
│                          │ SSE / REST /api                            │
└──────────────────────────┬────────────────────────────────────────────┘
                           ▼
┌───────────────────────────────────────────────────────────────────────┐
│                      FastAPI Backend (Python 3.11)                    │
│                                                                       │
│  ┌───────────────────────────────────────────────────────────────┐    │
│  │                    PipelineExecutor                            │    │
│  │  Step1 → Step2 → Step3 → Step4 → Step5 → Step6 → Step7       │    │
│  │                       → Step8 ──FAIL──┐                       │    │
│  │                          ▲ PASS        │                       │    │
│  │                          │             ▼                       │    │
│  │                      Step10 ←── Step9 ←── Step7b              │    │
│  │                          │                                     │    │
│  │                          ▼                                     │    │
│  │                       Step11 (reflection)                      │    │
│  └───────────────────────────────────────────────────────────────┘    │
│                           │                                           │
│            ┌──────────────┴──────────────┐                            │
│            ▼                             ▼                            │
│   ┌─────────────────┐          ┌──────────────────┐                   │
│   │  8 Agents Roster│          │    Graph Builder │                   │
│   │  (8 roles)      │          │  (DAG workflow)  │                   │
│   └────────┬────────┘          └────────┬─────────┘                   │
│            │                            │                             │
│            └──────────────┬─────────────┘                             │
│                           ▼                                           │
│                    ┌────────────────┐                                 │
│                    │   LLMRouter    │                                 │
│                    │  FallbackChain │                                 │
│                    └───────┬────────┘                                 │
│          ┌─────────────────┼───────────────────┐                     │
│          ▼                 ▼                   ▼                     │
│   NVIDIA NIM          Groq LPU          Google Gemini                 │
│   (DeepSeek V4)    (Llama 3.3 70B)    (2.0 Flash-Lite)                │
│                                                                       │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │                    MCP Server Manager                         │    │
│  │  ┌────────┐ ┌────────┐ ┌──────┐ ┌───────┐ ┌──────────────┐  │    │
│  │  │ GitHub │ │ Notion │ │Slack │ │Google │ │   Hashnode   │  │    │
│  │  │  MCP   │ │  MCP   │ │ MCP  │ │Workspace││    MCP      │  │    │
│  │  └────────┘ └────────┘ └──────┘ └───────┘ └──────────────┘  │    │
│  └──────────────────────────────────────────────────────────────┘    │
│                                                                       │
│  ┌────────────────────┐  ┌──────────────────────┐                    │
│  │ Experience Memory  │  │ Crystallized Knowledge│                    │
│  │ (semantic lessons) │  │     Store (SQLite)    │                    │
│  └────────────────────┘  └──────────────────────┘                    │
└───────────────────────────────────────────────────────────────────────┘
```

## 8 Agents Roster

| # | Agent Role            | Responsibility                                   | MCP Tools Access                        | Primary Model                          |
|---|-----------------------|--------------------------------------------------|-----------------------------------------|----------------------------------------|
| 1 | ORCHESTRATOR          | Task decomposition, wave planning, final synthesis | All MCP (coordinator)                  | nvidia/deepseek-v4-flash               |
| 2 | CONTENT_WEB2          | SEO articles, blog posts, social content, guides | Hashnode, Notion, Google Workspace     | nvidia/deepseek-v4-flash               |
| 3 | CONTENT_WEB3          | Web3 explainers, tokenomics, DeFi research, NFTs  | Hashnode, Notion, GitHub (for repos)   | nvidia/llama-3.1-nemotron-70b-instruct |
| 4 | FOOTBALL              | Match analysis, player scouting, tactics, fantasy  | Notion, Google Workspace (sheets)      | groq/llama-3.3-70b-versatile           |
| 5 | EDITOR                | Grammar, style, tone, fact-check, formatting       | Notion, Google Workspace (docs)        | google/gemini-2.0-flash-lite           |
| 6 | SECURITY              | Vulnerability audit, threat modeling, code review  | GitHub (scan repos), Notion            | nvidia/llama-3.1-nemotron-70b-instruct |
| 7 | KNOWLEDGE             | KnowledgeCrystal extraction, lesson distillation   | All (read-only for synthesis)          | google/gemini-2.0-flash-lite           |
| 8 | STUDY_PARTNER         | Study plans, flashcards, syllabus breakdown        | Notion (KB), Google Workspace          | groq/mixtral-8x7b-32768                |

## Request Flow

```
User request (Task description)
    │
    ▼
Next.js frontend (Tasks page)
    │  POST /api/tasks  SSE stream GET /api/tasks/{id}/stream
    ▼
FastAPI src/api/routes/tasks.py
    │
    ▼
PipelineExecutor.run(task)
    │
    ├── Step1  Complexity Check      → SINGLE | MULTI
    ├── Step2  Pattern Match         → pattern_id + confidence
    ├── Step3  Experience Recall     → lessons[] from ExperienceMemory
    ├── Step4  Team Assembly         → agent_waves + verifier + reviewers
    ├── Step5  Prompt Injection      → per-agent SOUL + context prompts
    ├── Step6  Parallel Execution    → AgentResult[] (asyncio.gather per wave)
    ├── Step7  Verifier              → passed/confidence/feedback/stale per output
    ├── Step8  P6 Quality Gate       → PASS | FAIL + aggregate_score
    │       │ FAIL
    │       └── Step9 Fix & Revalidate  → single rework loop
    │              │
    │              └── Step7b (re-Verifier) → approved_outputs
    ├── Step10 Synthesizer           → final_report + confidences
    └── Step11 Post-Task Reflection  → KnowledgeCrystal + lessons (silent fail)
    │
    ▼
Graph (DAG from graph_builder.py) coordinates agent waves
    │
    ▼
Agent.invoke() → tool_allowlist resolved via McpToolRegistry
    │
    ▼
LLMRouter.generate(role, prompt)
    │  per-agent AGENT_MODEL_MAP
    │  fallback order: nvidia_nim → groq → google_gemini
    ▼
(NVIDIA NIM | Groq | Google Gemini) + MCP Servers (tool calls)
```

## Module Dependency Graph

```
core/config ─────────────────────────────────────┐
    │                                            │
    ▼                                            │
core/types ────► core/logging                    │
    │                │                           │
    │                └─────────┐                 │
    ▼                          ▼                 ▼
llm/* ─────────────────► knowledge/*         mcp/*
  │  router              memory, store         registry, manager
  │  providers                │                    │
  │  models                   │                    │
  │                           │                    │
  └───────────┬───────────────┴───────┬────────────┘
              ▼                       ▼
          agents/*          orchestration/*
            base.py            pipeline.py (PipelineExecutor)
            <8 roles>          patterns.py, steps.py, graph_builder.py
              │                       │
              └───────────┬───────────┘
                          ▼
                       api/*
                     main.py, routes/*
```

Layers (from bottom to top, no cycles):
1. **core/** — config, Pydantic types, structured logging (no imports from sibling layers)
2. **llm/** — providers, router, model profiles → depends on core/*
3. **knowledge/** — memory (semantic recall), store (SQLite crystals) → depends on core/*
4. **mcp/** — tool registry, server manager, server wrappers → depends on core/*
5. **agents/** — 8 agent classes with souls + tool allowlists → depends on llm, knowledge, mcp
6. **orchestration/** — patterns, 11 steps, graph, PipelineExecutor → depends on all above
7. **api/** — FastAPI routes, SSE → depends on orchestration, agents, core

## LLM Fallback Chain (Provider Breakers)

```
┌─────────────────────┐
│   LLMRouter.call()  │
└──────────┬──────────┘
           ▼
┌──────────────────────────────────────────────────────────────┐
│  NVIDIA NIM  ──►  Groq LPU  ──►  Google Gemini               │
│  (primary)         (fallback 1)      (fallback 2)             │
│                                                               │
│  ┌────────────┐     ┌────────────┐     ┌────────────────┐    │
│  │ pybreaker  │     │ pybreaker  │     │   pybreaker    │    │
│  │ fail_max=5 │ OK? │ fail_max=5 │ OK? │   fail_max=5   │    │
│  │ reset=30s  │     │ reset=30s  │     │   reset=30s    │    │
│  └─────┬──────┘     └─────┬──────┘     └───────┬────────┘    │
│        │ FAIL              │ FAIL               │ FAIL        │
│        ▼                   ▼                    ▼             │
│  (try Groq)           (try Gemini)        LLMProviderError    │
└──────────────────────────────────────────────────────────────┘
```

Per-request: each model attempt also uses tenacity retry within the provider:
- `stop_after_attempt=3`
- `wait_exponential_jitter(multiplier=1, min=0.25, max=4.0)`

## Failure Modes & Recovery

| Failure Mode                     | Detection                    | Recovery Strategy                                          |
|----------------------------------|------------------------------|------------------------------------------------------------|
| LLM provider 5xx / timeout       | `LLMProviderError` raised    | Provider fallback chain (NVIDIA→Groq→Gemini) + circuit breaker opens after 5 consecutive failures for 30s |
| LLM provider 429 rate-limit      | 429 status in response       | Same as above — breaker opens, traffic rerouted to next provider |
| MCP transport crash (subprocess) | Manager heartbeat times out   | `McpServerManager` auto-restarts crashed server; pending calls re-queued once healthy |
| Pipeline Step8 Quality Gate FAIL | `aggregate_score < 0.5`      | Goto Step9 rework loop **once**; Step7b re-verifies reworked outputs; Step10 continues with merged approved + reworked-passing (partial) |
| Step9 rework still fails         | Step7b `passed=False`        | Log it; move on to Step10 with partial outputs (confidence reduced) |
| Step11 reflection error          | Any exception in step11      | Silent fail — logged; pipeline still `COMPLETED`; no impact on user-visible final_report |
| Agent wave exception (Step6)     | `asyncio.gather return_exc`  | Exception caught per-agent → AgentResult with `confidence=0.0`, `errors=[...]`; Step7 marks as FAIL |
