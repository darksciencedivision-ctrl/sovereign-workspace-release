"""Phase 14E `.run` — the single assembled end-to-end scenario over LIVE shared MCP.

Consumes the `.roster` liveness matrix (`roster_report.assembled_report`) as the SINGLE source of
which legs are LIVE vs MOCK vs DETERMINISTIC_SUBSTITUTE — no leg is upgraded here beyond what
`.roster` proved. Then drives one assembled run over a REAL MCP server:

  1. a governed coding task CANDIDATE → node-local gate → controlled merge → ACCEPTED (promoted by a
     DIFFERENT gate node, invariant 18) across the assembled roster;
  2. one bounded debate (≤5 rounds, dissent preserved verbatim, cost-governed) requested by a
     NON-conductor worker (invariant 18, Phase 7 §2.8);
  3. conductor replacement mid-run (SuccessionManager: serialize → kill → reconstruct into a
     DIFFERENT mock model, ZERO project loss, Phase 11);
  4. full restart + recovery: the MCP process is stopped and restarted over the SAME durable store,
     then the successor reconstructs again — the ACCEPTED artifact, the debate record, and the
     succession snapshot all survive (zero project loss across a process restart).

Honesty (directive §6/§10.4): the rendered/visible panes are an operator-run metric (like the
Phase-1 spike and the 14A window) — this headless run proves the governed DATA path end-to-end
(MCP state, gate verdicts, provenance, succession, recovery). It does NOT claim a live `claude`
frontier call (owed at 14B) or a live local-coder LANDED edit (U31): the coding edit is a
deterministic seeded stand-in (`from_live_model=False`). The one leg that genuinely runs a real
model this session is the local reasoning Ollama receipt carried in the `.roster` report.

The UI-side recovery machine (terminal/recovery/*.js, RecoveryStore) is proven at gate/phase-14a
by the Node suite; this Python harness proves the corresponding governed DATA-path recovery (MCP
process restart + zero-loss conductor reconstruction), which is what a headless session can verify.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from adapters.coding.opencode.candidate import (
    package_worktree_candidate,
    submit_candidate_and_merge,
)
from control_plane.policy import Identity, SovereignPolicy
from node_runtime.workspace.worktree import MergeCoordinator, WorktreeManager
from control_plane.recovery import ConductorState, SuccessionManager
from debate_service.cost_governor.governor import CostGovernor
from debate_service.evidence_manager.manager import EvidenceManager, mcp_resolver
from debate_service.service import DebateService
from mcp_server.protocol import McpClient
from tools.assembled.roster_report import assembled_report

_DIRECTIVE_VERSION = "v2.4"
_FIXED_TS = "2026-07-18T00:00:00+00:00"


class _ScriptedDebater:
    """A deterministic debate participant for the assembled run — holds one fixed position and
    cites fixed evidence, so the Debate Service mechanics (rounds/budget/dissent/evidence) are
    exercised without live inference. Self-contained on purpose: the `tools/` harness must NOT
    depend on a `tests/` fixture (it has to import in a tests-excluded/offline profile too). A
    scripted participant is an honest DETERMINISTIC substitution (§6) — never a live model, and
    the run's honest_summary already labels the reasoning legs mock/deterministic."""

    def __init__(self, node_id: str, position: str, *, evidence_refs: list[str] | None = None) -> None:
        self.node_id = node_id
        self._position = position
        self._evidence_refs = evidence_refs or []

    def argue(self, topic: str, round_no: int, transcript: list[dict[str, Any]]) -> dict[str, Any]:
        return {"position": self._position, "evidence_refs": list(self._evidence_refs)}


def _prov(author: str, task_id: str | None = None) -> dict[str, Any]:
    return {"author_node": author, "task_id": task_id, "ts": _FIXED_TS,
            "directive_version": _DIRECTIVE_VERSION, "confidence": "high"}


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def _client(server: Any, node_id: str, role: str) -> McpClient:
    c = McpClient("127.0.0.1", server.port, server.credentials.issue(node_id, role, "proj"))
    c.connect()
    return c


def _default_server_factory(store_dir: Path) -> Any:  # pragma: no cover - exercised by the CLI
    from mcp_server.server import MCPServer

    srv = MCPServer(store_dir)
    srv.start()
    return srv


@dataclass(frozen=True)
class AssembledRunResult:
    """The observable outcome of the assembled end-to-end run — the phase evidence consumes this."""

    liveness: dict[str, Any]
    coding_task: dict[str, Any]
    debate: dict[str, Any]
    succession: dict[str, Any]
    restart_recovery: dict[str, Any]
    honest_summary: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "phase": "14E", "sub_step": "run",
            "liveness": self.liveness, "coding_task": self.coding_task, "debate": self.debate,
            "succession": self.succession, "restart_recovery": self.restart_recovery,
            "honest_summary": self.honest_summary,
        }


# ---- leg 1: governed coding task CANDIDATE → node-local gate → controlled merge → ACCEPTED --------

def _run_coding_task(server: Any, repo_path: Path) -> dict[str, Any]:
    # the conductor's assignment is published as the scoped objective (a single ACCEPTED MCP entry
    # the coder reads — invariant 8, no full-transcript forwarding)
    op = _client(server, "operator", "operator")
    obj = op.call("publish", kind="finding", tier="shared_project",
                  content_b64=_b64(b"Implement add() in calc.py to return a + b."),
                  provenance=_prov("operator"), status="ACCEPTED")
    op.close()
    objective_entry = obj["entry_id"]

    # the coding worker produces the edit in its OWN worktree. U31 honesty: no live local-coder
    # LANDED edit was producible headlessly, so the edit is a deterministic seeded stand-in and
    # from_live_model=False is recorded verbatim — the governed path is the system under test (§6).
    mgr = WorktreeManager(repo_path)
    wt = mgr.create("coder-A")
    (wt.path / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    packet = package_worktree_candidate(
        wt, task_id="t-add", context_entry_id=objective_entry, from_live_model=False)

    worker = _client(server, "coder-A", "worker")
    result = submit_candidate_and_merge(
        mcp_client=worker, worktree_manager=mgr, merger=MergeCoordinator(repo_path),
        worktree=wt, packet=packet, operator_approved=True)
    worker.close()
    if not (result.published and result.entry_id):
        raise RuntimeError(f"assembled coding task failed to publish CANDIDATE: {result.refused_reason}")

    # invariant 18: the CANDIDATE is promoted here by a DIFFERENT node (a gate), never its author.
    # The author-self-promotion REFUSAL is enforced by control_plane.policy.authorize_transition
    # (promotion is gate/operator-only) and proven live by a negative test in the .run suite —
    # this harness uses a distinct gate node rather than re-exercising that refusal.
    gate = _client(server, "gate-1", "gate")
    promoted = gate.call("transition", entry_id=result.entry_id, requested_status="ACCEPTED",
                         reviewer_note="assembled stage gate PASS")
    gate.close()

    return {
        "objective_entry": objective_entry, "candidate_entry": result.entry_id,
        "author_node": "coder-A", "promoted_by": "gate-1",
        "local_gate": result.local_gate, "merged": result.merged, "merge_sha": result.merge_sha,
        "final_status": promoted["status"], "from_live_model": result.from_live_model,
        "changed_files": list(result.changed_files),
    }


# ---- leg 2: one bounded debate (≤5 rounds, dissent preserved verbatim, cost-governed) -------------

def _run_bounded_debate(server: Any, evidence_ref: str,
                        debaters: list[Any] | None = None) -> dict[str, Any]:
    caller_client = _client(server, "worker-1", "worker")
    svc = DebateService(
        SovereignPolicy(),
        CostGovernor(per_caller_quota=100_000, global_concurrent_cap=4),
        EvidenceManager(mcp_resolver(caller_client)), caller_client, round_cost=100)
    caller = Identity("worker-1", "worker", "proj")
    # two participants holding fixed opposing positions => dissent is preserved verbatim (invariant
    # 15), never forced to concur. Both cite the REAL coding artifact just accepted.
    if debaters is None:
        debaters = [_ScriptedDebater("worker-1", "keep", evidence_refs=[evidence_ref]),
                    _ScriptedDebater("reviewer-2", "drop", evidence_refs=[evidence_ref])]
    req = {"caller_node": "worker-1",
           "topic": "Should the merged add() implementation be accepted as-is?",
           "participants": [{"capability": "reasoning", "requirements": {"structured_output": True}}],
           "max_rounds": 5, "budget": {"tokens": 10_000}}
    rec = svc.request_debate(caller, req, debaters)
    caller_client.close()
    return {
        "debate_id": rec["debate_id"], "outcome": rec["result"]["outcome"],
        "rounds_used": rec["result"].get("rounds_used"), "dissent": rec["result"].get("dissent"),
        "mcp_entry": rec["mcp_entry"],
    }


# ---- leg 3: conductor replacement mid-run (serialize → kill → reconstruct, zero loss) -------------

def _accepted_heads(client: McpClient) -> dict[str, str]:
    """Capture EVERY current ACCEPTED entry at its live version so the succession snapshot passes
    the §19.1 event-tail + heads-current checks (a head omitted or stale would flag project loss)."""
    heads: dict[str, str] = {}
    for e in client.call("read_status", status="ACCEPTED"):
        head = client.call("get_head", entry_id=e["entry_id"])
        heads[e["entry_id"]] = f'{e["entry_id"]}@{head["version"]}'
    return heads


def _replace_conductor_mid_run(server: Any, roster_nodes: list[dict[str, Any]],
                               coding: dict[str, Any], debate: dict[str, Any]) -> dict[str, Any]:
    cond_a = _client(server, "conductor-A", "conductor")
    state = ConductorState(
        tasks=[{"task_id": "t-add", "state": "DONE"}],
        nodes=roster_nodes,  # non-empty registry (§19.1 node_registry_present)
        open_debates=[debate["debate_id"]], pending_gates=[],
        memory_heads=_accepted_heads(cond_a),
        routing={"t-add": "coder-A"}, outstanding_issues=["U31"],
        directive_version=_DIRECTIVE_VERSION, task_graph_version=1,
        current_conductor={"node_id": "conductor-A", "model": "claude-mock",
                           "reason": "operator_selected", "since": _FIXED_TS})
    SuccessionManager(cond_a).serialize(state, trigger="major_event")
    cond_a.close()  # KILL conductor A mid-run (session gone)

    # operator Resume → Select a DIFFERENT mock model; the successor reconstructs from MCP
    cond_b = _client(server, "conductor-B", "conductor")
    reconstructed, report = SuccessionManager(cond_b).reconstruct(
        expected_directive_version=_DIRECTIVE_VERSION,
        new_selection={"node_id": "conductor-B", "model": "fable-mock"})
    cond_b.close()
    zero_loss = (reconstructed.tasks == state.tasks and reconstructed.nodes == state.nodes
                 and reconstructed.memory_heads == state.memory_heads
                 and reconstructed.open_debates == state.open_debates
                 and reconstructed.routing == state.routing)
    return {
        "ok": report.ok, "reasons": report.reasons(),
        "predecessor_model": "claude-mock", "successor_model": reconstructed.current_conductor["model"],
        "successor_reason": reconstructed.current_conductor["reason"], "zero_loss": bool(zero_loss),
    }


# ---- leg 4: full MCP process restart + zero-loss recovery over the SAME durable store -------------

def _prove_restart_recovery(server: Any, coding: dict[str, Any],
                            debate: dict[str, Any]) -> dict[str, Any]:
    cond_c = _client(server, "conductor-C", "conductor")
    _, report = SuccessionManager(cond_c).reconstruct(
        expected_directive_version=_DIRECTIVE_VERSION,
        new_selection={"node_id": "conductor-C", "model": "sonnet-mock"})
    accepted = {e["entry_id"] for e in cond_c.call("read_status", status="ACCEPTED")}
    coding_survived = coding["candidate_entry"] in accepted
    try:
        debate_survived = bool(cond_c.call("get_content", entry_id=debate["mcp_entry"]))
    except Exception:
        debate_survived = False  # fail closed: an unreadable record is NOT counted as survived
    snapshot_survived = SuccessionManager(cond_c).latest() is not None
    cond_c.close()
    return {
        "ok": bool(report.ok and coding_survived and debate_survived and snapshot_survived),
        "reasons": report.reasons(),
        "coding_entry_survived": coding_survived, "debate_record_survived": debate_survived,
        "snapshot_survived": snapshot_survived,
    }


def run_assembled_scenario(*, store_dir: Path, repo_path: Path,
                           server_factory: Callable[[Path], Any] | None = None,
                           allow_live: bool = True,
                           report: dict[str, Any] | None = None,
                           debaters: list[Any] | None = None) -> AssembledRunResult:
    """Drive the assembled end-to-end scenario. `server_factory(store_dir)` must return a STARTED
    MCP server (with `.port`, `.credentials.issue`, `.stop()`); it is called twice — once for the
    run and once for the post-restart recovery — over the SAME durable `store_dir`."""
    store_dir = Path(store_dir)
    store_dir.parent.mkdir(parents=True, exist_ok=True)
    factory = server_factory or _default_server_factory

    liveness = report or assembled_report(allow_live=allow_live, run_smoke=allow_live)
    roster_nodes = [{"node_id": r["role"], "state": "READY", "liveness": r["liveness"]}
                    for r in liveness["roles"]]

    srv = factory(store_dir)
    try:
        coding = _run_coding_task(srv, repo_path)
        # the debate cites the just-accepted coding CANDIDATE as its evidence anchor
        debate = _run_bounded_debate(srv, coding["candidate_entry"], debaters)
        succession = _replace_conductor_mid_run(srv, roster_nodes, coding, debate)
    finally:
        srv.stop()  # KILL the MCP process (full restart begins)

    srv2 = factory(store_dir)
    try:
        restart = _prove_restart_recovery(srv2, coding, debate)
    finally:
        srv2.stop()

    honest_summary = {
        "live_roles": liveness["live_roles"],
        "owed": [f"{r['role']}: {r['reason']}" for r in liveness["roles"] if r["owed"]],
        "coding_edit_from_live_model": coding["from_live_model"],
        "coding_edit_note": ("deterministic seeded stand-in (U31 — no live local-coder LANDED edit "
                             "producible headlessly); the governed CANDIDATE→gate→merge→ACCEPTED "
                             "path is the system under test (§6)"),
        "merge_approval": ("SIMULATED standing-delegation operator approval (operator ruling "
                           "2026-07-16, OP-1..OP-3) — NOT a live per-merge operator action; the "
                           "MergeCoordinator still requires gate PASS + this approval, inv 1"),
        "debate_participants": ("deterministic scripted debaters (not live models) — the Debate "
                                "Service mechanics (rounds/budget/dissent/evidence) are the system "
                                "under test (§6)"),
        "frontier_live_call": "OWED — no live `claude` call claimed (skip-with-record at 14B)",
        "voice": "MOCK_STT (14D skip-with-record — no real Parakeet)",
        "ui_recovery_machine": ("terminal/recovery/*.js + RecoveryStore proven at gate/phase-14a "
                                "(Node suite); this run proves the governed DATA-path recovery "
                                "(MCP restart + zero-loss conductor reconstruction)"),
        "genuinely_live_this_session": ("local reasoning Ollama receipt (item-7 smoke) when the "
                                        "daemon is reachable; every other leg is mock/deterministic "
                                        "by design or prohibition"),
    }
    return AssembledRunResult(
        liveness=liveness, coding_task=coding, debate=debate, succession=succession,
        restart_recovery=restart, honest_summary=honest_summary)


def main() -> int:  # pragma: no cover - CLI entry for the evidence receipt
    import json
    import subprocess
    import tempfile

    tmp = Path(tempfile.mkdtemp(prefix="sow-assembled-"))
    repo = tmp / "proj"
    repo.mkdir()
    for args in (["init", "-b", "main"], ["config", "user.email", "op@sovereign.local"],
                 ["config", "user.name", "operator"]):
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)
    (repo / "calc.py").write_text("def add(a, b):\n    raise NotImplementedError\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "seed"], check=True, capture_output=True)

    result = run_assembled_scenario(store_dir=tmp / "store", repo_path=repo, allow_live=True)
    print(json.dumps(result.as_dict(), indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
