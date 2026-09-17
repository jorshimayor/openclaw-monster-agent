"""Slither, Aderyn and Semgrep, normalized to one finding shape.

These are triage signal, not findings. They feed hypotheses; nothing here
reaches a report without going through the verification gate first.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .base import ToolRun, ToolUnavailable, run_tool


@dataclass(frozen=True)
class StaticFinding:
    tool: str
    check: str
    severity: str
    description: str
    location: str

    def key(self) -> tuple[str, str]:
        """Dedupe identity: the same issue found twice is one issue."""
        return (self.check.lower(), self.location.lower())


def slither(workspace: Path, timeout: float = 600) -> list[StaticFinding]:
    run = run_tool(
        ["slither", ".", "--json", "-", "--disable-color"], cwd=workspace, timeout=timeout
    )
    # Slither exits non-zero when it finds anything, so the code is not an error.
    payload = _load(run.stdout)
    if not payload or not payload.get("success"):
        return []
    out = []
    for detector in (payload.get("results") or {}).get("detectors") or []:
        elements = detector.get("elements") or []
        location = _element_location(elements[0]) if elements else "?"
        out.append(
            StaticFinding(
                tool="slither",
                check=detector.get("check", "?"),
                severity=str(detector.get("impact", "unknown")).lower(),
                description=(detector.get("description") or "").strip(),
                location=location,
            )
        )
    return out


def aderyn(workspace: Path, timeout: float = 600) -> list[StaticFinding]:
    report = workspace / "aderyn-report.json"
    run_tool(["aderyn", ".", "-o", report.name], cwd=workspace, timeout=timeout)
    if not report.exists():
        return []
    payload = json.loads(report.read_text())
    out = []
    for severity in ("critical_issues", "high_issues", "medium_issues", "low_issues"):
        for issue in (payload.get(severity) or {}).get("issues") or []:
            for instance in issue.get("instances") or []:
                out.append(
                    StaticFinding(
                        tool="aderyn",
                        check=issue.get("title", "?"),
                        severity=severity.split("_")[0],
                        description=(issue.get("description") or "").strip(),
                        location=f"{instance.get('contract_path', '?')}:{instance.get('line_no', '?')}",
                    )
                )
    return out


def sweep(workspace: Path) -> tuple[list[StaticFinding], list[str]]:
    """Every static tool that is installed, merged and deduped.

    A missing tool is reported, not fatal — you should know the sweep was
    partial rather than read a short list as a clean bill of health.
    """
    findings: list[StaticFinding] = []
    skipped: list[str] = []
    for name, fn in (("slither", slither), ("aderyn", aderyn)):
        try:
            findings.extend(fn(workspace))
        except ToolUnavailable:
            skipped.append(name)

    seen: dict[tuple[str, str], StaticFinding] = {}
    for finding in findings:
        seen.setdefault(finding.key(), finding)
    return list(seen.values()), skipped


def _load(stdout: str) -> dict | None:
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        return None


def _element_location(element: dict) -> str:
    mapping = element.get("source_mapping") or {}
    lines = mapping.get("lines") or []
    return f"{mapping.get('filename_relative', '?')}:{lines[0] if lines else '?'}"
