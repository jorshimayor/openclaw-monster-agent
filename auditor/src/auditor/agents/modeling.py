"""Phase 1 — the modeling agent.

Before anything can be broken it has to be understood: who acts, what they are
trusted with, and every path value can take through the system. Bugs live on
the money flows, so those are the part worth the reasoning model's time.
"""

from __future__ import annotations

from pathlib import Path

from ..gateway import Gateway
from ..schemas import SystemModel

SYSTEM = """You are the modeling agent in an auditing system. You do not look \
for bugs. You build an accurate model of what the code does, which a later \
agent will attack.

Be concrete and complete about:
- actors and roles, and which of them the protocol TRUSTS to behave
- state variables that represent value or authority
- every external call, because that is where control leaves the contract
- every money flow: how value enters, what it becomes, how it leaves

Return only JSON matching the requested schema."""


def read_sources(workspace: Path, limit_bytes: int = 220_000) -> str:
    """Contract sources, largest first, until the budget is spent.

    Truncation is reported in the text rather than silently swallowed, so the
    model is told what it has not seen instead of assuming it saw everything.
    """
    files = sorted(
        (p for p in workspace.rglob("*.sol") if not _is_noise(p, workspace)),
        key=lambda p: p.stat().st_size,
        reverse=True,
    )
    chunks, used, skipped = [], 0, []
    for path in files:
        text = path.read_text(errors="replace")
        rel = path.relative_to(workspace)
        if used + len(text) > limit_bytes:
            skipped.append(str(rel))
            continue
        chunks.append(f"// ===== {rel} =====\n{text}")
        used += len(text)
    if skipped:
        chunks.append(f"// NOT SHOWN ({len(skipped)} files over budget): {', '.join(skipped[:40])}")
    return "\n\n".join(chunks)


def _is_noise(path: Path, workspace: Path) -> bool:
    parts = set(path.relative_to(workspace).parts)
    return bool(parts & {"lib", "node_modules", "out", "cache", "test", "script", "mocks"})


def build_model(gateway: Gateway, workspace: Path) -> SystemModel:
    sources = read_sources(workspace)
    if not sources.strip():
        raise ValueError(f"no Solidity sources found under {workspace}")
    return gateway.complete(
        "reasoning",
        [
            {"role": "system", "content": SYSTEM},
            {
                "role": "user",
                "content": (
                    f"Model this protocol.\n\nJSON schema:\n"
                    f"{SystemModel.model_json_schema()}\n\nSOURCES:\n{sources}"
                ),
            },
        ],
        schema=SystemModel,
    )
