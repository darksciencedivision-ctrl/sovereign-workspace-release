"""Phase 14C `.gate` (deterministic): the full governed chain from a driven worktree to the trunk.

    driven worktree edit → node-local gate → CANDIDATE published to MCP → controlled merge

These tests use a REAL MCP server, a REAL git worktree, and the REAL `MergeCoordinator` — but a
DETERMINISTIC SEEDED worktree edit stands in for the model's output (directive §6, U31: a small local
coder did not complete a live schema-correct edit this session, so the governed path — the system
under test — is exercised with a scripted edit, and `from_live_model=False` records that). No
`opencode` is spawned here; the live spawn is proven in `.harness`/`.worktree`.

What is proven, all fail-closed:
  - worker publishes CANDIDATE, never self-canonizes (invariant 10) + full provenance (invariant 11);
  - a failed artifact cannot advance — a FAIL node-local gate is neither published nor merged (16);
  - the trunk merge requires the passing gate AND operator approval (invariant 1);
  - a different node promotes CANDIDATE→ACCEPTED; the author cannot (invariant 18).
"""
from __future__ import annotations

import base64
import subprocess
from pathlib import Path

import pytest

from adapters.coding.opencode.candidate import (
    CandidateRefused,
    WorktreeCandidateGate,
    package_worktree_candidate,
    submit_candidate_and_merge,
)
from mcp_server.protocol import McpClient, McpError
from node_runtime.workspace.worktree import (
    MergeCoordinator,
    MergeRefused,
    WorktreeError,
    WorktreeManager,
)
from mcp_server.server import MCPServer


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)


@pytest.fixture()
def repo(tmp_path):
    """A throwaway git repo (NEVER the build repo) seeded with a target the 'edit' will implement."""
    base = tmp_path / "proj"
    base.mkdir()
    _git(base, "init", "-b", "main")
    _git(base, "config", "user.email", "op@sovereign.local")
    _git(base, "config", "user.name", "operator")
    # seed a function to implement — deliberately free of placeholder markers so the packaged
    # manifest passes the node-local gate's no_placeholders check when the edit is a clean impl
    (base / "calc.py").write_text("def add(a, b):\n    raise NotImplementedError\n", encoding="utf-8")
    _git(base, "add", "-A")
    _git(base, "commit", "-m", "seed target")
    return base


@pytest.fixture()
def server(tmp_path):
    srv = MCPServer(tmp_path / "store"); srv.start()
    yield srv
    srv.stop()


def _client(server: MCPServer, node_id: str, role: str) -> McpClient:
    c = McpClient("127.0.0.1", server.port, server.credentials.issue(node_id, role, "proj"))
    c.connect()
    return c


def _publish_objective(server: MCPServer, text: str) -> str:
    op = _client(server, "op", "operator")
    entry = op.call("publish", kind="finding", tier="shared_project",
                    content_b64=base64.b64encode(text.encode("utf-8")).decode("ascii"),
                    provenance={"author_node": "op", "task_id": None,
                                "ts": "2026-07-18T00:00:00+00:00", "directive_version": "v2.4",
                                "confidence": "high"}, status="ACCEPTED")
    op.close()
    return entry["entry_id"]


def _seed_edit(wt_path: Path) -> None:
    """The deterministic stand-in for a completed model edit — a clean, marker-free implementation."""
    (wt_path / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")


# ---- happy path: seeded edit → gate PASS → CANDIDATE → controlled merge → ACCEPTED --------------

def test_full_chain_candidate_published_and_merged(repo, server):
    obj_entry = _publish_objective(server, "Implement add() in calc.py to return a + b.")
    mgr = WorktreeManager(repo)
    wt = mgr.create("coder-A")
    _seed_edit(wt.path)  # deterministic seeded edit (NOT a live model — from_live_model=False)

    worker = _client(server, "coder-A", "worker")
    events: list = []
    packet = package_worktree_candidate(
        wt, task_id="t-add", context_entry_id=obj_entry, from_live_model=False)
    assert packet.from_live_model is False and "calc.py" in packet.changed_files
    assert packet.content_hash.startswith("sha256:")

    merger = MergeCoordinator(repo, on_event=lambda k, **d: events.append((k, d)))
    gate = WorktreeCandidateGate(on_event=lambda k, **d: events.append((k, d)))
    result = submit_candidate_and_merge(
        mcp_client=worker, worktree_manager=mgr, merger=merger, worktree=wt, packet=packet,
        operator_approved=True, gate=gate)

    assert result.local_gate == "PASS"
    assert result.published and result.entry_id and result.entry_id.startswith("m-")
    assert result.merged and result.merge_sha and len(result.merge_sha) == 40
    # the trunk now carries the merged change (controlled merge path passed)
    assert (repo / "calc.py").read_text(encoding="utf-8") == "def add(a, b):\n    return a + b\n"
    assert any(k == "candidate_published" for k, _ in events)
    assert any(k == "merge_applied" for k, _ in events)

    # the published entry is a CANDIDATE with full provenance (never self-canonized: invariant 10/11)
    head = worker.call("get_head", entry_id=result.entry_id)
    assert head["status"] == "CANDIDATE"
    prov = head["provenance"]
    for f in ("author_node", "task_id", "ts", "directive_version", "confidence"):
        assert f in prov, f
    assert prov["author_node"] == "coder-A"
    assert obj_entry in prov["evidence"] and packet.content_hash in prov["evidence"]
    worker.close()

    # invariant 18: a DIFFERENT node (a gate) promotes CANDIDATE→ACCEPTED; the author cannot
    gate_client = _client(server, "gate-1", "gate")
    promoted = gate_client.call("transition", entry_id=result.entry_id,
                                requested_status="ACCEPTED", reviewer_note="stage gate PASS")
    assert promoted["applied"] and promoted["status"] == "ACCEPTED"
    gate_client.close()


def test_author_cannot_self_promote_its_own_candidate(repo, server):
    """Invariant 18 at the memory layer: the coding node that published the CANDIDATE cannot promote
    it to ACCEPTED — only a different node can (no node solely judges its own work)."""
    obj_entry = _publish_objective(server, "Implement add().")
    mgr = WorktreeManager(repo); wt = mgr.create("coder-A"); _seed_edit(wt.path)
    worker = _client(server, "coder-A", "worker")
    packet = package_worktree_candidate(wt, task_id="t-add", context_entry_id=obj_entry,
                                        from_live_model=False)
    result = submit_candidate_and_merge(
        mcp_client=worker, worktree_manager=mgr, merger=MergeCoordinator(repo), worktree=wt,
        packet=packet, operator_approved=True)
    assert result.published
    # the worker may move its own entry to UNDER_REVIEW but never to a promoted state
    worker.call("transition", entry_id=result.entry_id, requested_status="UNDER_REVIEW")
    with pytest.raises(McpError):
        worker.call("transition", entry_id=result.entry_id, requested_status="ACCEPTED")
    worker.close()


# ---- invariant 16: a FAIL node-local gate is neither published nor merged ----------------------

def test_failed_local_gate_blocks_publish_and_merge(repo, server):
    """A packaged change that still contains a placeholder marker fails the node-local gate — it must
    NOT be published to MCP and must NOT reach the trunk (invariant 16, fail closed)."""
    obj_entry = _publish_objective(server, "Implement add().")
    mgr = WorktreeManager(repo); wt = mgr.create("coder-A")
    # a DIRTY edit: leaves a TODO in the code → no_placeholders check fails
    (wt.path / "calc.py").write_text("def add(a, b):\n    return a + b  # TODO verify\n", encoding="utf-8")
    worker = _client(server, "coder-A", "worker")
    packet = package_worktree_candidate(wt, task_id="t-add", context_entry_id=obj_entry,
                                        from_live_model=False)
    events: list = []
    result = submit_candidate_and_merge(
        mcp_client=worker, worktree_manager=mgr, merger=MergeCoordinator(repo), worktree=wt,
        packet=packet, operator_approved=True,
        gate=WorktreeCandidateGate(on_event=lambda k, **d: events.append((k, d))))
    assert result.local_gate == "FAIL"
    assert result.published is False and result.entry_id is None and result.merged is False
    assert "no_placeholders" in (result.refused_reason or "")
    # nothing was published to MCP and the trunk is untouched
    assert worker.call("read_status", status="CANDIDATE") == []
    assert (repo / "calc.py").read_text(encoding="utf-8") == "def add(a, b):\n    raise NotImplementedError\n"
    worker.close()


def test_gate_publish_refuses_failed_artifact_directly(repo, server):
    """The publish path itself fails closed: a FAIL verdict raises rather than writing to MCP."""
    obj_entry = _publish_objective(server, "x")
    mgr = WorktreeManager(repo); wt = mgr.create("coder-A")
    (wt.path / "calc.py").write_text("def add(a, b):\n    return a + b  # FIXME\n", encoding="utf-8")
    worker = _client(server, "coder-A", "worker")
    packet = package_worktree_candidate(wt, task_id="t", context_entry_id=obj_entry,
                                        from_live_model=False)
    with pytest.raises(CandidateRefused, match="invariant 16"):
        WorktreeCandidateGate().publish(worker, packet)
    worker.close()


# ---- invariant 1: the merge requires operator approval (a passing gate alone is not enough) -----

def test_merge_refused_without_operator_approval_candidate_still_published(repo, server):
    """A passing gate WITHOUT operator approval still publishes the CANDIDATE (the worker's
    submission for review) but the trunk merge is refused — the protected action is never
    self-authorized (invariant 1)."""
    obj_entry = _publish_objective(server, "Implement add().")
    mgr = WorktreeManager(repo); wt = mgr.create("coder-A"); _seed_edit(wt.path)
    worker = _client(server, "coder-A", "worker")
    packet = package_worktree_candidate(wt, task_id="t-add", context_entry_id=obj_entry,
                                        from_live_model=False)
    result = submit_candidate_and_merge(
        mcp_client=worker, worktree_manager=mgr, merger=MergeCoordinator(repo), worktree=wt,
        packet=packet, operator_approved=False)  # NOT approved
    assert result.published and result.entry_id  # CANDIDATE submitted for review
    assert result.merged is False and "operator approval" in (result.refused_reason or "")
    # trunk untouched: the un-approved work never reached it
    assert (repo / "calc.py").read_text(encoding="utf-8") == "def add(a, b):\n    raise NotImplementedError\n"
    # the CANDIDATE is genuinely in MCP, awaiting review
    listed = worker.call("read_status", status="CANDIDATE")
    assert any(e["entry_id"] == result.entry_id for e in listed)
    worker.close()


def test_merge_refused_when_operator_approved_is_truthy_not_true(repo, server):
    """Strict-boolean approval (invariant 1 / F3): a truthy-but-not-True value does not approve."""
    obj_entry = _publish_objective(server, "Implement add().")
    mgr = WorktreeManager(repo); wt = mgr.create("coder-A"); _seed_edit(wt.path)
    worker = _client(server, "coder-A", "worker")
    packet = package_worktree_candidate(wt, task_id="t-add", context_entry_id=obj_entry,
                                        from_live_model=False)
    result = submit_candidate_and_merge(
        mcp_client=worker, worktree_manager=mgr, merger=MergeCoordinator(repo), worktree=wt,
        packet=packet, operator_approved=1)  # truthy, not True
    assert result.published and result.merged is False
    worker.close()


# ---- packaging edge cases ----------------------------------------------------------------------

def test_package_refuses_empty_worktree(repo, server):
    """A worktree with no changes has nothing to submit — refuse rather than publish an empty
    artifact (fail closed)."""
    obj_entry = _publish_objective(server, "do nothing")
    mgr = WorktreeManager(repo); wt = mgr.create("coder-A")  # no edit performed
    with pytest.raises(CandidateRefused, match="no worktree changes"):
        package_worktree_candidate(wt, task_id="t", context_entry_id=obj_entry, from_live_model=False)


def test_manifest_is_deterministic_and_content_addressed(repo, server):
    """The same worktree change packages to the same bytes and the same hash (content-addressing)."""
    obj_entry = _publish_objective(server, "impl")
    mgr = WorktreeManager(repo); wt = mgr.create("coder-A"); _seed_edit(wt.path)
    p1 = package_worktree_candidate(wt, task_id="t", context_entry_id=obj_entry, from_live_model=False)
    p2 = package_worktree_candidate(wt, task_id="t", context_entry_id=obj_entry, from_live_model=False)
    assert p1.content == p2.content and p1.content_hash == p2.content_hash
    import hashlib
    assert p1.content_hash == "sha256:" + hashlib.sha256(p1.content).hexdigest()
    # the artifact metadata is content-addressed to the same bytes (the node-local gate checks this)
    assert p1.structured["artifact"]["artifact_id"] == p1.content_hash
    assert p1.structured["artifact"]["size_bytes"] == len(p1.content)


def test_from_live_model_flag_is_recorded_verbatim(repo, server):
    """Honesty (U31): the packet records whether the edit came from a live model. This session's
    seeded edit is from_live_model=False; the flag is never silently flipped."""
    obj_entry = _publish_objective(server, "impl")
    mgr = WorktreeManager(repo); wt = mgr.create("coder-A"); _seed_edit(wt.path)
    packet = package_worktree_candidate(wt, task_id="t", context_entry_id=obj_entry,
                                        from_live_model=False)
    worker = _client(server, "coder-A", "worker")
    WorktreeCandidateGate().publish(worker, packet)
    # provenance model marker reflects the seeded origin, not a fabricated live model
    listed = worker.call("read_status", status="CANDIDATE")
    assert listed and listed[0]["provenance"]["model"] == "seeded-edit"
    worker.close()


def test_live_model_id_is_recorded_in_provenance(repo, server):
    """Invariant 11 fidelity: when an edit genuinely comes from a live model, provenance records the
    ACTUAL model id, not a generic marker. (Deterministic plumbing check of the provenance path — the
    real live origin is exercised in test_opencode_candidate_live.py.)"""
    obj_entry = _publish_objective(server, "impl")
    mgr = WorktreeManager(repo); wt = mgr.create("coder-A"); _seed_edit(wt.path)
    worker = _client(server, "coder-A", "worker")
    packet = package_worktree_candidate(wt, task_id="t", context_entry_id=obj_entry,
                                        from_live_model=True, model="ollama/qwen2.5-coder:7b")
    WorktreeCandidateGate().publish(worker, packet)
    listed = worker.call("read_status", status="CANDIDATE")
    assert listed and listed[0]["provenance"]["model"] == "ollama/qwen2.5-coder:7b"
    worker.close()


class _FailingCommitManager:
    """A worktree manager whose commit fails — to prove submit_candidate_and_merge fails closed."""

    def commit(self, node_id, message):
        raise WorktreeError("simulated commit failure")


def test_commit_failure_is_a_governed_result_not_a_crash(repo, server):
    """Fail-closed framing: a commit failure (which happens BEFORE publish) aborts the chain with a
    governed result — nothing published, nothing merged — never an uncaught crash."""
    obj_entry = _publish_objective(server, "impl")
    mgr = WorktreeManager(repo); wt = mgr.create("coder-A"); _seed_edit(wt.path)
    worker = _client(server, "coder-A", "worker")
    packet = package_worktree_candidate(wt, task_id="t", context_entry_id=obj_entry,
                                        from_live_model=False)
    result = submit_candidate_and_merge(
        mcp_client=worker, worktree_manager=_FailingCommitManager(), merger=MergeCoordinator(repo),
        worktree=wt, packet=packet, operator_approved=True)
    assert result.published is False and result.merged is False
    assert "commit failed" in (result.refused_reason or "")
    # fail closed: the commit runs before publish, so nothing reached MCP
    assert worker.call("read_status", status="CANDIDATE") == []
    worker.close()
