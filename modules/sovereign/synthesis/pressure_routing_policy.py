"""Phase 20.4 — stateless pressure-adaptive model routing policy."""
from __future__ import annotations

from typing import Any

# Pressure tier thresholds
TIER_BASELINE_MAX = 2.0
TIER_ELEVATED_MAX = 5.0
TIER_HIGH_MAX = 8.0
# > HIGH_MAX → critical

# Debate depth adjustments by tier
TIER_DEBATE_ROUNDS: dict[str, int] = {
    "baseline": 1,
    "elevated": 2,
    "high": 3,
    "critical": 4,
}

# Model strength selection by tier (stronger models at higher pressure)
TIER_MODEL_STRENGTH: dict[str, str] = {
    "baseline": "standard",
    "elevated": "standard",
    "high": "strong",
    "critical": "strong",
}

# Context budget recommendations by tier (tokens)
TIER_CONTEXT_BUDGET: dict[str, int] = {
    "baseline": 2048,
    "elevated": 3072,
    "high": 4096,
    "critical": 6144,
}

# Arbitration scrutiny recommendations by tier
TIER_ARBITRATION_SCRUTINY: dict[str, str] = {
    "baseline": "standard",
    "elevated": "elevated",
    "high": "high",
    "critical": "high",
}

# Contradiction-aware synthesis activation threshold
CONTRADICTION_AWARE_SYNTHESIS_PRESSURE_THRESHOLD = 3.0


def classify_pressure_tier(aggregate_pressure: float) -> str:
    """Classify aggregate pressure into a routing tier."""
    if aggregate_pressure <= TIER_BASELINE_MAX:
        return "baseline"
    if aggregate_pressure <= TIER_ELEVATED_MAX:
        return "elevated"
    if aggregate_pressure <= TIER_HIGH_MAX:
        return "high"
    return "critical"


def build_routing_signal(aggregate_pressure: float, topic: str = "") -> dict[str, Any]:
    """
    Build a routing signal from aggregate pressure.

    Applied actions (will be enacted by orchestrator):
    - debate_rounds: int
    - model_strength: str
    - enable_contradiction_aware_synthesis: bool

    Recommended-only actions (advisory, not automatically applied):
    - context_budget: int
    - arbitration_scrutiny: str
    """
    tier = classify_pressure_tier(aggregate_pressure)
    debate_rounds = TIER_DEBATE_ROUNDS[tier]
    model_strength = TIER_MODEL_STRENGTH[tier]
    enable_cas = aggregate_pressure >= CONTRADICTION_AWARE_SYNTHESIS_PRESSURE_THRESHOLD

    return {
        "tier": tier,
        "aggregate_pressure": aggregate_pressure,
        "topic": topic,
        # Applied actions
        "applied": {
            "debate_rounds": debate_rounds,
            "model_strength": model_strength,
            "enable_contradiction_aware_synthesis": enable_cas,
        },
        # Recommended-only (not automatically applied — advisory only)
        "recommended": {
            "context_budget": TIER_CONTEXT_BUDGET[tier],
            "arbitration_scrutiny": TIER_ARBITRATION_SCRUTINY[tier],
        },
    }
