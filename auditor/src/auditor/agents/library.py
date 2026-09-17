"""The per-vertical invariant libraries — the moat.

Generic prompting does not beat human auditors. What the specialists have that
a general model does not is this: a curated list of properties that must hold
in their vertical, and the real exploits that broke them.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from ..schemas import Invariant, Vertical

KNOWLEDGE = Path(__file__).resolve().parents[1] / "knowledge"


@dataclass(frozen=True)
class Library:
    vertical: Vertical
    invariants: list[Invariant]
    anchors: list[str]
    failure_modes: list[str]

    def prompt_block(self) -> str:
        """The library as the specialist sees it."""
        lines = [f"KNOWN INVARIANTS FOR {self.vertical.value.upper()}:"]
        for inv in self.invariants:
            star = " [crown jewel]" if inv.crown_jewel else ""
            lines.append(f"- {inv.id}{star}: {inv.statement}")
            lines.append(f"    assertion: {inv.testable_claim}")
            lines.append(f"    functions: {', '.join(inv.functions)}")
        lines.append("\nHISTORICAL BREAKS TO PATTERN-MATCH AGAINST:")
        lines += [f"- {a}" for a in self.anchors]
        lines.append("\nFAILURE MODES:")
        lines += [f"- {f}" for f in self.failure_modes]
        return "\n".join(lines)


def load_library(vertical: Vertical | str) -> Library:
    vertical = Vertical(vertical)
    path = KNOWLEDGE / f"{vertical.value}.yaml"
    if not path.exists():
        raise FileNotFoundError(
            f"no invariant library for {vertical.value!r}. Verticals with a library: "
            f"{', '.join(sorted(p.stem for p in KNOWLEDGE.glob('*.yaml')))}"
        )
    raw = yaml.safe_load(path.read_text())
    return Library(
        vertical=vertical,
        invariants=[
            Invariant(**{**inv, "vertical": vertical}) for inv in raw.get("invariants") or []
        ],
        anchors=list(raw.get("anchors") or []),
        failure_modes=list(raw.get("failure_modes") or []),
    )
