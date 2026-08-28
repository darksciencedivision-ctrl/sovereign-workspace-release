"""Phase 16C `.dispatch` — the governed CONDUCTOR dispatch feed the shell sources on launch.

Proves the emitter drives the REAL governed dispatch (`control_plane.orchestration.live_flow`) through
its full loop (decompose → assign BY DESCRIPTOR → CANDIDATE over MCP → real gate engine → conductor
synthesis) and folds it into the stable `conductor_dispatch_feed@1.0` shell contract — MOCK-first, no
live model call — closing U58 exactly as far as the non-interactive evidence allows:

  * governed happy path ⇒ `dispatched:true`, routing BY DESCRIPTOR (invariant 4), ≥1 gate-ACCEPTED
    artifact (invariant 18 — the GATE node's PASS, not the synthesizer's), HONEST mock-first legs
    (`conductor=mock`, `workers=mock` — never a claimed live worker leg), the packet's
    `operator_disposition` "pending" (gate promotion is NOT operator acceptance, invariant 1), the LIVE
    worker leg recorded OWED (U58), and D-LOOP-1 proven (`torn_down:true`);
  * the pure fold (`fold_dispatch_feed`) is deterministic and invents nothing; a plan-blocked trace
    folds to a fail-closed `dispatched:false` with the plan verdict as the reason;
  * a fault (`build_conductor_dispatch_feed` over a broken store) ⇒ the un-dispatched feed, never a
    fabricated dispatch (invariant 3);
  * `--emit-conductor-dispatch` prints ONLY the feed JSON and exits 0; any other invocation is a
    fail-closed usage error (exit 2).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from control_plane.orchestration.conductor_dispatch import (
    CONDUCTOR_DISPATCH_FEED_SCHEMA,
    DEFAULT_OBJECTIVE,
    DISPATCH_TS,
    build_conductor_dispatch_feed,
    fold_dispatch_feed,
    run_governed_dispatch,
    undispatched_feed,
)
from tools.live.emit_conductor_dispatch import main

ROOT = Path(__file__).resolve().parents[2]
CONDUCTOR_DIR = ROOT / "conductor"


# --- the governed dispatch (real MCP flow, mock-first) -----------------------------

def test_governed_dispatch_runs_by_descriptor_accepts_and_is_mock_honest(tmp_path) -> None:
    feed = run_governed_dispatch(conductor_dir=CONDUCTOR_DIR, store_root=tmp_path)

    assert feed["schema"] == CONDUCTOR_DISPATCH_FEED_SCHEMA
    assert feed["dispatched"] is True
    # invariant 4: assignment is BY DESCRIPTOR — never by node/vendor name
    assert feed["assigned_count"] >= 1
    assert feed["by_descriptor"] is True
    assert all("by descriptor" in a["rationale"] for a in feed["assignments"])
    # invariant 18: the acceptance verdict is the gate node's, and at least one artifact was accepted
    assert feed["accepted_count"] >= 1
    assert feed["acceptance_verdict"] == "PASS"
    assert feed["gate_summary"]["plan"] == "PASS"
    assert feed["gate_summary"]["stage_pass"] >= 1
    # MOCK-FIRST HONESTY: no live worker/conductor leg is claimed
    assert feed["legs"] == {"conductor": "mock", "workers": "mock"}
    # invariant 1: gate promotion is NOT operator acceptance
    assert feed["operator_disposition"] == "pending"
    # U58: the LIVE worker leg is recorded OWED, never faked away
    assert feed["live_workers_owed"]["owed"] is True
    assert feed["live_workers_owed"]["issue"] == "U58"
    # D-LOOP-1: the loopback MCP server + flow were torn down before the feed returned
    assert feed["torn_down"] is True
    # replayable injected ts
    assert feed["ts"] == DISPATCH_TS


def test_governed_dispatch_is_deterministic(tmp_path) -> None:
    """Same objective + fixed injected ts ⇒ identical folded feed (the acceptance packet is replayable
    by design). Two runs in isolated stores must agree bit-for-bit on the governed facts."""
    a = run_governed_dispatch(conductor_dir=CONDUCTOR_DIR, store_root=tmp_path / "a")
    b = run_governed_dispatch(conductor_dir=CONDUCTOR_DIR, store_root=tmp_path / "b")
    # The GOVERNED FACTS are deterministic; `acceptance_packet` is a store-assigned MCP entry id that
    # legitimately varies per server instance, so it is excluded (reporting it as deterministic would
    # be the overclaim — the id is not a governed fact).
    for k in ("assignments", "assigned_count", "by_descriptor", "accepted_count",
              "acceptance_verdict", "legs", "gate_summary", "ts"):
        assert a[k] == b[k], f"non-deterministic field {k!r}"


# --- the pure fold -----------------------------------------------------------------

def test_fold_reports_plan_block_as_undispatched() -> None:
    """A trace whose plan gate FAILED dispatched nothing — the fold says so, fail closed, rather than
    reporting an empty success."""
    trace = {
        "objective": "obj",
        "plan_gate": {"verdict": "FAIL", "kind": "plan"},
        "assignments": [],
        "legs": {"conductor": "mock", "workers": "mock"},
        "gate_records": [],
    }
    feed = fold_dispatch_feed(trace)
    assert feed["dispatched"] is False
    assert "FAIL" in feed["reason"]
    assert feed["assigned_count"] == 0


def test_fold_requires_by_descriptor_on_every_assignment() -> None:
    """`by_descriptor` is true only when EVERY assignment cites the descriptor — one that does not
    (a hypothetical name-based route) drops the flag, so the invariant-4 claim can't be over-reported."""
    trace = {
        "objective": "obj",
        "plan_gate": {"verdict": "PASS", "kind": "plan"},
        "assignments": [
            {"task": "t-1", "node": "worker-A", "rationale": "resolved by descriptor"},
            {"task": "t-2", "node": "worker-B", "rationale": "resolved by node name"},
        ],
        "legs": {"conductor": "mock", "workers": "mock"},
        "gate_records": [],
        "packet": {"accepted_count": 0, "operator_disposition": "pending", "ts": DISPATCH_TS},
    }
    feed = fold_dispatch_feed(trace)
    assert feed["dispatched"] is True     # a plan ran and tasks were routed
    assert feed["by_descriptor"] is False  # but not every route was by descriptor


def test_fold_rejects_non_mapping() -> None:
    with pytest.raises(TypeError):
        fold_dispatch_feed(["not", "a", "mapping"])


# --- fail closed -------------------------------------------------------------------

def test_build_feed_fails_closed_on_setup_fault(tmp_path) -> None:
    """A store_root that cannot host the MCP server ⇒ the un-dispatched feed, never a fabricated
    dispatch (invariant 3). We point store_root at a FILE so `store/` cannot be created under it."""
    afile = tmp_path / "not-a-dir"
    afile.write_text("x", encoding="utf-8")
    feed = build_conductor_dispatch_feed(conductor_dir=CONDUCTOR_DIR, store_root=afile)
    assert feed["dispatched"] is False
    assert feed["reason"]
    assert feed["assignments"] == []
    assert feed["legs"] == {"conductor": "skipped", "workers": "skipped"}
    # U58 is still surfaced even on the failure path
    assert feed["live_workers_owed"]["issue"] == "U58"


def test_undispatched_feed_shape() -> None:
    feed = undispatched_feed("BoomError: kaboom", objective="obj")
    assert feed["schema"] == CONDUCTOR_DISPATCH_FEED_SCHEMA
    assert feed["dispatched"] is False
    assert feed["reason"] == "BoomError: kaboom"
    assert feed["objective"] == "obj"
    assert feed["torn_down"] is True


# --- the CLI contract --------------------------------------------------------------

def test_main_emits_one_json_line(capsys) -> None:
    rc = main(["--emit-conductor-dispatch"])
    assert rc == 0
    out = capsys.readouterr().out
    assert out.count("\n") == 1
    feed = json.loads(out)
    assert feed["schema"] == CONDUCTOR_DISPATCH_FEED_SCHEMA
    # the emitter runs the REAL governed dispatch, mock-first
    assert feed["dispatched"] is True
    assert feed["legs"] == {"conductor": "mock", "workers": "mock"}
    assert feed["live_workers_owed"]["issue"] == "U58"
    assert feed["torn_down"] is True


def test_main_usage_error_is_fail_closed(capsys) -> None:
    rc = main(["--nonsense"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "usage" in err.lower()


# --- Phase 17B `.legs`: the live path exists, and the DEFAULT path must never reach it -----

def test_the_default_path_launches_no_subprocess_at_all(monkeypatch, capsys) -> None:
    """The shell's launch path invokes this emitter with no flag. An app launch may NEVER spend the
    operator's subscription, so the strongest form of the claim is asserted: not "it uses a mock
    backend" but "no process is launched at all" (validator R9 — this was verified by hand and
    unpinned by any test)."""
    import subprocess

    def _forbidden(*a, **k):
        raise AssertionError("the default dispatch path launched a subprocess")

    monkeypatch.setattr(subprocess, "run", _forbidden)
    monkeypatch.setattr(subprocess, "Popen", _forbidden)
    rc = main(["--emit-conductor-dispatch"])
    assert rc == 0
    feed = json.loads(capsys.readouterr().out)
    assert feed["legs"] == {"conductor": "mock", "workers": "mock"}
    assert feed["live_workers_owed"]["owed"] is True
    assert feed["worker_evidence"] == [] and feed["worker_legs"] == {}
    assert "live_run" not in feed, "the mock path must not present itself as a live run"
    assert feed["ts"] == DISPATCH_TS, "the mock path stays replayable"


def test_a_fault_after_a_live_call_still_reports_the_spend(tmp_path) -> None:
    """§6, the under-reporting direction (spec-audit MAJOR-1).

    `undispatched_feed` hard-coded `workers: skipped` / `owed: true`, so a run whose worker had
    ALREADY spent a subscription call and THEN hit a fault — an auth pause, or a second transport
    failure — emitted a feed saying nothing ran. Faults are exactly where under-reporting hides.
    """
    spent_row = [{"node_id": "w-live", "leg": "live", "executed": True, "spent": True,
                  "verified": False, "model": None, "tasks": ["t-1"]}]
    feed = undispatched_feed("BackendAuthPause: rate limited", objective="o",
                             worker_evidence=spent_row, ts="2026-07-26T00:00:00+00:00")

    assert feed["dispatched"] is False                    # still fail-closed about the dispatch
    assert feed["legs"]["workers"] == "attempted"         # ...but the spend is on the record
    assert feed["worker_legs"]["worker:w-live"] == "attempted"
    assert feed["worker_evidence"][0]["spent"] is True
    assert feed["ts"] == "2026-07-26T00:00:00+00:00"

    # and a fault with no live worker behind it is unchanged: nothing ran, nothing claimed
    bare = undispatched_feed("OSError: store unreadable")
    assert bare["legs"] == {"conductor": "skipped", "workers": "skipped"}
    assert bare["worker_evidence"] == [] and bare["live_workers_owed"]["owed"] is True


# --- the live worker is told the criteria it will be judged against (17E `.close`) -------------


def test_the_live_objective_states_the_stage_criteria_and_cannot_self_defeat() -> None:
    """The live worker's scoped context names the gate it faces — and never trips that gate itself.

    17E `.close` measured this: a live `claude` worker answered the bare smoke objective in prose
    containing an informal incompleteness marker, the real STAGE gate refused the artifact on
    `no_placeholders` (a CRITICAL criterion), and the assembled leg went red on a live answer that
    was otherwise perfectly good work. The node was judged by a rule nobody gave it. Telling it the
    criteria is scoped need-to-know (Plan §9), NOT a softened gate: the gate still computes its
    verdict from the published bytes and still refuses an artifact that trips one.

    The trap this test exists for: the objective travels INTO the artifact body
    (`ModelWorkerAdapter.execute`), so a brief that spelled out the marker words would make
    `no_placeholders` fail on EVERY run, for the text of the instruction itself.

    Two corrections from the 17E `.close` spec-audit are pinned below. (M3) The refusal run the
    docs cite as evidence that this gate refuses live work was produced under the BARE objective —
    it is evidence about the gate FUNCTION, not about the briefed path. (m1) The brief must not tell
    the node it is judged on `claims_cite_evidence`: that criterion reads the ADAPTER's generated
    claim records, which the node's prose cannot affect. Only `no_placeholders` binds its wording.
    """
    from control_plane.gates.criteria import GateContext, evaluate_criterion
    from control_plane.orchestration.live_flow import STAGE_CRITERIA
    from tools.live.emit_conductor_dispatch import LIVE_WORKER_OBJECTIVE

    # it names every criterion the stage gate will apply, derived from the same constant
    for criterion in STAGE_CRITERIA:
        assert criterion in LIVE_WORKER_OBJECTIVE, f"the brief does not name {criterion}"

    # ...and the brief itself passes the criterion it describes, judged by the REAL gate function
    result = evaluate_criterion(
        "no_placeholders",
        GateContext(artifact_content=LIVE_WORKER_OBJECTIVE.encode("utf-8"), structured_output={}))
    assert result.passed, f"the brief trips the gate it describes: {result.reason}"

    # it still asks for the same smoke-scale work, so the live exchange stays minimal
    assert DEFAULT_OBJECTIVE in LIVE_WORKER_OBJECTIVE

    # (m1) it claims exactly ONE criterion binds the node's wording, because exactly one does:
    # `claims_cite_evidence` evaluates `structured_output["claims"]`, which the adapter fabricates.
    assert "One of those binds your wording" in LIVE_WORKER_OBJECTIVE
    assert "every claim you make" not in LIVE_WORKER_OBJECTIVE
    # ...proven by holding the claim records fixed and varying the prose: the verdict does not move.
    cited = {"claims": [{"text": "the roster is capability-keyed", "evidence_refs": ["m-1"]}]}
    verdicts = {evaluate_criterion("claims_cite_evidence",
                                   GateContext(artifact_content=prose, structured_output=cited)).passed
                for prose in (b"careful settled prose", b"reckless unsupported assertions")}
    assert verdicts == {True}, ("the brief would be wrong about which criteria the node can trip: "
                                "claims_cite_evidence moved with the node's wording")


def test_the_cited_refusal_run_was_produced_under_the_BARE_objective(repo_root: Path = ROOT) -> None:
    """The published refusal is evidence about the gate FUNCTION, not about the briefed path (M3).

    `PHASE17E_DISPATCH_GATE_REFUSAL_20260731T1513Z.json` is cited in three places as proof that this
    gate still refuses live work. It does prove that — a VERIFIED live checkpoint published a
    CANDIDATE and the STAGE gate refused it. What it cannot prove is anything about the CHANGED path,
    because it predates the brief. This test fails if anyone ever re-labels that file as evidence
    about the briefed configuration by quietly swapping its objective.
    """
    from tools.live.emit_conductor_dispatch import LIVE_WORKER_OBJECTIVE

    refusal = json.loads((repo_root / "docs" / "evidence" / "live"
                          / "PHASE17E_DISPATCH_GATE_REFUSAL_20260731T1513Z.json")
                         .read_text(encoding="utf-8"))
    assert refusal["objective"] == DEFAULT_OBJECTIVE
    assert refusal["objective"] != LIVE_WORKER_OBJECTIVE
    # ...and it is a genuine refusal of a genuine live artifact, which is why it is kept
    assert refusal["acceptance_verdict"] == "FAIL" and refusal["accepted_count"] == 0
    assert refusal["gate_summary"]["stage_pass"] == 0 and refusal["gate_summary"]["stage_total"] == 1
    assert any(r["leg"] == "live" and r["verified"] is True for r in refusal["worker_evidence"])


def test_the_u58_record_never_narrates_the_gate(tmp_path) -> None:
    """`live_workers_record` cannot observe the gate, so it must not describe it (spec-audit H2).

    The literal used to read "the real gate engine accepted it" and was emitted verbatim onto the
    refusal feed above, where `acceptance_verdict` is FAIL — a published evidence artifact carrying a
    sentence its own data falsifies (invariant 11). The record's subject is the WORKER leg (U58).
    """
    from control_plane.orchestration.conductor_dispatch import LIVE_WORKERS_MET, live_workers_record

    for text in (LIVE_WORKERS_MET["note"],
                 live_workers_record({"workers": "live"},
                                     [{"node_id": "w", "verified": True}])["note"]):
        low = text.lower()
        assert "accepted it" not in low and "gate engine accepted" not in low
        # it points at the fields that DO carry the gate's verdict, so the reader is not left guessing
        assert "acceptance_verdict" in text and "gate_summary" in text

    # unchanged where it matters: the discharge still requires BOTH reads, and stays owed otherwise
    assert live_workers_record({"workers": "live"}, [{"node_id": "w", "verified": False}])["owed"] is True
    assert live_workers_record({"workers": "mock"}, [{"node_id": "w", "verified": True}])["owed"] is True


def test_the_mock_path_objective_is_unchanged_by_the_live_brief(tmp_path) -> None:
    """The brief is the LIVE path's scoped context only: the shell's launch dispatch — the one every
    ordinary app start runs — keeps the replayable objective its receipts were folded from."""
    from tools.live.emit_conductor_dispatch import LIVE_WORKER_OBJECTIVE

    feed = run_governed_dispatch(conductor_dir=CONDUCTOR_DIR, store_root=tmp_path)
    assert feed["objective"] == DEFAULT_OBJECTIVE
    assert feed["objective"] != LIVE_WORKER_OBJECTIVE


def test_the_live_brief_does_not_break_the_gates_it_describes(tmp_path) -> None:
    """End-to-end, with mock workers: the brief's own text travels into the artifact and the
    acceptance packet, so a governed dispatch carrying it must still reach an ACCEPTED artifact.

    A unit assertion on `no_placeholders` alone would miss the packet-level acceptance gate, which
    reads the same objective back out of the synthesis. No live call is made here — the point is the
    TEXT, and it is the same text the live path sends."""
    from tools.live.emit_conductor_dispatch import LIVE_WORKER_OBJECTIVE

    feed = run_governed_dispatch(conductor_dir=CONDUCTOR_DIR, store_root=tmp_path,
                                 objective=LIVE_WORKER_OBJECTIVE)
    assert feed["dispatched"] is True
    assert feed["accepted_count"] >= 1
    assert feed["acceptance_verdict"] == "PASS"
    assert feed["gate_summary"]["stage_pass"] >= 1
