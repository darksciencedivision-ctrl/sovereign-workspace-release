"""Persistence & conductor succession (Phase 11; I-CS1): serialize conductor state to MCP,
reconstruct into a freshly-selected conductor with zero project loss."""
from control_plane.recovery.succession import (
    DEFAULT_INTERVAL_S,
    ConductorState,
    StalenessReport,
    SuccessionManager,
    should_snapshot,
)

__all__ = [
    "ConductorState", "StalenessReport", "SuccessionManager", "should_snapshot", "DEFAULT_INTERVAL_S",
]
