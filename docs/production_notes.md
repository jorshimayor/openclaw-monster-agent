# Production Notes — studied & tested 23 Aug 2026

> **Round 2 addendum (same day):** tasks now persist to Neon Postgres.
> Findings and fixes:
> - **DB layer was silently dead in production.** `create_async_engine`
>   refuses the bare `postgresql://` scheme; `init_db` swallowed the error,
>   so `is_db_available()` was False and nothing ever wrote to Neon (the
>   `tasks` table only existed from a hand-run migration).
>   `normalize_database_url()` now forces `postgresql+asyncpg://` and strips
>   libpq-only params (`sslmode`, `channel_binding`) — with regression tests.
> - **`/api/health/diag` lied**: `tasks_table_created` was computed from
>   logger+executor presence. Replaced with `engine_initialized` =
>   `is_db_available()`.
> - **Task persistence implemented** (`src/core/task_repo.py`): write-through
>   on create/every pipeline event/terminal state; GET falls back to
>   Postgres; list merges Postgres + in-memory. Best-effort by design — a
>   Neon hiccup can't kill a pipeline.
> - **All 9 agents tested live**: personal_assistant, orchestrator, editor,
>   football, knowledge, security, content_web3 verified end-to-end;
>   content_web2 + study overran the 180 s default route timeout on long
>   generations → both bumped to 240 s (matching content_web3).
> - **Test suite: 43 passing / 10 failing+erroring → 80 passing / 0
>   failing** across unit + integration + e2e (fixed: un-awaited async store
>   calls, wrong patch targets, a graph model that contradicted the real
>   bounded-rework flow, a schema test asserting the opposite of the model,
>   a cancel-race, stale 8-agent expectations, and the mocked-spawn fake
>   that died instantly under the liveness gate).

What the deployed system actually is, what was broken, what got fixed, and
what is still known-weak. Written after a live production test campaign
(task pipeline runs against monster-agent-backend.joelobafemii.workers.dev).

## Architecture reality

```
Cloudflare Worker (backend-worker/src/index.ts, ~140 lines)
  └─ routes ALL traffic to ONE named Cloudflare Container instance
       └─ Docker: python:3.12-slim + uvicorn + FastAPI (backend/src)
            ├─ 9 agents, 11-step pipeline, LLM router (NIM → Groq fallback)
            ├─ task state: IN-MEMORY dict (_TASK_STORE)  ← biggest weakness
            ├─ knowledge crystals: persisted store (survives)
            └─ MCP servers spawned via npx (needs node in the image)
Frontend: Next.js on Cloudflare Pages
```

## Verified working in production (23 Aug 2026)

- `/api/health` → ok; `/api/llm/test` → NVIDIA NIM `llama-3.1-70b`, 1.3 s
- 9 agents listed; knowledge store read/write
- **Full 11-step pipeline: COMPLETED.** Real task (weekly season-plan brief),
  ~150 s execution, quality gate 0.904, 15 KB synthesized report, 2
  knowledge crystals extracted. Steps observed:
  complexity → pattern → experience → team → prompt → execution → verifier
  → quality_gate → synthesizer → reflection.

## Bugs found & fixed (all verified by test)

1. **Random routing across 2 stateful containers** — `getRandom(ns, 2)` +
   in-memory task store made the same task id alternate 200/404 (verified:
   `404 200 404 200 404 404`). Fixed: single named instance via
   `getContainer(ns, "backend-primary")`; env vars now injected via the
   supported `this.envVars` constructor pattern. After fix: 10/10 200s.
2. **`'dict' object has no attribute 'confidence'`** — pipeline steps return
   `state.model_dump()`, so step 10 (and step 9's rework path) received
   dicts and crashed after the quality gate. Fixed: shared
   `ensure_agent_results()` normalizer applied at every consumer boundary
   (steps 7, 9, 10).
3. **`'str' object has no attribute 'value'`** — `AgentResult` uses
   `use_enum_values=True`, so `agent_role` is a plain string; all
   `.agent_role.value` accesses (step 10 ×2, step 9 ×2, step 11
   crystallizer) crashed. Fixed: `role_str()` helper.
4. **MCP servers all down** — they spawn via `npx`, but the image had no
   Node.js. Fixed: node + npm added to the Dockerfile.

Unit tests: 43 → 45 passing after fixes (two previously-failing tests,
including the 11-step end-to-end, now pass; nothing regressed).

## Known-weak (current, honest)

- **A deploy or sleep still interrupts an in-flight pipeline run** — the
  task row survives in Postgres (status shows where it stopped) but the run
  itself doesn't resume. Resumable pipelines would need step-level
  checkpointing.
- SSE streaming only works while the run's container holds the task in
  memory (by design; the durable record is Postgres).
- google_workspace MCP server still down (its own OAuth config, not the
  platform).
- apt's Node is v20 via bookworm; fine for MCP SDK, pin nodesource if a
  server ever needs newer.
- Cold starts: first request after idle boots the container (~30–60 s);
  first deploy rollout takes ~3–4 min before new code serves.

## Ops crib

```sh
cd backend-worker
npm run deploy          # rebuilds image + deploys worker
npm run tail            # live logs
npx wrangler secret list
curl https://monster-agent-backend.joelobafemii.workers.dev/api/health
curl https://monster-agent-backend.joelobafemii.workers.dev/api/mcp/doctor
```

## Season-plan integration

`docs/private-sot` (symlink → chelsea_bot/docs/private, never committed)
holds the career plan + season calendar. A launchd job
(`com.bridgways.weekbrief`, Mon 08:00) runs `weekly_brief.sh`: macOS
notification + creates an OpenClaw task from the week's calendar row + logs
to `briefs/`. The pipeline turns the row into a 5-day execution plan.
