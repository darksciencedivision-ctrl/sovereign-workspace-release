"""Phase 14C `.gate` (live): drive REAL OpenCode, then run the governed CANDIDATE→merge chain.

This is the honest live tie-off of Phase 14C: it spawns REAL `opencode run` (local, credential-free)
through the supervised gate against the host's local Ollama coder, in a REAL isolated worktree, from
a REAL scoped MCP entry — then packages the result as a CANDIDATE, gates it, publishes it to a REAL
MCP server, and drives the REAL `MergeCoordinator` into the trunk. SKIPS-WITH-RECORD (directive
§10.4) when OpenCode or a local coder model is absent — never faked.

HONESTY (directive §6, U31). A small local coder is flaky at COMPLETING a schema-correct headless
edit. So the merge is driven by whatever the worktree holds AFTER the drive: if the live model landed
a gate-clean edit, THAT is packaged (`from_live_model=True`); otherwise a DETERMINISTIC seeded edit is
applied and `from_live_model=False` is recorded — the governed path (package → node-local gate →
CANDIDATE publish → controlled merge) is the system under test and is proven either way. The test
never claims a live landed edit that the model did not produce; the actual origin is printed and
asserted from `from_live_model`.
"""
from __future__ import annotations

import base64
import subprocess
from pathlib import Path

import pytest

from adapters import detect
from adapters.coding.opencode.candidate import (
    WorktreeCandidateGate,
    package_worktree_candidate,
    submit_candidate_and_merge,
)
from adapters.coding.opencode.driver import OpenCodeDriver
from adapters.coding.opencode.harness import OpenCodeCliHarness
from mcp_server.protocol import McpClient
from mcp_server.server import MCPServer
from node_runtime.supervisor.opencode_spawn import probe_opencode, spawn_opencode_harness
from node_runtime.workspace.worktree import MergeCoordinator, WorktreeManager

_HARNESS = OpenCodeCliHarness()
_PROBE = probe_opencode(_HARNESS) if detect.opencode_available() else None
_DRIVABLE = bool(_PROBE and _PROBE.present and _PROBE.meets_minimum and _PROBE.coder_model)

pytestmark = pytest.mark.skipif(
    not _DRIVABLE,
    reason="opencode + a local Ollama coder model not both present — .gate live chain "
           "SKIPPED-WITH-RECORD (§10.4)")

_SEED = "def add(a, b):\n    raise NotImplementedError\n"
_CLEAN_IMPL = "def add(a, b):\n    return a + b\n"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)


@pytest.fixture()
def repo(tmp_path):
    base = tmp_path / "proj"
    base.mkdir()
    _git(base, "init", "-b", "main")
    _git(base, "config", "user.email", "op@sovereign.local")
    _git(base, "config", "user.name", "operator")
    (base / "calc.py").write_text(_SEED, encoding="utf-8")
    _git(base, "add", "-A")
    _git(base, "commit", "-m", "seed target")
    return base


@pytest.fixture()
def server(tmp_path):
    srv = MCPServer(tmp_path / "store"); srv.start()
    yield srv
    srv.stop()


def test_live_drive_then_governed_candidate_and_merge(repo, server, capsys):
    # 1. scoped objective in shared MCP memory, read by the ONE entry_id (invariant 8)
    op = McpClient("127.0.0.1", server.port, server.credentials.issue("op", "operator", "proj"))
    op.connect()
    objective = ("In calc.py in the working directory, the function add(a, b) raises "
                 "NotImplementedError. Use the edit tool to make it return a + b instead.")
    obj_entry = op.call("publish", kind="finding", tier="shared_project",
                        content_b64=base64.b64encode(objective.encode("utf-8")).decode("ascii"),
                        provenance={"author_node": "op", "task_id": None,
                                    "ts": "2026-07-18T00:00:00+00:00", "directive_version": "v2.4",
                                    "confidence": "high"}, status="ACCEPTED")["entry_id"]

    # 2. supervised spawn + isolated worktree
    supervised = spawn_opencode_harness(
        mcp_client=object(), node_id="oc-gate", permission_profile_id="pp-coding",
        workspace_root=str(repo), harness=_HARNESS)
    mgr = WorktreeManager(repo)
    wt = mgr.create("oc-gate")
    (wt.path / "calc.py").write_text(_SEED, encoding="utf-8")

    worker = McpClient("127.0.0.1", server.port, server.credentials.issue("oc-gate", "worker", "proj"))
    worker.connect()
    driver = OpenCodeDriver(supervised, wt, worker, base_repo=repo,
                            session_dir=repo.parent / "oc-session", timeout_s=240.0)

    # 3. drive REAL opencode (recorded); the governance facts below are reliably true
    scoped = driver.read_scoped_objective(obj_entry)
    assert scoped == objective
    drive = driver.drive(scoped)
    assert drive.drove is True, drive.as_dict()
    assert drive.model.startswith("ollama/")                # §2.3 local pin
    assert drive.escaped is False and drive.containment_verified is True  # confined to worktree

    # 4. decide the edit ORIGIN honestly: use the live edit ONLY if it landed AND passes the gate;
    #    otherwise apply a deterministic seeded edit and record from_live_model=False (U31).
    from_live_model = False
    if drive.edit_completed:
        trial = package_worktree_candidate(wt, task_id="t-add", context_entry_id=obj_entry,
                                           from_live_model=True, model=drive.model)
        if WorktreeCandidateGate().evaluate(trial).passed:
            from_live_model = True
    if not from_live_model:
        (wt.path / "calc.py").write_text(_CLEAN_IMPL, encoding="utf-8")

    packet = package_worktree_candidate(
        wt, task_id="t-add", context_entry_id=obj_entry, from_live_model=from_live_model,
        model=drive.model if from_live_model else None)

    # 5. the full governed chain against REAL MCP + REAL MergeCoordinator
    result = submit_candidate_and_merge(
        mcp_client=worker, worktree_manager=mgr, merger=MergeCoordinator(repo), worktree=wt,
        packet=packet, operator_approved=True)

    assert result.local_gate == "PASS"
    assert result.published and result.entry_id and result.merged and result.merge_sha
    head = worker.call("get_head", entry_id=result.entry_id)
    assert head["status"] == "CANDIDATE"                    # worker never self-canonizes (inv 10)
    assert head["provenance"]["author_node"] == "oc-gate"   # provenance present (inv 11)

    # 6. a DIFFERENT node promotes CANDIDATE→ACCEPTED (invariant 18)
    gate_client = McpClient("127.0.0.1", server.port, server.credentials.issue("gate-1", "gate", "proj"))
    gate_client.connect()
    promoted = gate_client.call("transition", entry_id=result.entry_id,
                                requested_status="ACCEPTED", reviewer_note="stage gate PASS")
    assert promoted["applied"] and promoted["status"] == "ACCEPTED"

    # honest record of where the merged bytes came from
    origin = "LIVE local model" if from_live_model else "deterministic seeded edit (U31)"
    print(f"\n[.gate LIVE] drive={drive.as_dict()}")
    print(f"[.gate LIVE] merged content origin = {origin}; result={result.as_dict()}")
    if not from_live_model:
        print("[.gate LIVE] the flaky local coder did not land a gate-clean edit this run - the "
              "governed CANDIDATE->gate->merge path is proven with a seeded edit (harness/governance "
              "path is the system under test).")

    gate_client.close(); worker.close(); op.close()
