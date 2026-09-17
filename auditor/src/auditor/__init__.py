"""An invariant-first, model-agnostic auditing agent for authorized web3 bounty work.

Two rules hold the system up, and both are code rather than prompts:

  scope.check_scope   — nothing runs against a target that is not authorized
  schemas.Finding     — nothing becomes a finding without a passing PoC
"""

from .budget import Budget, BudgetExhausted
from .gateway import Gateway, ModelsUnavailable
from .pipeline import AuditReport, audit
from .schemas import Finding, Hypothesis, Invariant, Severity, SystemModel, Vertical
from .scope import Allowed, ScopeError, check_scope

__all__ = [
    "Budget", "BudgetExhausted", "Gateway", "ModelsUnavailable", "AuditReport", "audit",
    "Finding", "Hypothesis", "Invariant", "Severity", "SystemModel", "Vertical",
    "Allowed", "ScopeError", "check_scope",
]
