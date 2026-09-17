"""Phase 4 — the adversarial verifier panel.

Different architectures fail differently, so a finding that three of them
cannot refute is far likelier to be real. The panel's job is to attack the
finding, not to agree with it, and a majority refute kills it even though the
PoC passed — because a PoC can pass for the wrong reason.
"""

from __future__ import annotations

from ..gateway import Gateway, ModelsUnavailable
from ..schemas import Finding, Verdict

SYSTEM = """You are an adversarial reviewer. Your job is to REFUTE the finding \
you are shown, not to confirm it.

Refute it if any of these hold:
- the PoC passes for a reason other than the claimed bug (e.g. it asserts \
something trivially true, or sets up state no real caller could reach)
- the preconditions require privileges the trust model already grants
- the behaviour is intended and documented
- the impact claimed does not follow from the state reached

If you cannot refute it on those grounds, say so plainly.

Return only JSON: {"refuted": bool, "reasoning": "one paragraph"}"""


def review(gateway: Gateway, finding: Finding) -> list[Verdict]:
    verdicts: list[Verdict] = []
    for model in gateway.panel:
        prompt = (
            f"INVARIANT: {finding.invariant.statement}\n"
            f"CLAIM: {finding.hypothesis.claim}\n"
            f"ATTACK PATH: {' -> '.join(finding.hypothesis.attack_path)}\n\n"
            f"PASSING PoC:\n{finding.proof.test_source}\n\n"
            f"TEST OUTPUT:\n{finding.proof.output[-2000:]}"
        )
        try:
            verdict = gateway.complete(
                "reasoning",
                [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
                schema=Verdict,
                temperature=0.2,
            )
        except ModelsUnavailable:
            continue
        verdicts.append(Verdict(model=model, refuted=verdict.refuted, reasoning=verdict.reasoning))
    return verdicts


def survives(verdicts: list[Verdict]) -> bool:
    """A finding survives only on a clear minority refute.

    A tie kills it, and an empty panel is no panel rather than a pass. Both
    defaults point the same way: when the panel is unsure, the finding does not
    ship. A false positive sent to a program costs reputation; a false negative
    costs one bounty.
    """
    if not verdicts:
        return False
    refuted = sum(1 for v in verdicts if v.refuted)
    return refuted * 2 < len(verdicts)
