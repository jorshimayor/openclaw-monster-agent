# 11-Step Pipeline · Input / Process / Output / Failure

Each step with I → (P = pipeline state machine lives in `backend/src/orchestration/steps.py`. The `PipelineExecutor.run()` in `pipeline.py` calls them sequentially with cancellation checks in between.

---

## Step 1 · Complexity Check

**Input**: `Task.description`**

**Process**:
1. Count description character count.
2. Case-insensitive match against `_COMPLEX_KEYWORDS` set (compare, analyze, audit, research, synthesize, integrate, multiple, comprehensive, full, deep, thorough, complex, advanced, enterprise, production, scale, secure, security, strategy, roadmap, plan, report).
3. Decision:
   - `len(desc) > 250 **OR** keyword hits >= 2 → **MULTI_AGENT**
   - Else → **SINGLE_AGENT**

**Output**:
```
ComplexityState {
  complexity: "SINGLE_AGENT" | "MULTI_AGENT",
  complexity_reason: str,
  description_length: int,
  keyword_hits: int
}
```

**Failure Path**: Step1 cannot hard-fail (no exceptions). If logic throws unexpectedly → pipeline catches, logs, defaults `complexity: MULTI_AGENT`.

---

## Step 2 · Pattern Match

**Input**: `task_description: str`

**Process**:
Calls `patterns.match_pattern()` → tokenizes description, scores against `PATTERN_CONFIGS` keywords, returns pattern ID with confidence. Supported patterns in `patterns.WorkflowPattern` enum.

**Output**:
```
PatternMatchState {
  pattern_id: WorkflowPattern (e.g. "CONTENT_BRIEF, SECURITY_AUDIT, GENERIC...),
  confidence: 0.0..1.0,
  matched_keywords: List[str]
}
```

**Failure Path**: Any exception → defaults to `pattern_id: GENERIC`, `confidence: 0.0`. Pipeline continues.

---

## Step 3 · Experience Recall

**Input**: `pattern_id`, `task_description`, `ExperienceMemory`

**Process**:
`memory.recall(task_description, top_k=5, min_similarity=0.15)` — semantic similarity lookup against stored lessons.

**Output**:
```
ExperienceRecallState {
  lessons: List[str],           (up to 5),
  recalled_count: int
}
```

**Failure Path**: If `memory is None` (no memory component) OR exception → `lessons: [], recalled_count: 0, pipeline continues. Never aborts.

---

## Step 4 · Team Assembly

**Input**: `PatternConfig`, `experience_lessons[]`, `McpToolRegistry` (optional)

**Process**:
1. Iterate `pattern_config.agent_waves` (list of waves, each wave is list of AgentRole).
2. For each role: pick primary model from `AGENT_MODEL_MAP`, look up agent class → `tool_allowlist`.
3. If registry given → resolve `registry.get_tools_for_agent(allowlist)`.
4. Emits waves config + verifier role + review team.

**Output**:
```
TeamAssemblyState {
  agent_waves_cfg: List[List[agent_cfg]],    // agent_cfg = {role, model, tool_allowlist, tool_instances, wave_index}
  verifier_role: AgentRole,
  review_team: List[AgentRole],              // e.g. [EDITOR, SECURITY]
  total_agents: int
}
```

**Failure Path**: Exception → pipeline catches; falls back to a single `[ORCHESTRATOR]` wave, verifier=EDITOR, review_team=[].

---

## Step 5 · Prompt Injection

**Input**: `waves_cfg[]`, `shared_context{task_description, experience_lessons, pattern}`

**Process**:
1. For each agent in each wave:
   - Load agent SOUL (markdown persona from `backend/src/souls/<role>.md` via `_load_soul_for_role()`.
   - Concatenate: `SOUL + ROLE block + SHARED CONTEXT + EXPERIENCE LESSONS + TASK.
   - Embed the final `built_prompt`.

**Output**:
```
PromptInjectionState {
  agent_waves_with_prompts: List[List[agent_cfg + built_prompt]]
}
```

**Failure Path**: SOUL file missing / loader throws → generic `# SOUL: {role}` stub prompt. Hard error. Pipeline continues.

---

## Step 6 · Parallel Execution

**Input**: `waves_with_prompts[]`, `LLMRouter` (optional), `agent_factory` (optional)

**Process**:
For each wave in order (waves are sequential; agents inside a wave, parallel with `asyncio.gather(*coros, return_exceptions=True)`).
Per-agent call chain:
1. `agent_factory(role).invoke()` (if given) → else
2. `_lookup_agent_class(role) → Agent.invoke()` with LLM → else
3. Direct `llm.generate(prompt, role)` bare LLM call → else
4. Stub fallback.

Each `AgentResult{agent_role, output, confidence, errors[]}

**Output**:
```
ParallelExecutionState {
  wave_outputs: List[List[AgentResult]],
  all_outputs: List[AgentResult],          // flattened
  execution_seconds: float
}
```

**Failure Path**: Per-agent exceptions are caught by `return_exceptions=True` and wrapped as an `AgentResult(confidence=0.0, errors=[str(exc)])`. Pipeline never aborts on Step6.

---

## Step 7 · Verifier

**Input**: `outputs: List[AgentResult]`, `verifier_agent`, `LLMRouter`, `ttl_seconds=3600`, `confidence_threshold=0.7`

**Process**:
For each AgentResult:
1. Check **stale**: `created_at` < TTL boundary (if field present).
2. **confidence >= threshold** → pass.
3. **output length >= 30 chars**.
4. **errors empty**.
5. (Optional) verifier_agent LLM review → PASS/FAIL string parse.

Marks per output `{agent_role, passed, confidence, feedback, stale, original_output}`.

**Output**:
```
VerifierState {
  verified_outputs: List[verified_item],
  passed_count: int,
  failed_count: int
}
```

**Failure Path**: If verifier_agent review blows up → fall back to heuristics-only. No aborts. If everything is ambiguous → conservative (0.5 confidence default).

---

## Step 8 · P6 Quality Gate

**Input**: `verified_outputs[]`, `review_team_roles[]`, `LLMRouter`

**Process**:
1. `ratio = passed_count / total`.
2. Per review_team role: deterministic pseudo-score (base 0.5 + 0.3·ratio bounded 0..1).
3. `aggregate = ratio*0.6 + mean(review_scores)*0.4`.
4. `overall = aggregate >= 0.5 ? PASS : FAIL.
5. Partition: approved_outputs = items where passed=true; failed_outputs = rest.

**Output**:
```
QualityGateState {
  overall: "PASS" | "FAIL",
  aggregate_score: 0.0..1.0,
  review_scores: {role: score},
  approved_outputs: List[AgentResult],
  failed_outputs: List[verified_item]
}
```

**Failure Path**: Empty `verified_outputs[]` → overall=FAIL, aggregate=0.0. No exception. If Gate FAIL → Step9 kicked in by PipelineExecutor.

---

## Step 9 · Fix & Revalidate (single rework loop)

**Input**: `failed_outputs_with_feedback[]` (from Step8), agents, LLM, `single_rework=True`)

**Process**:
For each failed item:
1. Build rework prompt: `REWORK INSTRUCTIONS + FEEDBACK + PREVIOUS OUTPUT.
2. Call `llm.generate(prompt, role)` → reworked `AgentResult(confidence=0.65)`.

**Output**:
```
FixRevalidateState {
  reworked_outputs: List[AgentResult],
  stop_after: true,                       // only one rework allowed
  single_rework_performed: true
}
```

**Failure Path**: Exception per item → `AgentResult(output="[rework failed: ...]", confidence=0.0`. Pipeline continues; those stay failed. No infinite loops (single_rework=True → stop_after=true).

After Step9 the PipelineExecutor runs **Step7b**: re-verify reworked outputs. Passing reworks join approved_outputs. Still-failing reworks are logged + dropped. Merge approved + Step8-approved. Merged set → Step10.

---

## Step 10 · Synthesizer

**Input**: `approved_outputs[]`, `orchestrator_agent`, `LLMRouter`, `task_description`

**Process**:
1. Collect per-output section headers → `confidences{role: conf}`, `overall_conf = mean(confidences)`.
2. Build fallback combined report.
3. If orchestrator_agent given → invoke with combined + approved → overwrite final_report with LLM synthesis.
4. Always emits the final report (even empty).

**Output**:
```
SynthesizerState {
  final_report: str,
  confidence_ratings: {role: 0..1},
  overall_confidence: 0..1
}
```

**Failure Path**: ALWAYS SUCCEEDS. If no approved outputs → "(no approved outputs)" section; summary PARTIAL. Orchestrator exception → fallback to template report instead.

---

## Step 11 · Post-Task Reflection

**Input**: `final_output: str`, `Task`, `crystallizer_agent`, `LLMRouter`, `CrystallizedKnowledgeStore`, `ExperienceMemory`

**Process**:
1. `extractor.extract(final_output)` → KnowledgeCrystals (entities, strategies, pitfalls, frameworks).
2. If no extractor → crystallizer_agent LLM extraction → crystals.
3. `store.add(crystals)` → `saved_crystal_id`.
4. Build `lessons_lines` from crystals.
5. `memory.store(description, lessons_lines)`.

**Output**:
```
ReflectionState {
  saved_crystal_id: str | null,
  lessons_stored: List[str]
}
```

**Failure Path**: SILENT FAIL — any exception logged via `logger.exception(...)`; `PipelineExecutor catches; pipeline status still COMPLETED; Step11 failure never affects final_report or task status.

---

## Rework Loop Diagram

```
 Step7 (Verifier)
       │
       ▼
 Step8 (Quality Gate ───────────────────── PASS ──────────────────────┐
       │ FAIL                                            │
       └──────► Step9 (Fix & Revalidate, max=1)          │
                   │                                    │
                   ▼                                    │
              Step7b (Re-Verifier only reworked)        │
                   │                                    │
                   ├──── PASS → merge approved_outputs ◄───┘
                   │
                   └──── FAIL (still) → logged, dropped, partial)
                                        │
                                        ▼
                                   Step10 (Synthesizer)  [merges Step8-approved + Step7b-approved]
```
