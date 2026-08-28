"""Phase 14E `.run` — the single assembled end-to-end scenario over LIVE shared MCP.

These tests drive `tools/assembled/run.run_assembled_scenario` against a REAL MCP server, a REAL
throwaway git repo, the REAL SuccessionManager, the REAL DebateService, and the REAL controlled
merge path. They prove the governed DATA path end-to-end (the rendered panes are an operator-run
metric, directive §6): a governed coding task CANDIDATE→gate→ACCEPTED, one bounded debate, a
conductor replacement mid-run, and a full MCP process restart + zero-loss recovery.

Honesty (directive §6/§10.4): the coding edit is a deterministic seeded stand-in
(`from_live_model=False`, U31 — no live local-coder LANDED edit was producible); no live `claude`
frontier call is claimed (owed at 14B). The deterministic suite runs with `allow_live=False` so it
needs no daemon; a separate live test runs the Ollama receipt and SKIPS-WITH-RECORD if the daemon
is absent — never faked.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from mcp_server.protocol import McpClient, McpError
from mcp_server.server import MCPServer
from tools.assembled.run import _b64, _prov, run_assembled_scenario


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)


def _seed_repo(base: Path) -> Path:
    """A throwaway git repo (NEVER the build repo) seeded with a target the seeded edit implements."""
    base.mkdir()
    _git(base, "init", "-b", "main")
    _git(base, "config", "user.email", "op@sovereign.local")
    _git(base, "config", "user.name", "operator")
    # seed calc.py with a DIFFERENT body so the worktree edit is a real change (marker-free so the
    # node-local gate's no_placeholders check passes on the clean impl)
    (base / "calc.py").write_text("def add(a, b):\n    raise NotImplementedError\n", encoding="utf-8")
    _git(base, "add", "-A")
    _git(base, "commit", "-m", "seed target")
    return base


@pytest.fixture()
def repo(tmp_path):
    return _seed_repo(tmp_path / "proj")


def _server_factory(store_dir: Path):
    srv = MCPServer(store_dir)
    srv.start()
    return srv


def _run(tmp_path, repo, *, allow_live):
    return run_assembled_scenario(
        store_dir=tmp_path / "store", repo_path=repo,
        server_factory=_server_factory, allow_live=allow_live)


# ---- the deterministic assembled run (no daemon needed) -----------------------------------------

def test_assembled_run_governed_data_path_end_to_end(tmp_path, repo):
    result = _run(tmp_path, repo, allow_live=False).as_dict()

    # 1. governed coding task: CANDIDATE → node-local gate PASS → controlled merge → ACCEPTED
    coding = result["coding_task"]
    assert coding["local_gate"] == "PASS"
    assert coding["candidate_entry"].startswith("m-")
    assert coding["merged"] is True and len(coding["merge_sha"]) == 40
    assert coding["final_status"] == "ACCEPTED"
    # U31 honesty: the merged edit is a seeded stand-in, never claimed as a live model edit
    assert coding["from_live_model"] is False
    # invariant 18: the CANDIDATE was promoted by a DIFFERENT node than its author
    assert coding["promoted_by"] != coding["author_node"]

    # 2. one bounded debate (≤5 rounds, dissent preserved verbatim, cost-governed)
    debate = result["debate"]
    assert debate["debate_id"].startswith("d-")
    assert debate["outcome"] == "DISSENT_PRESERVED"
    assert debate["rounds_used"] <= 5
    assert "keep" in debate["dissent"] and "drop" in debate["dissent"]
    assert debate["mcp_entry"].startswith("m-")

    # 3. conductor replacement mid-run: reconstruct into a DIFFERENT mock model, ZERO project loss
    succ = result["succession"]
    assert succ["ok"] is True, succ["reasons"]
    assert succ["predecessor_model"] != succ["successor_model"]
    assert succ["zero_loss"] is True

    # 4. full MCP process restart + recovery over the SAME durable store
    restart = result["restart_recovery"]
    assert restart["ok"] is True, restart["reasons"]
    assert restart["coding_entry_survived"] is True
    assert restart["debate_record_survived"] is True
    assert restart["snapshot_survived"] is True


def test_assembled_run_reports_honest_liveness_no_upgrade(tmp_path, repo):
    """The run CONSUMES the .roster liveness matrix and never upgrades a leg: frontier stays OWED,
    voice stays mock (14D skip), the coding edit stays a deterministic substitute."""
    result = _run(tmp_path, repo, allow_live=False).as_dict()
    live = result["liveness"]
    roles = {r["role"]: r for r in live["roles"]}
    # frontier worker is OWED (no live claude call claimed), conductor is MOCK
    assert roles["frontier_worker"]["owed"] is True
    assert roles["conductor"]["liveness"] == "MOCK"
    # the honest summary names exactly which legs were live vs mock/deterministic + the owed items
    summary = result["honest_summary"]
    assert "frontier" in " ".join(summary["owed"]).lower()
    assert summary["coding_edit_from_live_model"] is False
    assert summary["voice"] == "MOCK_STT (14D skip-with-record — no real Parakeet)"


def test_assembled_run_is_deterministic(tmp_path, repo):
    """Two runs over fresh stores produce the same governed verdicts (no hidden nondeterminism in
    the data path)."""
    r1 = _run(tmp_path / "a", repo, allow_live=False).as_dict()
    # a second, INDEPENDENT fresh repo (not a clone of the now-merged r1 trunk) so the worktree
    # edit is a real change in run 2 as well
    repo2 = _seed_repo(tmp_path / "proj2")
    r2 = run_assembled_scenario(store_dir=tmp_path / "b" / "store", repo_path=repo2,
                                server_factory=_server_factory, allow_live=False).as_dict()
    assert r1["coding_task"]["local_gate"] == r2["coding_task"]["local_gate"] == "PASS"
    assert r1["debate"]["outcome"] == r2["debate"]["outcome"]
    assert r1["succession"]["ok"] == r2["succession"]["ok"] is True


def test_author_cannot_self_promote_candidate_invariant_18(tmp_path):
    """inv 18 enforced LIVE by policy, not by harness convention: the CANDIDATE's author (a worker)
    is REFUSED promotion to ACCEPTED — only a DIFFERENT gate/operator node can promote. The
    assembled run uses a distinct gate node; this proves the refusal it relies on is real."""
    srv = _server_factory(tmp_path / "store")
    try:
        author = McpClient("127.0.0.1", srv.port, srv.credentials.issue("coder-A", "worker", "proj"))
        author.connect()
        pub = author.call("publish", kind="finding", tier="shared_project",
                          content_b64=_b64(b"self-promotion probe"),
                          provenance=_prov("coder-A"), status="CANDIDATE")
        # the author trying to canonize its own work must be denied (gate/operator-only promotion)
        with pytest.raises(McpError):
            author.call("transition", entry_id=pub["entry_id"], requested_status="ACCEPTED")
        author.close()
    finally:
        srv.stop()


# ---- the one live leg: the on-host Ollama receipt inside the assembled run -----------------------

def test_assembled_run_live_ollama_leg_or_skip_with_record(tmp_path, repo):
    """allow_live=True runs the real item-7 Ollama receipt as the assembled run's one genuinely-live
    leg. If the daemon is absent it degrades honestly (available=False) — never faked."""
    result = _run(tmp_path, repo, allow_live=True).as_dict()
    smoke = result["liveness"]["item7_ollama_smoke"]
    if not smoke["available"]:
        pytest.skip(f"Ollama daemon not reachable — live leg SKIP-WITH-RECORD: {smoke['reason']}")
    # daemon present: a real generate must have produced non-empty output, recorded not faked
    assert smoke["generated"] is True
    assert "local_reasoning_worker" in result["liveness"]["live_roles"]
    # the governed data path still holds around the live leg
    assert result["coding_task"]["final_status"] == "ACCEPTED"
    assert result["restart_recovery"]["ok"] is True
