"""No PoC, no finding — enforced by the type, not by a prompt."""

import pytest

from auditor.schemas import Finding, Hypothesis, Invariant, Proof, Severity


def make(proven: bool, reason: str = "") -> Proof:
    return Proof(hypothesis_id="H1", proven=proven, layer="unit", discarded_because=reason)


HYP = Hypothesis(id="H1", invariant_id="LEND-01", claim="c", attack_path=["a"])
INV = Invariant(id="LEND-01", statement="s", testable_claim="t", functions=["borrow"])


def test_a_finding_cannot_be_built_from_an_unproven_hypothesis():
    with pytest.raises(ValueError, match="refusing to build a finding"):
        Finding.from_proof(
            hypothesis=HYP, invariant=INV,
            proof=make(False, "never compiled"), severity=Severity.HIGH,
        )


def test_the_refusal_says_why_it_was_discarded():
    with pytest.raises(ValueError, match="never compiled"):
        Finding.from_proof(
            hypothesis=HYP, invariant=INV,
            proof=make(False, "never compiled"), severity=Severity.HIGH,
        )


def test_a_proven_hypothesis_becomes_a_finding():
    finding = Finding.from_proof(
        hypothesis=HYP, invariant=INV, proof=make(True), severity=Severity.HIGH
    )
    assert finding.proof.proven
    assert finding.severity is Severity.HIGH
