"""Reusable Debate Service (I-DS1): any authorized node may request a bounded, evidence-based,
cost-governed debate whose dissent is preserved. Plan §2.15, §19.2."""
from debate_service.cost_governor.governor import CostGovernor, DebateRefused
from debate_service.evidence_manager.manager import EvidenceManager, mcp_resolver
from debate_service.round_manager.manager import Debater, RoundManager, RoundOutcome
from debate_service.service import DebateAuthorizationError, DebateService

__all__ = [
    "CostGovernor", "DebateRefused", "EvidenceManager", "mcp_resolver",
    "Debater", "RoundManager", "RoundOutcome", "DebateService", "DebateAuthorizationError",
]
