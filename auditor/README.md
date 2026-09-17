# auditor

An invariant-first, model-agnostic auditing agent for **authorized** web3 bounty
work. Scaffolds Phases 0–3 of the build guide, which is the part that has to
exist before any of the rest is worth building.

## The two rules that are code, not prompts

Everything else in here is replaceable. These two are the product.

**1. Nothing runs against an unauthorized target.** `scope.check_scope()` reads
`config/scope.yaml`, fails closed, and has no override flag. An entry must
record what authorizes it, and an expired entry is refused with the date it
ended. The pipeline calls it before it reads a single line of the target.

```
$ python -m auditor scope https://github.com/aave/aave-v3-core
REFUSED: not in scope. Add it to config/scope.yaml with the URL of the program
that authorizes testing it. There is no flag to skip this check.
```

**2. No PoC, no finding.** `Finding.from_proof()` raises unless the proof
passed. There is no other constructor path, so a hypothesis that could not be
turned into a compiling, passing Foundry exploit cannot reach a report no
matter how confident the model was about it. This is what removes most false
positives, and it is why the gate is a type error rather than an instruction.

## Getting started

```bash
pip install -r requirements-dev.txt
python -m auditor doctor          # what is installed, and what you lose without it
python -m auditor scope <target>  # is this authorized?
pytest
```

`doctor` is honest about a partial toolchain. A missing fuzzer does not raise —
it silently shrinks coverage, and a short findings list then reads like a clean
bill of health.

Then point the gateway at LiteLLM or OpenRouter and run against a practice
target, which the shipped scope file already authorizes:

```bash
export AUDITOR_GATEWAY_URL=http://localhost:4000      # or OpenRouter
export AUDITOR_GATEWAY_KEY=...
git clone https://github.com/theredguild/damn-vulnerable-defi targets/practice/dvd
python -m auditor audit targets/practice/dvd --vertical lending
```

## What runs

```
scope gate ─► static sweep ─► model ─► invariants ─► hypotheses ─► PoC GATE ─► panel ─► report
              (triage only)                                        (most die here)
```

| Stage | Module | Notes |
| --- | --- | --- |
| Authorization | `scope.py` | Fails closed. No override. |
| Static sweep | `tools/static_analysis.py` | Slither + Aderyn, normalized and deduped. Signal, never a finding. |
| System model | `agents/modeling.py` | Actors, trust, state, external calls, money flows. |
| Invariants | `agents/invariants.py` | Library invariants are kept as ground truth; the model adds protocol-specific ones. |
| Hypotheses | `agents/invariants.py` | Ranked so crown-jewel invariants reach the expensive gate first. |
| **Proof** | `agents/poc.py` | Writes a Foundry test, runs it, feeds failures back, up to N attempts. |
| Consensus | `agents/panel.py` | Multi-model refutation. A tie kills the finding. |

## The model layer

Agent code never names a provider. It calls `gateway.complete(stage=...)`, and
`config/model-policy.yaml` maps the stage to a primary model plus fallbacks.

The fallback chain triggers on transport failure, on an empty completion, **and
on output that fails schema validation** — the third being the one that matters.
JSON-mode fidelity varies by provider, so a model returning confident malformed
JSON is treated exactly like one returning a 500. Nothing downstream ever sees
prose where a structure was expected.

## The libraries

`src/auditor/knowledge/*.yaml` — the moat. Each invariant is written so it can
become an assertion rather than a topic, alongside the real exploits that broke
it. Lending is the deep one, as the guide's Phase 2 suggests; stablecoin,
bridge and DeFi are seeded and get their Phase 5 depth later.

## What is not built yet

Deliberately listed, so a gap is never mistaken for a pass:

- **Fuzzing, symbolic and formal layers.** `Proof.layer` exists and the
  hypothesis carries a `suggested_layer`, but only the unit/Foundry layer
  runs. Echidna, Medusa, Halmos, Certora and Kontrol are Phase 3 remainder.
- **Fork simulation and the economic-simulation agent.** Phase 5.
- **RAG over Solodit.** Hypotheses currently anchor on the hand-written
  libraries only.
- **The reporter.** `report.json` is machine output; the Immunefi-style
  writeup with severity, root cause and fix is Phase 4.
- **Regression eval harness.** Phase 6, and until it exists every prompt change
  is tuning blind.
- **The DLT lane.** The guide flags that non-EVM targets need different tooling
  entirely. Nothing here applies to them.
- **Severity.** Currently derived from whether the invariant was marked a crown
  jewel. That is a placeholder, not an impact assessment.

## Submitting

Don't, automatically. The CLI says so on every run and there is no submit
command. A human reviews everything before it goes to a program.
