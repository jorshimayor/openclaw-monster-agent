"""Every structured output the models produce, as a schema.

The guide's boundary caveat: tool-calling fidelity varies by provider, so
nothing is parsed out of prose. A model response either validates against one
of these or it counts as a failed call and the gateway falls through to the
next model.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class Vertical(StrEnum):
    STABLECOIN = "stablecoin"
    BRIDGE = "bridge"
    DEFI = "defi"
    LENDING = "lending"
    DLT = "dlt"


class Severity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# --- Phase 1: the system model -------------------------------------------

class Actor(BaseModel):
    name: str
    role: str
    trusted: bool = Field(description="Whether the protocol assumes this actor behaves")
    capabilities: list[str] = []


class MoneyFlow(BaseModel):
    """A path value can take through the system. Bugs live on these."""

    name: str
    entry: str = Field(description="Function value enters through")
    exit: str = Field(description="Function value leaves through")
    steps: list[str] = []
    external_calls: list[str] = []


class SystemModel(BaseModel):
    summary: str
    actors: list[Actor]
    state_variables: list[str]
    external_calls: list[str]
    money_flows: list[MoneyFlow]
    trust_assumptions: list[str]


# --- Phase 2: invariants and hypotheses ----------------------------------

class Invariant(BaseModel):
    """A property that must always hold, stated so it can be tested."""

    id: str
    statement: str = Field(description="What must always be true, in one sentence")
    testable_claim: str = Field(description="The assertion, as it would read in code")
    functions: list[str] = Field(description="Functions that could break it")
    vertical: Vertical | None = None
    crown_jewel: bool = Field(
        default=False,
        description="Worth the cost of formal verification if it survives fuzzing",
    )


class Hypothesis(BaseModel):
    """A proposed break. Not a finding — nothing is a finding without a proof."""

    id: str
    invariant_id: str
    claim: str
    attack_path: list[str]
    preconditions: list[str] = []
    economic_impact: str = ""
    suggested_layer: Literal["fuzz", "symbolic", "formal", "fork", "unit"] = "unit"


# --- Phase 3: the proof --------------------------------------------------

class Proof(BaseModel):
    """The output of the verification gate. `proven` is the only thing that matters."""

    hypothesis_id: str
    proven: bool
    layer: str
    test_source: str = ""
    command: str = ""
    output: str = ""
    attempts: int = 0
    discarded_because: str = ""


class Finding(BaseModel):
    """A reportable bug.

    Constructible only from a proof that passed — see `from_proof`. This class
    is where "no PoC, no finding" stops being advice and becomes a type error.
    """

    hypothesis: Hypothesis
    invariant: Invariant
    proof: Proof
    severity: Severity
    root_cause: str = ""
    suggested_fix: str = ""
    refutations: list[str] = []

    @classmethod
    def from_proof(
        cls,
        *,
        hypothesis: Hypothesis,
        invariant: Invariant,
        proof: Proof,
        severity: Severity,
        **extra: object,
    ) -> "Finding":
        if not proof.proven:
            raise ValueError(
                f"refusing to build a finding from an unproven hypothesis "
                f"({hypothesis.id}): {proof.discarded_because or 'no passing PoC'}"
            )
        return cls(
            hypothesis=hypothesis, invariant=invariant, proof=proof, severity=severity, **extra
        )


class Verdict(BaseModel):
    """One panel member's attempt to refute a finding."""

    model: str
    refuted: bool
    reasoning: str
