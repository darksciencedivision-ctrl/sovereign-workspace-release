"""Gate engine (Phase 8): declarative criteria, deterministic verdicts referencing
evidence/debate records, failed artifacts cannot advance (invariant 16, no conductor override)."""
from control_plane.gates.criteria import (
    GateContext,
    Severity,
    UnknownCriterion,
    evaluate_criterion,
    known_criteria,
)
from control_plane.gates.engine import GateConfigError, GateDefinition, GateEngine, define_gate

__all__ = [
    "GateContext", "Severity", "UnknownCriterion", "evaluate_criterion", "known_criteria",
    "GateConfigError", "GateDefinition", "GateEngine", "define_gate",
]
