"""Mock-model node: the Phase 3 exit-criterion vehicle (Plan section 7-P3).

Deterministic stand-in for a model-backed node: loads its config fail-closed, produces a
structured output + artifact THROUGH the WorkspaceBinding (never raw filesystem), and
submits to its LocalGate before anything is considered publishable. Seeded defect modes
exist so tests prove the gate actually rejects: this is the falsifiability hook, not
product behavior.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from node_runtime.context.loaders import NodeConfig, load_node_config
from node_runtime.gate.local_gate import GateVerdict, LocalGate
from node_runtime.workspace.binding import WorkspaceBinding

DEFECT_MODES = ("none", "invalid_artifact_schema", "missing_evidence", "placeholder_text", "workspace_escape")


@dataclass(frozen=True)
class MockNodeResult:
    config: NodeConfig
    structured_output: dict[str, Any]
    artifact_path: Path | None
    gate: GateVerdict
    escape_attempted: bool
    escape_refused: bool


def run_mock_node(
    node_id: str,
    config_dir: Path,
    workspace: WorkspaceBinding,
    *,
    defect: str = "none",
) -> MockNodeResult:
    if defect not in DEFECT_MODES:
        raise ValueError(f"unknown defect mode: {defect}")
    config = load_node_config(config_dir, expected_node_class="worker_reasoning")

    body = f"# Mock analysis by {node_id}\n\nDeterministic content derived from directive hash {config.hashes['DIRECTIVE.md'][:12]}.\n"
    if defect == "placeholder_text":
        body += "\nTODO: fill this section in later.\n"
    content = body.encode("utf-8")
    digest = "sha256:" + hashlib.sha256(content).hexdigest()

    escape_attempted = defect == "workspace_escape"
    escape_refused = False
    artifact_path: Path | None = None
    if escape_attempted:
        from node_runtime.workspace.binding import WorkspaceEscape
        try:
            workspace.write_text("..\\outside_the_fence.md", body)
        except WorkspaceEscape:
            escape_refused = True  # correct behavior: refused and logged by the binding
    else:
        artifact_path = workspace.write_text("out/analysis.md", body)

    metadata: dict[str, Any] = {
        "artifact_id": digest,
        "media_type": "text/markdown",
        "size_bytes": len(content),
        "created_by_node": node_id,
        "task_id": None,
        "ts": datetime.now(timezone.utc).isoformat(),
        "schema": "artifact@1.0",
    }
    if defect == "invalid_artifact_schema":
        del metadata["media_type"]

    claims: list[dict[str, Any]] = [
        {"text": "the directive was loaded fail-closed", "evidence_refs": [f"config:{config.hashes['DIRECTIVE.md']}"]},
        {"text": "the artifact is content-addressed", "evidence_refs": [digest]},
    ]
    if defect == "missing_evidence":
        claims.append({"text": "an unsupported assertion", "evidence_refs": []})

    structured_output: dict[str, Any] = {
        "summary": f"mock node {node_id} completed its task",
        "claims": claims,
        "artifact": metadata,
        "workspace_files": [str(artifact_path.relative_to(workspace.root))] if artifact_path else [],
    }

    gate = LocalGate().evaluate(structured_output, content)
    if artifact_path is not None:
        workspace.write_text("out/structured_output.json", json.dumps(structured_output, indent=2))
    return MockNodeResult(
        config=config, structured_output=structured_output, artifact_path=artifact_path,
        gate=gate, escape_attempted=escape_attempted, escape_refused=escape_refused,
    )
