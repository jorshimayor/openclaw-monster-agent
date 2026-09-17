"""Phase 3 — the verification gate. The crux of the whole system.

Everything upstream produces hypotheses, which are guesses. This module is the
only thing that converts a guess into a finding, and it does so on one
condition: a Foundry test that compiles and passes, where passing means the
invariant actually broke.

The rule is enforced here and in `Finding.from_proof`, not in a prompt. A model
cannot talk its way past a red test.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ..gateway import Gateway, ModelsUnavailable
from ..schemas import Hypothesis, Invariant, Proof, SystemModel
from ..tools import forge

SYSTEM = """You write Foundry proof-of-concept exploits.

Rules:
- Output ONE complete Solidity file and nothing else. No prose, no fences.
- pragma solidity ^0.8.20; import "forge-std/Test.sol";
- The contract name must match the file name you are given.
- The test must FAIL LOUDLY if the bug is absent and PASS only when the \
invariant is genuinely broken. Assert the broken state at the end — do not \
write a test that passes because nothing reverted.
- Use only what exists in the sources you were shown. Do not invent functions.
- If you are given failure output from a previous attempt, fix that specific \
error. Do not restructure the test."""


@dataclass
class ProofAttempt:
    source: str
    outcome: forge.TestOutcome


def _extract_solidity(content: str) -> str:
    """Models fence code even when told not to. Take the file, drop the chatter."""
    fenced = re.search(r"```(?:solidity|sol)?\s*(.*?)```", content, re.S)
    text = fenced.group(1) if fenced else content
    start = text.find("// SPDX")
    if start == -1:
        start = text.find("pragma solidity")
    return text[start:].strip() if start != -1 else text.strip()


def prove(
    gateway: Gateway,
    workspace: Path,
    hypothesis: Hypothesis,
    invariant: Invariant,
    model: SystemModel,
    *,
    max_attempts: int = 4,
) -> Proof:
    """Try to break `invariant` the way `hypothesis` claims. Return the verdict.

    A proof that never compiles, never passes, or runs out of attempts is
    discarded — which is the point. Most hypotheses die here, and that is the
    mechanism that keeps the report worth reading.
    """
    test_name = f"PoC_{re.sub(r'[^A-Za-z0-9]', '_', hypothesis.id)}"
    test_path = workspace / "test" / f"{test_name}.t.sol"
    test_path.parent.mkdir(parents=True, exist_ok=True)

    sources = _relevant_sources(workspace, invariant.functions)
    history: list[ProofAttempt] = []

    for attempt in range(1, max_attempts + 1):
        messages = [
            {"role": "system", "content": SYSTEM},
            {
                "role": "user",
                "content": (
                    f"File name: {test_name}.t.sol (contract {test_name})\n\n"
                    f"INVARIANT TO BREAK — {invariant.id}: {invariant.statement}\n"
                    f"assertion: {invariant.testable_claim}\n\n"
                    f"HYPOTHESIS: {hypothesis.claim}\n"
                    f"attack path: {' -> '.join(hypothesis.attack_path)}\n"
                    f"preconditions: {'; '.join(hypothesis.preconditions) or 'none stated'}\n\n"
                    f"PROTOCOL SUMMARY: {model.summary}\n\n"
                    f"SOURCES:\n{sources}"
                ),
            },
        ]
        if history:
            last = history[-1]
            messages.append({"role": "assistant", "content": last.source})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"That attempt did not prove the bug (attempt {attempt - 1} of "
                        f"{max_attempts}). Fix this and return the whole file again:\n\n"
                        f"{last.outcome.feedback}"
                    ),
                }
            )

        try:
            content = gateway.complete("poc_writing", messages)
        except ModelsUnavailable as exc:
            return Proof(
                hypothesis_id=hypothesis.id,
                proven=False,
                layer="unit",
                attempts=attempt - 1,
                discarded_because=f"no model could write the PoC: {exc}",
            )

        source = _extract_solidity(str(content))
        test_path.write_text(source)
        outcome = forge.run_test(workspace, match_path=f"test/{test_name}.t.sol")
        history.append(ProofAttempt(source=source, outcome=outcome))

        if outcome.passed:
            return Proof(
                hypothesis_id=hypothesis.id,
                proven=True,
                layer="unit",
                test_source=source,
                command=outcome.run.command_line,
                output=outcome.run.stdout[-6000:],
                attempts=attempt,
            )

    # Out of attempts. Leave the last test on disk so a human can look at it,
    # but the hypothesis is dead as far as the pipeline is concerned.
    last = history[-1]
    return Proof(
        hypothesis_id=hypothesis.id,
        proven=False,
        layer="unit",
        test_source=last.source,
        command=last.outcome.run.command_line,
        output=last.outcome.feedback,
        attempts=max_attempts,
        discarded_because=(
            "no passing PoC after "
            f"{max_attempts} attempts ({'never compiled' if not last.outcome.compiled else 'exploit did not hold'})"
        ),
    )


def _relevant_sources(workspace: Path, functions: list[str], limit_bytes: int = 120_000) -> str:
    """Files mentioning the functions at issue first, then the rest until full."""
    files = [p for p in workspace.rglob("*.sol") if "lib" not in p.parts and "out" not in p.parts]
    scored = []
    for path in files:
        try:
            text = path.read_text(errors="replace")
        except OSError:
            continue
        hits = sum(1 for fn in functions if fn and fn in text)
        scored.append((hits, -len(text), path, text))
    scored.sort(reverse=True)

    chunks, used = [], 0
    for _, _, path, text in scored:
        if used + len(text) > limit_bytes:
            continue
        chunks.append(f"// ===== {path.relative_to(workspace)} =====\n{text}")
        used += len(text)
    return "\n\n".join(chunks)
