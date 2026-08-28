"""Phase 15D `.succession` — a REAL conductor succession over a REAL governed run.

Directive §11 15D: "kill the Fable-5 conductor mid-run, resume on a different backend, zero loss,
then restore selection." Nothing here is simulated except the model backends: a real MCP server,
the real Scheduler, the real GateEngine, the real `SuccessionManager` (Phase 11) and the real
`LiveGovernedFlow` (`.flow`). The conductor that finishes the run is a SEPARATELY CONSTRUCTED
adapter on a different backend, holding a different MCP session, that reloaded all 12 conductor
files from shared memory.

MOCK-FIRST (§10.4): no `claude` process is spawned by this suite — pinned by an explicit
subprocess ban below — and a mock succession can never be packaged as a live one.
"""
from __future__ import annotations

import base64
import json
import subprocess
from pathlib import Path

import pytest

from adapters.base.mock_backend import MockReasoningBackend
from adapters.conductor import publish_conductor_files
from adapters.conductor.adapter import CONDUCTOR_FILE_ORDER, ConductorNotReady
from control_plane.conductor.selection import OPERATOR_SELECTED_CONDUCTOR
from control_plane.orchestration.live_succession import (
    LiveConductorSuccession,
    SuccessionError,
    capture_project_snapshot,
    compare_zero_loss,
    mock_predecessor_handle,
    mock_successor_handle,
)
from mcp_server.protocol import McpClient
from mcp_server.server import MCPServer
from node_runtime.supervisor.subscription_governor import SubscriptionGovernor

ROOT = Path(__file__).resolve().parents[2]
CONDUCTOR_DIR = ROOT / "conductor"
OBJECTIVE = "Design the offline conductor roster"
SUBSCRIPTION = "sub-anthropic-1"


class _ChainedPlanBackend(MockReasoningBackend):
    """A deterministic decomposition whose later tasks DEPEND on the first.

    This is what makes the kill genuinely MID-RUN: task 1 runs in wave 1, tasks 2 and 3 only
    become READY once it reaches DONE, so the work the successor completes is work the
    predecessor never saw. With a dependency-free plan the whole graph would finish in one wave
    and the "succession" would have nothing left to resume.
    """

    def propose_plan(self, objective, files, cycle):
        plan = super().propose_plan(objective, files, cycle)
        plan["proposed_tasks"] = [
            {"desc": f"stage 1 of: {objective}", "capability": "reasoning"},
            {"desc": f"stage 2 of: {objective}", "capability": "coding", "deps": [1]},
            {"desc": f"stage 3 of: {objective}", "capability": "reasoning", "deps": [1]},
        ]
        return plan


class _SequentialPlanBackend(MockReasoningBackend):
    """A STRICTLY sequential chain: t1 -> t2 -> t3, one task per wave.

    `_ChainedPlanBackend` is only two levels deep (t2 and t3 both depend on t1), so it quiesces in
    two waves and cannot exercise a wave bound set below the chain length. This one needs three
    waves, which is what makes the wave-budget arithmetic observable.
    """

    def propose_plan(self, objective, files, cycle):
        plan = super().propose_plan(objective, files, cycle)
        plan["proposed_tasks"] = [
            {"desc": f"stage 1 of: {objective}", "capability": "reasoning"},
            {"desc": f"stage 2 of: {objective}", "capability": "reasoning", "deps": [1]},
            {"desc": f"stage 3 of: {objective}", "capability": "reasoning", "deps": [2]},
        ]
        return plan


@pytest.fixture()
def env(tmp_path):
    srv = MCPServer(tmp_path / "store")
    srv.start()
    op = McpClient("127.0.0.1", srv.port, srv.credentials.issue("op-boot", "operator", "proj"))
    op.connect()
    manifest = publish_conductor_files(op, "op-boot", CONDUCTOR_DIR)
    op.close()
    yield {"srv": srv, "manifest": manifest}
    srv.stop()


def _reader(srv):
    c = McpClient("127.0.0.1", srv.port, srv.credentials.issue("audit", "operator", "proj"))
    c.connect()
    return c


def _succession(env, *, governor=None, subscription_ref=None, predecessor_backend=None,
                successor_factory=None):
    """Build the runner. Both conductors are constructed BY THE RUNNER from clients it owns, so the
    kill actually closes the predecessor's MCP session."""
    manifest = env["manifest"]
    return LiveConductorSuccession(
        env["srv"], manifest,
        predecessor_factory=lambda c: mock_predecessor_handle(
            c, manifest, governor=governor, subscription_ref=subscription_ref,
            backend=(predecessor_backend if predecessor_backend is not None
                     else _ChainedPlanBackend())),
        successor_factory=successor_factory or (lambda c: mock_successor_handle(
            c, manifest, governor=governor, subscription_ref=subscription_ref)),
        governor=governor, subscription_ref=subscription_ref)


# --- the headline criterion ------------------------------------------------------------

def test_kill_conductor_mid_run_resume_on_different_backend_with_zero_loss(env) -> None:
    outcome = _succession(env).run(OBJECTIVE, kill_after_waves=1)

    assert outcome.ran is True and outcome.published is True
    assert outcome.skipped_with_record is False, outcome.reason

    # (1) the succession really happened, onto a DIFFERENT backend
    report = outcome.report
    assert report["predecessor"]["model_name"] == "mock-fable5"
    assert report["successor"]["model_name"] == "mock-successor"
    assert report["predecessor"]["node_id"] != report["successor"]["node_id"]

    # (2) ZERO LOSS — and non-vacuously: real artifacts existed before the kill
    assert outcome.zero_loss.ok is True, outcome.zero_loss.checks
    assert outcome.zero_loss.checks["pre_kill_accepted_count"] > 0
    assert outcome.zero_loss.checks["missing_entries"] == []
    assert outcome.zero_loss.checks["drifted_entries"] == []

    # (3) the successor COMPLETED work the predecessor never saw (a real mid-run resume): the
    #     accepted set GREW after the kill, so the successor did not merely re-publish a summary
    assert (outcome.zero_loss.checks["post_succession_accepted_count"]
            > outcome.zero_loss.checks["pre_kill_accepted_count"])

    # (4) the §19.1 staleness checklist passed — the successor was cleared to assign work
    assert report["staleness"]["ok"] is True, report["staleness"]["failed_checks"]

    # (5) the operator's selection was RESTORED after the succession
    assert report["restored_selection"]["model"] == OPERATOR_SELECTED_CONDUCTOR.model
    assert report["restored_selection"]["reason"] == "operator_selected"

    # (6) it is recorded as a mock succession, never a live one (§10.4)
    assert report["run_spend_leg"] == "mock"
    assert outcome.legs == {"conductor_predecessor": "mock",
                            # `skipped`, not `mock`: see the dedicated test below — the successor
                            # never invoked its model, and the leg vocabulary reports model SPEND
                            "conductor_successor": "skipped",
                            "workers": "mock"}


def test_the_packet_covers_pre_and_post_kill_work_and_the_swap_is_recorded(env) -> None:
    """RENAMED: the old name claimed the SUCCESSOR synthesized the packet, which this body never
    checked — a mutant in which the closed predecessor synthesized it passed here unnoticed. That
    fact is pinned by `test_the_packet_was_authored_by_the_SUCCESSOR_node_in_mcp_provenance`;
    this test covers the packet's CONTENTS and the recorded swap.
    """
    outcome = _succession(env).run(OBJECTIVE, kill_after_waves=1)
    trace = outcome.trace

    # the packet was synthesized AFTER the swap, so its conductor is the successor
    assert trace["conductor_swaps"], "the run records no conductor swap"
    assert trace["conductor_swaps"][-1]["selection"]["selection"]["reason"] == "succession"

    # every task in the graph reached a terminal state, including the ones only the successor ran
    packet = trace["packet"]
    assert packet["accepted_count"] >= 2
    accepted_tasks = {row["task_id"] for row in packet["accepted"]}
    assert len(accepted_tasks) >= 2, packet["task_states"]
    # the pre-kill task's artifact is IN the successor's packet — the successor accepted work it
    # did not itself commission, read back from shared memory
    assert "t-1" in accepted_tasks


# --- the kill is real ------------------------------------------------------------------

def test_the_predecessor_is_actually_dead_after_the_kill(env) -> None:
    """Not "we stopped calling it" — its session is closed and its adapter refuses to act."""
    runner = _succession(env)
    outcome = runner.run(OBJECTIVE, kill_after_waves=1)
    assert outcome.ran is True, outcome.reason
    handle = runner.predecessor_handle           # the real object the run used

    # the adapter is no longer ACTIVE, so it cannot run a conductor cycle (fail closed)
    assert handle.adapter.is_active is False
    with pytest.raises(ConductorNotReady):
        handle.adapter.run_cycle(OBJECTIVE)
    # its loaded files are still in memory — which is exactly why `ready` is NOT a liveness signal
    # and why the death evidence reads `is_active` instead
    assert handle.adapter.get_context_status()["ready"] is True
    assert outcome.trace["succession"]["predecessor_dead"]["is_active"] is False


def test_the_successor_reloaded_all_twelve_conductor_files_from_mcp(env) -> None:
    """Zero loss is only meaningful because the successor rebuilt its context from SHARED MEMORY —
    it inherits nothing from the predecessor's session (invariant 5)."""
    runner = _succession(env)
    outcome = runner.run(OBJECTIVE, kill_after_waves=1)

    assert outcome.ran is True, outcome.reason
    assert runner.successor_handle.adapter.loaded_files == CONDUCTOR_FILE_ORDER


# --- governance around the succession ---------------------------------------------------

def test_ix3_handoff_releases_the_predecessor_terminal_before_the_successor_acquires(env) -> None:
    governor = SubscriptionGovernor()
    governor.register_subscription(SUBSCRIPTION, "claude_code", allowance=1)

    outcome = _succession(env, governor=governor, subscription_ref=SUBSCRIPTION).run(
        OBJECTIVE, kill_after_waves=1)

    assert outcome.ran is True, outcome.reason
    # observed on the real governor, not asserted by the caller
    assert outcome.report["handoff_order"] == ["release", "acquire"]
    assert "release-before-acquire observed" in outcome.report["handoff_note"]
    # allowance=1 held throughout: the succession never ran two terminals at once
    assert governor.active_count(SUBSCRIPTION) <= 1


def test_the_succession_report_is_promoted_by_a_gate_node_not_by_its_author(env) -> None:
    """Invariant 18: no node solely judges its own work. The successor authored the report; the
    gate node read the stored bytes back and decided."""
    outcome = _succession(env).run(OBJECTIVE, kill_after_waves=1)
    reader = _reader(env["srv"])

    entry_id = outcome.report_entry
    stored = json.loads(base64.b64decode(
        reader.call("get_content", entry_id=entry_id)["content_b64"]))
    assert stored["schema"] == "succession_report@1.0"

    accepted = {e["entry_id"] for e in reader.call("read_status", status="ACCEPTED")}
    assert entry_id in accepted                       # the gate promoted it
    verdict = outcome.trace["succession"]["report_gate"]
    assert verdict["decided_by"] == "gate_engine"
    assert verdict["schema"] == "gate@1.0"
    # gate promotion is NOT operator acceptance (invariant 1)
    assert stored["operator_disposition"] == "pending"
    reader.close()


def test_the_snapshot_the_successor_reconstructed_from_is_durable_in_mcp(env) -> None:
    outcome = _succession(env).run(OBJECTIVE, kill_after_waves=1)
    reader = _reader(env["srv"])
    snapshot_entry = outcome.trace["succession"]["snapshot_entry"]
    doc = json.loads(base64.b64decode(
        reader.call("get_content", entry_id=snapshot_entry)["content_b64"]))
    assert doc["checkpoint"]["kind"] == "succession_snapshot"
    assert doc["checkpoint"]["conductor"]["model"] == OPERATOR_SELECTED_CONDUCTOR.model
    assert doc["state"]["memory_heads"], "the snapshot pinned no memory heads"
    reader.close()


# --- honesty ---------------------------------------------------------------------------

def test_a_run_with_nothing_left_to_resume_is_skip_with_record_not_a_succession(env) -> None:
    """A dependency-free plan finishes in one wave. Killing the conductor afterwards demonstrates
    no MID-RUN succession, and the runner says so instead of reporting one."""
    outcome = _succession(env, predecessor_backend=MockReasoningBackend()).run(
        OBJECTIVE, kill_after_waves=8)
    assert outcome.ran is False
    assert outcome.skipped_with_record is True
    assert "not a mid-run succession" in outcome.reason
    assert outcome.report is None


def test_interrupting_and_resuming_a_run_does_not_buy_it_extra_waves(env) -> None:
    """Kills a surviving mutant. The `.flow`-gated structural bound `_max_waves` is on the WHOLE
    run; `run_waves` subtracts `waves_run` so a resumed run gets the same TOTAL budget an
    uninterrupted one does. Dropping the subtraction was invisible to the entire suite, which would
    let a succession quietly extend a bounded run.

    The bound must be made to BIND for this to discriminate: normally quiescence fires first
    (`_max_waves(n) = n + 1` while the longest dependency chain is `n`), so with the real bound an
    interrupted and an uninterrupted run finish identically whether or not the subtraction is
    there. Patching the bound below the chain length is what exposes the arithmetic.
    """
    import control_plane.orchestration.live_flow as lf
    from control_plane.orchestration.live_flow import LiveGovernedFlow

    def _run(interrupt: bool) -> int:
        # the client's identity must BE the publishing node — MCP enforces
        # provenance.author_node == the publishing node (invariant 11)
        srv = env["srv"]
        client = McpClient("127.0.0.1", srv.port,
                           srv.credentials.issue("conductor-fable5", "conductor", "proj"))
        client.connect()
        flow = LiveGovernedFlow(
            srv, env["manifest"],
            conductor_handle=mock_predecessor_handle(client, env["manifest"],
                                                     backend=_SequentialPlanBackend()))
        try:
            flow.begin(OBJECTIVE)
            if interrupt:
                flow.run_waves(max_waves=1)
            flow.run_waves()
            return flow._run.waves_run
        finally:
            flow.close()
            client.close()

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(lf, "_max_waves", lambda n: 2)     # below the 3-task chain, so the bound binds
        uninterrupted = _run(interrupt=False)
        interrupted = _run(interrupt=True)

    assert interrupted == uninterrupted == 2, (interrupted, uninterrupted)


def test_capture_project_snapshot_hashes_the_bytes_mcp_actually_stored(env) -> None:
    """The comparison must not trust a publisher's own `content_hash` claim (I-M1)."""
    import hashlib

    op = _reader(env["srv"])
    payload = b"an accepted finding"
    entry = op.call("publish", kind="finding", tier="shared_project",
                    content_b64=base64.b64encode(payload).decode("ascii"),
                    provenance={"author_node": "audit", "task_id": None,
                                "ts": "2026-07-20T00:00:00+00:00",
                                "directive_version": "v2.4", "confidence": "high"},
                    status="ACCEPTED")
    snap = capture_project_snapshot(op, {})
    assert snap["accepted"][entry["entry_id"]] == "sha256:" + hashlib.sha256(payload).hexdigest()
    op.close()


def test_the_zero_loss_verdict_flips_when_a_real_captured_artifact_goes_missing(env) -> None:
    """Load-bearing check: the comparison is run against REAL captured snapshots, then one entry is
    removed from the 'after' side. A comparison that always returned ok would not notice."""
    outcome = _succession(env).run(OBJECTIVE, kill_after_waves=1)
    reader = _reader(env["srv"])
    after = capture_project_snapshot(reader, {})
    before = {"accepted": dict(after["accepted"]), "task_states": {}}
    victim = sorted(after["accepted"])[0]
    del after["accepted"][victim]

    assert compare_zero_loss(before, after).ok is False
    assert compare_zero_loss(before, before).ok is True          # control: unmodified passes
    assert outcome.zero_loss.ok is True
    reader.close()


def test_the_successor_leg_is_skipped_because_synthesis_never_invokes_a_model(env) -> None:
    """A STATED LIMIT of this unit, not an accident (recorded as U46).

    `LiveGovernedFlow._synthesize` assembles the acceptance packet deterministically from MCP reads
    and gate records — it never calls the conductor's backend. So the successor conducts (loads its
    12 files, reads the ACCEPTED set, publishes, is gated) without ever spending a model call, and
    the leg vocabulary — which reports MODEL SPEND, not activity — correctly says `skipped`.

    The consequence to be honest about: this succession proves the GOVERNED handover end to end, it
    does not yet prove a successor's MODEL producing a synthesis. That needs a decomposition cycle
    on the successor, which is owed to the live smoke.
    """
    runner = _succession(env)
    outcome = runner.run(OBJECTIVE, kill_after_waves=1)

    assert outcome.report["successor"]["leg"] == "skipped"
    assert outcome.report["successor"]["calls_spent"] == 0
    assert runner.successor_handle.adapter.backend.calls == 0
    # the predecessor, by contrast, DID spend a (mock) call to decompose
    assert outcome.report["predecessor"]["calls_spent"] >= 1
    # and the successor nonetheless did real conductor work: it published the packet
    assert outcome.acceptance_packet


def test_a_kill_that_did_not_happen_is_REFUSED_not_reported(env) -> None:
    """The sharpest guard in this unit, and the one a gate-validator defeated in review.

    With `close()` neutered the predecessor survives the "kill". Before the fix, `_death_evidence`
    merely RECORDED `is_active: True` while the run published a gate-ACCEPTED report carrying the
    claim "the conductor was replaced mid-run with no loss of gated project state". A recorded-but-
    unchecked death field is not a guard, so the runner now refuses.
    """
    def _factory(client):
        handle = mock_predecessor_handle(client, env["manifest"], backend=_ChainedPlanBackend())
        handle.adapter.close = lambda: None          # the kill does nothing
        return handle

    runner = LiveConductorSuccession(
        env["srv"], env["manifest"], predecessor_factory=_factory,
        successor_factory=lambda c: mock_successor_handle(c, env["manifest"]))
    outcome = runner.run(OBJECTIVE, kill_after_waves=1)

    assert outcome.ran is False and outcome.published is False
    assert outcome.report is None                    # nothing was emitted to MCP
    assert outcome.governance_refusal is True        # a defect, not an environmental skip
    assert "still active after close()" in outcome.reason
    # the predecessor really was still alive — i.e. the test's premise held
    assert runner.predecessor_handle.adapter.is_active is True


def test_a_failed_staleness_checklist_stops_the_successor_before_it_assigns_work(env) -> None:
    """§19.1 gates the successor. Previously the checklist was computed, stored in the report and
    then ignored while `run_waves()` was called unconditionally on the next line."""
    from control_plane.recovery import succession as succession_mod

    real = succession_mod.SuccessionManager.reconstruct

    def _stale(self, **kw):
        state, checklist = real(self, **kw)
        # `ok` is the verdict field, computed independently of `checks` — patching `checks` alone
        # left `ok` True and the successor ran anyway, which is exactly the defect under test.
        object.__setattr__(checklist, "ok", False)
        return state, checklist

    runner = _succession(env)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(succession_mod.SuccessionManager, "reconstruct", _stale)
        outcome = runner.run(OBJECTIVE, kill_after_waves=1)

    assert outcome.ran is False and outcome.published is False
    assert outcome.governance_refusal is True
    assert "staleness checklist REFUSED" in outcome.reason


def test_the_packet_was_authored_by_the_SUCCESSOR_node_in_mcp_provenance(env) -> None:
    """Kills the mutation survivor that mattered most in review: with `swap_conductor`'s rebind
    removed, the CLOSED PREDECESSOR synthesized and published the acceptance packet and the whole
    suite still passed. The packet's own `synthesized_by` field cannot detect this — it is
    `capability().adapter`, the same constant for both conductors — so the only real evidence is
    MCP provenance, which the author cannot forge (invariant 11).
    """
    runner = _succession(env)
    outcome = runner.run(OBJECTIVE, kill_after_waves=1)
    assert outcome.ran is True, outcome.reason

    reader = _reader(env["srv"])
    rows = {e["entry_id"]: e for e in reader.call("read_status", status="ACCEPTED")}
    author = rows[outcome.acceptance_packet]["provenance"]["author_node"]
    assert author == runner.successor_handle.adapter.context.node_id
    assert author != runner.predecessor_handle.adapter.context.node_id
    reader.close()


def test_death_evidence_reports_real_liveness_not_file_load_status(env) -> None:
    """Kills a surviving mutant: `_death_evidence["is_active"]` could be silently decoupled from
    `adapter.is_active` (e.g. computed from `not status["ready"]`) with no test noticing."""
    runner = _succession(env)
    outcome = runner.run(OBJECTIVE, kill_after_waves=1)

    evidence = outcome.trace["succession"]["predecessor_dead"]
    assert evidence["is_active"] is False
    assert evidence["files_loaded"] is True

    # The post-kill pair above is NOT sufficient to pin this: on a closed conductor `is_active` is
    # False and `not ready` is also False, so a decoupled implementation reads identically. The
    # discriminating case is a LIVE adapter, where `is_active` is True while `not ready` is False.
    live = runner.successor_handle.adapter
    live.start() if not live.is_active else None
    live_evidence = LiveConductorSuccession._death_evidence(live)
    assert live_evidence["is_active"] is True
    assert live_evidence["files_loaded"] is True
    live.close()


def test_the_mock_helpers_refuse_a_real_vendor_backend(env) -> None:
    """They hard-code `leg="mock"` and overwrite `model_name`, so a real vendor backend passed here
    would record a genuine subscription spend as mock (§6). This unit has no live path (U51)."""
    class ClaudeCliBackend:                      # matched by NAME, as the guard documents
        model_name = "claude-fable-5"

    op = _reader(env["srv"])
    with pytest.raises(SuccessionError, match="live vendor backend"):
        mock_predecessor_handle(op, env["manifest"], backend=ClaudeCliBackend())
    op.close()


def test_the_report_says_plainly_that_no_conductor_was_rebound_to_the_restored_selection(env) -> None:
    """`restored_selection` is `{model: fable-5, adapter: claude_code}`. Without the note an
    operator concludes a claude_code conductor finished the run — in a run that spawned no vendor
    CLI at all (invariant 3)."""
    outcome = _succession(env).run(OBJECTIVE, kill_after_waves=1)
    note = outcome.report["restored_selection_note"]
    assert "no conductor was re-bound" in note
    # and the conductor that actually finished is recorded as the successor
    assert outcome.report["successor"]["model_name"] == "mock-successor"


def test_a_promotion_that_lost_its_CAS_is_refused_not_reported_as_published(env) -> None:
    """Invariant 13: no silent last-write-wins. If the report's promotion is not applied, its MCP
    status never changed, so `published=True` would be a false statement about durable state."""
    real_call = McpClient.call

    def _lose_cas(self, op, **args):
        result = real_call(self, op, **args)
        if op == "transition" and args.get("requested_status") in ("ACCEPTED", "REJECTED"):
            return {"applied": False, "conflict": "simulated concurrent writer"}
        return result

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(McpClient, "call", _lose_cas)
        outcome = _succession(env).run(OBJECTIVE, kill_after_waves=1)

    assert outcome.published is False
    assert outcome.governance_refusal is True
    assert "CAS conflict" in outcome.reason


def test_the_outcome_carries_the_succession_gate_verdict(env) -> None:
    """`published` says the record reached MCP, not that the gate accepted it (invariant 16)."""
    outcome = _succession(env).run(OBJECTIVE, kill_after_waves=1)
    assert outcome.report_verdict in ("PASS", "PASS_WITH_RESERVATIONS")
    assert outcome.governance_refusal is False


def test_no_leg_in_this_MOCK_FIRST_suite_can_reach_live(env) -> None:
    outcome = _succession(env).run(OBJECTIVE, kill_after_waves=1)
    assert outcome.report["run_spend_leg"] != "live"
    assert outcome.report["predecessor"]["verification"] is None
    assert outcome.report["successor"]["verification"] is None


def test_predecessor_party_reports_the_REBOUND_selection_record_not_the_pre_call_one(env) -> None:
    """U62 (discharged at `phase-15d.gate`). `LiveGovernedFlow.begin()` REBINDS the conductor
    handle with a post-CLI selection record when the handle carries a `rebind` (the live binding
    recomputes the EXECUTING checkpoint after the decompose call). If `run()` reports the
    predecessor from the handle it captured BEFORE `begin()`, the party echoes a STALE
    `selection.executing` mirror beside a freshly-correct `verification`. This pins that the
    predecessor party reads the rebound record.

    Mock-first: the rebind carries a NEUTRAL marker (an unverified reported checkpoint, `verified`
    stays False), so no `live`/verified claim is manufactured — the test discriminates purely on
    WHICH selection record the party echoed.
    """
    from dataclasses import replace

    marker_note = "REBOUND-POST-CLI-MARKER"

    def _rebinding_predecessor(client):
        base = mock_predecessor_handle(client, env["manifest"], backend=_ChainedPlanBackend())
        pre = base.selection_record
        assert pre["executing"]["note"] != marker_note          # the two records really differ
        post = json.loads(json.dumps(pre))                      # deep copy
        post["executing"]["note"] = marker_note
        post["executing"]["reported_unverified"] = "opus-4-8[1m]-unverified"
        # verified stays False — a mock rebind cannot verify; this proves the READ, not a live leg
        return replace(base, selection_record=pre, rebind=lambda _adapter: post)

    runner = LiveConductorSuccession(
        env["srv"], env["manifest"],
        predecessor_factory=_rebinding_predecessor,
        successor_factory=lambda c: mock_successor_handle(c, env["manifest"]))
    outcome = runner.run(OBJECTIVE, kill_after_waves=1)

    assert outcome.ran is True, outcome.reason
    executing = outcome.report["predecessor"]["selection"]["executing"]
    assert executing["note"] == marker_note, "party echoed the PRE-rebind selection record (U62)"
    assert executing["reported_unverified"] == "opus-4-8[1m]-unverified"
    # the honesty rules still hold: an unverified rebind is not a live leg
    assert executing["verified"] is False
    assert outcome.report["predecessor"]["leg"] == "mock"
    assert outcome.report["predecessor"]["verification"] is None


def test_the_whole_succession_spawns_no_subprocess(env, monkeypatch) -> None:
    """The ban is hooked at `subprocess.Popen`, BELOW anything that patches `subprocess.run`, so a
    provider CLI cannot be reached by any route this run takes (§10.4)."""
    spawned: list = []

    def _banned(*args, **kwargs):
        spawned.append(args)
        raise AssertionError(f"MOCK-FIRST violated: a subprocess was spawned: {args!r}")

    monkeypatch.setattr(subprocess, "Popen", _banned)
    outcome = _succession(env).run(OBJECTIVE, kill_after_waves=1)
    assert outcome.ran is True, outcome.reason
    assert spawned == []
