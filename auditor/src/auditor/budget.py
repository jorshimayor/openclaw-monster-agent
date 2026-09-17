"""Step and cost caps.

Agents loop indefinitely on hard targets. Every stage draws from one budget,
and when it is gone the run stops rather than quietly continuing.
"""

from __future__ import annotations

from dataclasses import dataclass, field


class BudgetExhausted(RuntimeError):
    pass


@dataclass
class Budget:
    max_steps: int = 120
    max_usd: float = 10.0
    steps: int = 0
    usd: float = 0.0
    ledger: list[tuple[str, float]] = field(default_factory=list)

    def spend(self, stage: str, usd: float = 0.0) -> None:
        self.steps += 1
        self.usd += usd
        self.ledger.append((stage, usd))
        if self.steps > self.max_steps:
            raise BudgetExhausted(f"step cap reached ({self.max_steps}) during {stage}")
        if self.usd > self.max_usd:
            raise BudgetExhausted(f"cost cap reached (${self.max_usd:.2f}) during {stage}")

    @property
    def remaining_steps(self) -> int:
        return max(0, self.max_steps - self.steps)

    def summary(self) -> str:
        return f"{self.steps}/{self.max_steps} steps, ${self.usd:.3f}/${self.max_usd:.2f}"
