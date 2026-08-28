"""TEST-ONLY demonstration approval queue — the trio Phase 17D `.events` removed from the product.

Phase 16D shipped this builder as the shell's approval-drawer PRODUCER: a canned objective run through
the real flow + gate engine, two canned commands run through the real broker, rebuilt identically on
every fetch. The operator opened the shell and saw three pending approvals no session had produced
(finding F2, 2026-07-25). Phase 17D replaced the producer with
`control_plane.orchestration.session_approvals`, which folds the real session-event log and shows an
EMPTY drawer for an empty session.

This module is what remains: a TEST-ONLY fixture, sited under `tests/` so no product import can reach
it. It still exercises the real governed producers end-to-end (a real `LiveGovernedFlow.begin` plan +
a real gate verdict, a real `CommandBroker` classification mirrored into a real `ApprovalQueue`), which
is why it is kept rather than deleted — but nothing it builds can ever reach the operator's drawer.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from adapters.conductor import publish_conductor_files
from control_plane.orchestration.live_flow import LiveGovernedFlow
from control_plane.orchestration.operator_surface import (
    ApprovalQueue,
    mirror_broker_outcome,
    propose_plan_for_approval,
)
from mcp_server.protocol import McpClient
from mcp_server.server import MCPServer
from voice_bridge.command_broker import CommandBroker, ProposedCommand

#: Smoke-scale objective (minimal work; the point is the governed drawer path, not the content).
DEFAULT_OBJECTIVE = "Design the offline conductor roster"

#: A fixed, replayable synthesis timestamp so the plan-gate run (and thus the item ids) are fully
#: deterministic — the same queue rebuilds identically.
APPROVALS_TS = "2026-07-24T00:00:00+00:00"

#: The representative governed commands the broker classifies into the drawer. Fixed so the queue is
#: deterministic. `spawn_node` is a PROTECTED verb (operator approval queued); the voice command is
#: low-confidence so it CLARIFIES (a question to the operator, approvable=False).
_PROTECTED_CMD = ProposedCommand(source="typed", verb="spawn_node", target="worker gpt-5.5",
                                 raw_text="spawn a gpt-5.5 worker node")
_CLARIFY_CMD = ProposedCommand(source="voice", verb="do", target="the roster thing",
                               raw_text="uh do the roster thing", confidence=0.2)


def build_governed_approval_queue(
    *,
    conductor_dir: Path,
    store_root: Path,
    objective: str = DEFAULT_OBJECTIVE,
    clock: Callable[[], str] | None = None,
) -> ApprovalQueue:
    """Build a REAL `ApprovalQueue` populated by the REAL governed producers and return it, tearing
    the loopback MCP server + flow down before returning (D-LOOP-1). NO live model call is made
    (mock-first). Deterministic: with a fixed `clock` and the fixed representative commands, the same
    three items enqueue in the same order (ap-1 plan, ap-2 protected_action, ap-3 clarification), so
    the decide path can rebuild this queue and resolve by item id.

    `store_root` is a caller-owned directory (a tempdir in the emitter/tests) — never touched outside.
    """
    ts = clock or (lambda: APPROVALS_TS)
    queue = ApprovalQueue()

    # (1) the PLAN item — a REAL conductor decomposition + REAL plan-gate verdict via flow.begin.
    srv = MCPServer(store_root / "store")
    srv.start()
    op: McpClient | None = None
    flow: LiveGovernedFlow | None = None
    try:
        op = McpClient("127.0.0.1", srv.port, srv.credentials.issue("op-boot", "operator", "proj"))
        op.connect()
        manifest = publish_conductor_files(op, "op-boot", conductor_dir)
        op.close()
        op = None  # closed cleanly on the happy path — don't double-close it in the finally
        flow = LiveGovernedFlow(srv, manifest, project_id="proj", clock=ts)
        run_state = flow.begin(objective)
        propose_plan_for_approval(
            queue, objective=objective, decomposition=run_state.decomposition,
            plan_gate=run_state.trace["plan_gate"], plan_blocked=run_state.plan_blocked)
    finally:
        if op is not None:
            try:
                op.close()
            except Exception:  # noqa: BLE001 — teardown must not mask the original error
                pass
        if flow is not None:
            flow.close()
        srv.stop()

    # (2) + (3) the PROTECTED_ACTION and CLARIFICATION items — a REAL broker classification mirrored
    # into the SAME drawer. The broker performs no I/O and holds no credential; it only classifies.
    broker = CommandBroker()
    mirror_broker_outcome(queue, broker.submit(_PROTECTED_CMD), _PROTECTED_CMD)
    mirror_broker_outcome(queue, broker.submit(_CLARIFY_CMD), _CLARIFY_CMD)
    return queue
