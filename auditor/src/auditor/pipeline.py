"""The orchestrator.

Hand-rolled rather than LangGraph: the state here is small enough that an
explicit loop is easier to read than a graph, and every stage is resumable
because the artefacts are written to disk as they are produced. Swap in
LangGraph when audits get long enough that checkpointing earns its dependency.

The order is the guide's: model, synthesize, hypothesize, verify, consensus,
report. The only step that can create a finding is verify.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .budget import Budget, BudgetExhausted
from .gateway import Gateway
from .schemas import Finding, Hypothesis, Invariant, Severity, SystemModel, Vertical
from .scope import Allowed, check_scope
from .tools import static_analysis
from .agents import invariants as invariants_agent
from .agents import modeling, panel, poc
from .agents.library import load_library


@dataclass
class AuditReport:
    target: str
    vertical: Vertical
    authorization: str
    started: str
    model: SystemModel | None = None
    invariants: list[Invariant] = field(default_factory=list)
    hypotheses: list[Hypothesis] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    discarded: list[dict] = field(default_factory=list)
    static_skipped: list[str] = field(default_factory=list)
    stopped_early: str = ""
    budget: str = ""

    def to_json(self) -> str:
        return json.dumps(
            {
                "target": self.target,
                "vertical": self.vertical.value,
                "authorization": self.authorization,
                "started": self.started,
                "budget": self.budget,
                "stopped_early": self.stopped_early,
                "static_skipped": self.static_skipped,
                "counts": {
                    "invariants": len(self.invariants),
                    "hypotheses": len(self.hypotheses),
                    "proven": len(self.findings),
                    "discarded": len(self.discarded),
                },
                "findings": [f.model_dump(mode="json") for f in self.findings],
                "discarded": self.discarded,
            },
            indent=2,
        )


def audit(
    target: str,
    vertical: Vertical | str,
    *,
    workspace: Path | None = None,
    budget: Budget | None = None,
    max_hypotheses: int = 12,
    out_dir: Path | None = None,
) -> AuditReport:
    # 1. Authorization, before anything reads the code.
    allowed: Allowed = check_scope(target)

    workspace = (workspace or Path(target)).resolve()
    vertical = Vertical(vertical)
    budget = budget or Budget()
    gateway = Gateway(budget=budget)
    library = load_library(vertical)

    report = AuditReport(
        target=target,
        vertical=vertical,
        authorization=f"{allowed.program.name} — {allowed.program.authorization} ({allowed.matched_on})",
        started=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )

    try:
        # 2. Static sweep. Triage signal only — never a finding on its own.
        static, skipped = static_analysis.sweep(workspace)
        report.static_skipped = skipped
        static_summary = "\n".join(
            f"- [{f.tool}/{f.severity}] {f.check} at {f.location}" for f in static[:60]
        )

        # 3. Model the protocol.
        report.model = modeling.build_model(gateway, workspace)

        # 4. Invariants, seeded by the vertical library.
        report.invariants = invariants_agent.synthesize(gateway, report.model, library)

        # 5. Hypotheses, ranked so the expensive gate sees the best first.
        hypotheses = invariants_agent.hypothesize(
            gateway, report.model, report.invariants, library, static_summary
        )
        by_id = {i.id: i for i in report.invariants}
        hypotheses.sort(key=lambda h: (not by_id[h.invariant_id].crown_jewel, h.id))
        report.hypotheses = hypotheses[:max_hypotheses]

        # 6. The gate. This is the only step that can produce a finding.
        for hypothesis in report.hypotheses:
            invariant = by_id[hypothesis.invariant_id]
            proof = poc.prove(gateway, workspace, hypothesis, invariant, report.model)
            if not proof.proven:
                report.discarded.append(
                    {"hypothesis": hypothesis.id, "reason": proof.discarded_because}
                )
                continue

            finding = Finding.from_proof(
                hypothesis=hypothesis,
                invariant=invariant,
                proof=proof,
                severity=Severity.HIGH if invariant.crown_jewel else Severity.MEDIUM,
            )

            # 7. Consensus. A passing PoC can still pass for the wrong reason.
            verdicts = panel.review(gateway, finding)
            if not panel.survives(verdicts):
                report.discarded.append(
                    {
                        "hypothesis": hypothesis.id,
                        "reason": "refuted by the verifier panel despite a passing PoC",
                        "verdicts": [v.model_dump() for v in verdicts],
                    }
                )
                continue
            finding.refutations = [v.reasoning for v in verdicts if v.refuted]
            report.findings.append(finding)

    except BudgetExhausted as exc:
        report.stopped_early = str(exc)

    report.budget = budget.summary()

    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "report.json").write_text(report.to_json())
    return report
