"""Phase 3 Sovereign node runtime: fail-closed config loaders, workspace binding,
process-tree containment scaffold, local gate, structured-output validation
(Buildout Directive section 5 Phase 3, Plan section 7-P3)."""
from node_runtime.context.loaders import LoaderError, NodeConfig, load_node_config
from node_runtime.gate.local_gate import (
    DEFAULT_CRITERIA,
    GateConfigError,
    GateVerdict,
    LocalGate,
)
from node_runtime.mock_node import DEFECT_MODES, MockNodeResult, run_mock_node
from node_runtime.workspace.binding import WorkspaceBinding, WorkspaceEscape

__all__ = [
    "LoaderError", "NodeConfig", "load_node_config",
    "DEFAULT_CRITERIA", "GateConfigError", "GateVerdict", "LocalGate",
    "DEFECT_MODES", "MockNodeResult", "run_mock_node",
    "WorkspaceBinding", "WorkspaceEscape",
]
