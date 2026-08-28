"""Phase 2 node process manager: registry, state machine, heartbeat, event log,
crash detection and restart (Buildout Directive section 5, Plan section 7-P2)."""
from .event_log import AppendOnlyEventLog, VerifyResult, verify_file
from .heartbeat import HeartbeatMonitor, HeartbeatPolicy
from .process_manager import NodeProcessManager, RestartPolicy
from .registry import NodeRecord, NodeRegistry, RegistrationRefused
from .states import LEGAL, IllegalTransition, NodeState, validate_transition

__all__ = [
    "AppendOnlyEventLog", "VerifyResult", "verify_file",
    "HeartbeatMonitor", "HeartbeatPolicy",
    "NodeProcessManager", "RestartPolicy",
    "NodeRecord", "NodeRegistry", "RegistrationRefused",
    "LEGAL", "IllegalTransition", "NodeState", "validate_transition",
]
