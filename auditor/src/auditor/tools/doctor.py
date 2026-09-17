"""Is the toolchain actually here?

Phase 0's milestone is that every tool runs and emits machine-readable output.
A missing fuzzer does not raise — it silently shrinks coverage, and a short
findings list then reads like a clean bill of health. This is how you see it.
"""

from __future__ import annotations

from dataclasses import dataclass

from .base import run_tool, which

# (binary, version args, what you lose without it)
TOOLCHAIN = [
    ("forge", ["--version"], "every PoC — this one is not optional"),
    ("slither", ["--version"], "static triage signal"),
    ("aderyn", ["--version"], "second-opinion static analysis"),
    ("semgrep", ["--version"], "custom pattern rules"),
    ("echidna", ["--version"], "stateful fuzzing of invariants"),
    ("medusa", ["--version"], "parallel fuzzing"),
    ("halmos", ["--version"], "symbolic execution where fuzzing is inconclusive"),
    ("wake", ["--version"], "Ackee static analysis and fuzzing"),
]

REQUIRED = {"forge"}


@dataclass
class Doctor:
    tool: str
    installed: bool
    version: str
    required: bool
    lost: str

    @property
    def line(self) -> str:
        mark = "ok " if self.installed else ("MISSING" if self.required else "-  ")
        detail = self.version if self.installed else f"without it you lose {self.lost}"
        return f"{mark} {self.tool:<9} {detail}"


def check_toolchain() -> list[Doctor]:
    results = []
    for tool, args, lost in TOOLCHAIN:
        installed = which(tool) is not None
        version = ""
        if installed:
            run = run_tool([tool, *args], timeout=60)
            version = (run.stdout or run.stderr).strip().splitlines()[0] if run.stdout or run.stderr else "?"
        results.append(
            Doctor(
                tool=tool,
                installed=installed,
                version=version,
                required=tool in REQUIRED,
                lost=lost,
            )
        )
    return results
