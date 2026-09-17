"""Foundry. The mechanics of every proof.

`run_test` returns the parsed --json output rather than the human log, because
whether a test passed is a fact and must not be re-derived by a model reading
prose.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .base import ToolRun, run_tool


@dataclass
class TestOutcome:
    passed: bool
    compiled: bool
    run: ToolRun
    failures: list[str]

    @property
    def feedback(self) -> str:
        """What the code model is shown when it has to try again."""
        if not self.compiled:
            return f"COMPILE ERROR\n{self.run.stderr[-4000:]}"
        if self.failures:
            return "TEST FAILED\n" + "\n".join(self.failures)[-4000:]
        return (self.run.stdout or self.run.stderr)[-4000:]


def build(workspace: Path, timeout: float = 600) -> ToolRun:
    return run_tool(["forge", "build"], cwd=workspace, timeout=timeout)


def run_test(workspace: Path, match_path: str, timeout: float = 900) -> TestOutcome:
    run = run_tool(
        ["forge", "test", "--match-path", match_path, "--json", "-vvv"],
        cwd=workspace,
        timeout=timeout,
    )

    # A compile failure produces no JSON at all; forge writes it to stderr.
    payload = _first_json_object(run.stdout)
    if payload is None:
        return TestOutcome(passed=False, compiled=False, run=run, failures=[])

    failures: list[str] = []
    total = 0
    for suite in payload.values():
        for name, result in (suite.get("test_results") or {}).items():
            total += 1
            if result.get("status") != "Success":
                reason = result.get("reason") or result.get("decoded_logs") or "failed"
                failures.append(f"{name}: {reason}")

    return TestOutcome(
        passed=total > 0 and not failures,
        compiled=True,
        run=run,
        failures=failures,
    )


def _first_json_object(stdout: str) -> dict | None:
    """forge prints build chatter before the JSON; take the first object that parses."""
    for line in stdout.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    return None
