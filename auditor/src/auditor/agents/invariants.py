"""Phase 2 — invariant synthesis and hypothesis generation.

The intellectual core. The specialist is a reasoning model plus its vertical
library: the library supplies properties that are known to matter, and the
model's job is to add the ones specific to this protocol and then say how each
might break.
"""

from __future__ import annotations

from pydantic import BaseModel

from ..gateway import Gateway
from ..schemas import Hypothesis, Invariant, SystemModel
from .library import Library

SYNTH_SYSTEM = """You are the invariant-synthesis agent. You write properties \
that must ALWAYS hold about this protocol.

A good invariant is falsifiable and points at code. "The protocol should be \
secure" is not an invariant. "totalBorrows + cash == totalSupplied - reserves" \
is. Every one you write must be something a Foundry assertion could check.

Start from the known library you are given, keep the ones that apply to this \
protocol, and add the ones specific to it that the library does not cover.

Return only JSON matching the requested schema."""

HYPOTH_SYSTEM = """You are a domain specialist. For each invariant you are \
given, propose concrete ways it could be broken in THIS code.

A hypothesis names a path: which function, called by whom, in what state, with \
what precondition. Do not propose a bug class; propose a sequence. If you \
cannot name the sequence, do not propose it — a later stage will try to write \
a working exploit for every one of these, and a vague hypothesis wastes that \
budget.

Return only JSON matching the requested schema."""


class _Invariants(BaseModel):
    invariants: list[Invariant]


class _Hypotheses(BaseModel):
    hypotheses: list[Hypothesis]


def synthesize(gateway: Gateway, model: SystemModel, library: Library) -> list[Invariant]:
    result = gateway.complete(
        "reasoning",
        [
            {"role": "system", "content": SYNTH_SYSTEM},
            {
                "role": "user",
                "content": (
                    f"{library.prompt_block()}\n\n"
                    f"SYSTEM MODEL:\n{model.model_dump_json(indent=2)}\n\n"
                    f"JSON schema:\n{_Invariants.model_json_schema()}"
                ),
            },
        ],
        schema=_Invariants,
    )
    # Library invariants are ground truth and are kept whether or not the model
    # echoed them back; the model's contribution is what it added.
    known = {inv.id for inv in library.invariants}
    return library.invariants + [i for i in result.invariants if i.id not in known]


def hypothesize(
    gateway: Gateway,
    model: SystemModel,
    invariants: list[Invariant],
    library: Library,
    static_summary: str = "",
) -> list[Hypothesis]:
    result = gateway.complete(
        "reasoning",
        [
            {"role": "system", "content": HYPOTH_SYSTEM},
            {
                "role": "user",
                "content": (
                    f"{library.prompt_block()}\n\n"
                    f"SYSTEM MODEL:\n{model.model_dump_json(indent=2)}\n\n"
                    "INVARIANTS TO ATTACK:\n"
                    + "\n".join(f"- {i.id}: {i.statement}" for i in invariants)
                    + (f"\n\nSTATIC TRIAGE SIGNAL (not findings):\n{static_summary}" if static_summary else "")
                    + f"\n\nJSON schema:\n{_Hypotheses.model_json_schema()}"
                ),
            },
        ],
        schema=_Hypotheses,
    )
    valid = {i.id for i in invariants}
    return [h for h in result.hypotheses if h.invariant_id in valid]
