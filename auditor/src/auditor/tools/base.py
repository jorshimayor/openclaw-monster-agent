"""Running external tools.

Every wrapper goes through `run_tool`. No shell, so a path with a space or a
quote in it cannot become an argument; an explicit timeout, so a fuzzer cannot
hang a run; and the full stdout/stderr preserved, because the whole point of
these tools is that they are ground truth and a summary of ground truth is not.
"""

from __future__ import annotations

import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path


class ToolUnavailable(RuntimeError):
    """The tool is not installed. Distinct from the tool running and failing."""


@dataclass
class ToolRun:
    tool: str
    command: list[str]
    code: int
    stdout: str
    stderr: str
    seconds: float
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.code == 0 and not self.timed_out

    @property
    def command_line(self) -> str:
        return " ".join(self.command)


def which(tool: str) -> str | None:
    return shutil.which(tool)


def run_tool(
    command: list[str],
    *,
    cwd: Path | None = None,
    timeout: float = 600.0,
    env: dict[str, str] | None = None,
) -> ToolRun:
    binary = command[0]
    if which(binary) is None:
        raise ToolUnavailable(f"{binary} is not on PATH — see `auditor doctor`")

    started = time.monotonic()
    try:
        proc = subprocess.run(
            command,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            check=False,
        )
        return ToolRun(
            tool=binary,
            command=command,
            code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            seconds=time.monotonic() - started,
        )
    except subprocess.TimeoutExpired as exc:
        return ToolRun(
            tool=binary,
            command=command,
            code=-1,
            stdout=exc.stdout or "",
            stderr=(exc.stderr or "") + f"\ntimed out after {timeout}s",
            seconds=time.monotonic() - started,
            timed_out=True,
        )
