"""Phase 15D `.flow` — the full governed loop end to end over a REAL MCP server, the REAL
scheduler, and the REAL gate engine, driven through the LIVE-capable conductor binding.

Directive §11 15D: conductor decomposes an objective -> Scheduler assigns BY CAPABILITY ->
workers publish CANDIDATE over MCP -> gates -> conductor SYNTHESIZES the ACCEPTED set into an
acceptance packet, carrying the conductor SELECTION on the result.

MOCK-FIRST (§10.4): the governed path is proven with a mock backend; the LIVE leg is
skip-with-record — no `claude` process is spawned by this suite, and a mock run can never be
packaged as live (`build_acceptance_packet` refuses).
"""
from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from adapters.base.backend import BackendAuthPause
from adapters.conductor import publish_conductor_files
from adapters.frontier.claude_code import ClaudeCliBackend, MockClaudeCliBackend
from control_plane.orchestration.live_flow import (
    AcceptancePacketError,
    LiveGovernedFlow,
    attempt_live_flow,
    build_acceptance_packet,
    decompose_plan,
)
from control_plane.profiles.live_authorization import load_live_authorization
from control_plane.profiles.loader import DeploymentProfile, ProfileLoader
from control_plane.tasks.graph import TaskState
from mcp_server.protocol import McpClient
from mcp_server.server import MCPServer
from node_runtime.supervisor.subscription_governor import SubscriptionGovernor

ROOT = Path(__file__).resolve().parents[2]
CONDUCTOR_DIR = ROOT / "conductor"
OBJECTIVE = "Design the offline conductor roster"

# OP-6 two-provider live scope (identical to the adapter/conductor suites)
_VALID_AUTH = {"config_version": "1.1", "live_operation_authorized": True, "register_row": "OP-6",
               "scope": {"providers": ["claude_code", "openai_codex_cli"],
                         "terminals_per_subscription": 2}}


@pytest.fixture()
def flow(tmp_path):
    srv = MCPServer(tmp_path / "store")
    srv.start()
    op = McpClient("127.0.0.1", srv.port, srv.credentials.issue("op-boot", "operator", "proj"))
    op.connect()
    manifest = publish_conductor_files(op, "op-boot", CONDUCTOR_DIR)
    op.close()
    f = LiveGovernedFlow(srv, manifest)
    yield {"srv": srv, "flow": f, "manifest": manifest}
    f.close()
    srv.stop()


def _reader(srv):
    c = McpClient("127.0.0.1", srv.port, srv.credentials.issue("audit", "operator", "proj"))
    c.connect()
    return c


# --- the governed loop -------------------------------------------------------------

def test_full_governed_loop_decompose_assign_candidate_gate_synthesize(flow) -> None:
    trace = flow["flow"].run(OBJECTIVE)

    # (b) the CONDUCTOR's own decomposition drives the graph — not hard-coded task ids
    decomp = trace["decomposition"]
    assert decomp["accepted_count"] >= 2
    assert [t["task_id"] for t in decomp["tasks"]] == [f"t-{i + 1}" for i in range(decomp["accepted_count"])]

    # (c) the plan gate is a REAL gate@1.0 record from the gate engine, not a stand-in publish
    assert trace["plan_gate"]["schema"] == "gate@1.0"
    assert trace["plan_gate"]["decided_by"] == "gate_engine"
    assert trace["plan_gate"]["kind"] == "plan" and trace["plan_gate"]["verdict"] == "PASS"

    # (d) assignment is BY DESCRIPTOR (invariant 4) — never by node/vendor name
    assert trace["assignments"]
    assert all("by descriptor" in a["rationale"] for a in trace["assignments"])
    assert {a["node"] for a in trace["assignments"]} <= {"worker-A", "worker-B"}

    # (e) every accepted artifact carries a real stage-gate verdict and reached DONE
    stage = [g for g in trace["gate_records"] if g["kind"] == "stage"]
    assert stage and all(g["verdict"] == "PASS" for g in stage)
    for task_id in [g["task_id"] for g in stage]:
        assert flow["flow"].graph.get(task_id).state is TaskState.DONE

    # (f) the conductor synthesized an acceptance packet over the ACCEPTED set
    packet = trace["packet"]
    assert packet["schema"] == "acceptance_packet@1.0"
    assert packet["accepted_count"] == len(trace["accepted_entries"]) > 0
    assert packet["objective"] == OBJECTIVE
    assert trace["acceptance_packet"].startswith("m-")


def test_capability_the_worker_pool_cannot_serve_is_queued_not_dropped(flow) -> None:
    """The mock decomposition includes a 'coding' task; the reasoning/review worker pool cannot
    serve it. It must be QUEUED with a reason — surfaced, never silently dropped, never routed to
    an incapable node."""
    trace = flow["flow"].run(OBJECTIVE)
    coding = [t for t in trace["decomposition"]["tasks"] if t["capability"] == "coding"]
    if not coding:
        pytest.skip("this objective's deterministic decomposition proposed no coding task")
    queued_ids = {q["task"] for q in trace["queued"]}
    assert {t["task_id"] for t in coding} <= queued_ids
    for q in trace["queued"]:
        assert "no node meets" in q["reason"]
    assert {t["task_id"] for t in coding} <= set(trace["packet"]["task_states"])


def test_artifacts_are_gate_promoted_and_provenanced_in_mcp(flow) -> None:
    trace = flow["flow"].run(OBJECTIVE)
    reader = _reader(flow["srv"])
    accepted = reader.call("read_status", status="ACCEPTED")
    by_id = {e["entry_id"]: e for e in accepted}
    try:
        assert trace["accepted_entries"]
        for entry_id in trace["accepted_entries"]:
            entry = by_id[entry_id]                          # promoted in MCP, not just in the graph
            prov = entry["provenance"]
            assert prov["task_id"] in {t["task_id"] for t in trace["decomposition"]["tasks"]}
            assert prov["author_node"].startswith("worker-")
            assert "gate-1" in prov.get("reviewers", [])     # the GATE promoted it, not the author
    finally:
        reader.close()


def test_seeded_defect_is_computed_fail_and_cannot_advance(flow) -> None:
    """Invariant 16: an artifact whose claimed hash does not match the stored bytes FAILS the
    stage gate (computed by the criteria, not asserted by the test), never reaches ACCEPTED, and
    its task cannot advance to DONE."""
    trace = flow["flow"].run(OBJECTIVE, gate_reject_tasks=frozenset({"t-1"}))

    failed_gates = [g for g in trace["gate_records"] if g["kind"] == "stage" and g["task_id"] == "t-1"]
    assert failed_gates and failed_gates[0]["verdict"] == "FAIL"
    assert any("artifact_content_addressed" in r for r in failed_gates[0]["reasons"])
    assert "t-1" in trace["failed_tasks"]
    assert flow["flow"].graph.get("t-1").state is TaskState.BLOCKED

    reader = _reader(flow["srv"])
    try:
        accepted_ids = {e["entry_id"] for e in reader.call("read_status", status="ACCEPTED")}
        assert not (set(trace["accepted_entries"]) & {"t-1"})
        assert trace["packet"]["failed_tasks"] == ["t-1"]
        # the packet itself is still gated and accepted; the FAILED artifact is not in it
        assert all(row["task_id"] != "t-1" for row in trace["packet"]["accepted"])
        assert trace["acceptance_packet"] in accepted_ids
    finally:
        reader.close()


def test_conductor_does_not_accept_its_own_acceptance_packet(flow) -> None:
    """Invariant 18: the packet is published CANDIDATE by the conductor and promoted by the GATE
    node after a real acceptance-gate verdict."""
    trace = flow["flow"].run(OBJECTIVE)
    assert trace["acceptance_gate"]["kind"] == "acceptance"
    assert trace["acceptance_gate"]["decided_by"] == "gate_engine"

    reader = _reader(flow["srv"])
    try:
        entry = next(e for e in reader.call("read_status", status="ACCEPTED")
                     if e["entry_id"] == trace["acceptance_packet"])
        assert entry["provenance"]["author_node"] == "conductor-fable5"
        assert "gate-1" in entry["provenance"].get("reviewers", [])
        body = json.loads(base64.b64decode(
            reader.call("get_content", entry_id=trace["acceptance_packet"])["content_b64"]))
        assert body["schema"] == "acceptance_packet@1.0"
    finally:
        reader.close()


def test_selection_is_carried_on_the_result_and_executing_stays_unverified(flow) -> None:
    """Directive §11 15D: the SELECTION is preserved and recorded separately from the EXECUTING
    checkpoint. Nothing live ran here, so nothing executed — and the record says so."""
    trace = flow["flow"].run(OBJECTIVE)
    sel = trace["conductor_selection"]
    assert sel["selection"]["model"] == "fable-5"
    assert sel["selection"]["reason"] == "operator_selected"
    assert sel["executing"]["model"] is None and sel["executing"]["verified"] is False
    assert trace["packet"]["conductor_selection"] == sel
    assert trace["packet"]["legs"]["conductor"] == "mock"


def test_unusable_decomposition_stops_at_the_plan_gate(flow, monkeypatch) -> None:
    """Fail closed: a conductor reply that could not be parsed decomposes nothing, the plan gate
    FAILS on the empty plan, and no worker is ever assigned."""
    from adapters.conductor import adapter as adapter_mod

    real = adapter_mod.ConductorAdapter.run_cycle

    def unparseable(self, objective):
        out = real(self, objective)
        out["decision"] = dict(out["decision"], parse_mode="unstructured", proposed_tasks=[])
        return out

    monkeypatch.setattr(adapter_mod.ConductorAdapter, "run_cycle", unparseable)
    trace = flow["flow"].run(OBJECTIVE)

    assert trace["plan_gate"]["verdict"] == "FAIL"
    assert "assignments" not in trace                      # nothing was ever scheduled
    assert trace["packet"]["accepted_count"] == 0
    assert trace["decomposition"]["accepted_count"] == 0


# --- declared ordering is honoured end to end ----------------------------------------

def _decomposition(monkeypatch, tasks):
    """Drive the REAL conductor cycle but substitute the proposed task list, so the ordering
    under test is the conductor's declared decomposition rather than a hand-built graph."""
    from adapters.conductor import adapter as adapter_mod

    real = adapter_mod.ConductorAdapter.run_cycle

    def patched(self, objective):
        out = real(self, objective)
        out["decision"] = dict(out["decision"], parse_mode="structured", proposed_tasks=tasks)
        return out

    monkeypatch.setattr(adapter_mod.ConductorAdapter, "run_cycle", patched)


def test_a_dependent_task_runs_in_a_later_wave_and_is_accepted(flow, monkeypatch) -> None:
    """A task with declared deps starts PENDING, not READY, so it is not in the first scheduling
    wave. The flow must keep scheduling until the graph quiesces — otherwise the dependent task
    is silently never executed, never gated, and never surfaces as failed or queued."""
    _decomposition(monkeypatch, [{"desc": "analyse the roster", "capability": "reasoning"},
                                 {"desc": "review the analysis", "capability": "review", "deps": [1]}])
    trace = flow["flow"].run(OBJECTIVE)

    assert [t["deps"] for t in trace["decomposition"]["tasks"]] == [[], ["t-1"]]
    # both tasks were assigned — t-2 only became READY after t-1 reached DONE
    assert {a["task"] for a in trace["assignments"]} == {"t-1", "t-2"}
    assert flow["flow"].graph.get("t-1").state is TaskState.DONE
    assert flow["flow"].graph.get("t-2").state is TaskState.DONE
    assert {row["task_id"] for row in trace["packet"]["accepted"]} == {"t-1", "t-2"}

    # ordering actually held: t-1 was gated before t-2 was assigned
    kinds = [(e["kind"], e.get("task_id"), e.get("to")) for e in trace["task_events"]]
    t1_done = kinds.index(("task_transition", "t-1", "DONE"))
    t2_ready = kinds.index(("task_transition", "t-2", "READY"))
    assert t1_done < t2_ready


def test_a_dependent_of_a_gate_failed_task_is_blocked_never_assigned(flow, monkeypatch) -> None:
    """Invariant 16 through the dependency edge: when a prerequisite FAILS its stage gate, the
    dependent task must never be assigned or executed — it is BLOCKED and surfaced."""
    _decomposition(monkeypatch, [{"desc": "analyse the roster", "capability": "reasoning"},
                                 {"desc": "review the analysis", "capability": "review", "deps": [1]}])
    trace = flow["flow"].run(OBJECTIVE, gate_reject_tasks=frozenset({"t-1"}))

    assert "t-1" in trace["failed_tasks"]
    assert flow["flow"].graph.get("t-1").state is TaskState.BLOCKED
    assert flow["flow"].graph.get("t-2").state is TaskState.BLOCKED
    assert "t-2" not in {a["task"] for a in trace["assignments"]}
    assert all(row["task_id"] != "t-2" for row in trace["packet"]["accepted"])
    # the blocked dependent is visible in the packet, not silently missing
    assert trace["packet"]["task_states"]["t-2"] == "BLOCKED"


def test_a_three_deep_dependency_chain_completes_in_order(flow, monkeypatch) -> None:
    """Depth beyond one extra pass: a 3-task chain needs three waves. This pins that scheduling
    runs to quiescence rather than a fixed number of passes."""
    _decomposition(monkeypatch, [{"desc": "analyse the roster", "capability": "reasoning"},
                                 {"desc": "review the analysis", "capability": "review", "deps": [1]},
                                 {"desc": "review the review", "capability": "review", "deps": [2]}])
    trace = flow["flow"].run(OBJECTIVE)

    assert [t["deps"] for t in trace["decomposition"]["tasks"]] == [[], ["t-1"], ["t-2"]]
    assert {a["task"] for a in trace["assignments"]} == {"t-1", "t-2", "t-3"}
    assert {row["task_id"] for row in trace["packet"]["accepted"]} == {"t-1", "t-2", "t-3"}

    order = [(e.get("task_id"), e.get("to")) for e in trace["task_events"]
             if e["kind"] == "task_transition"]
    assert order.index(("t-1", "DONE")) < order.index(("t-2", "READY"))
    assert order.index(("t-2", "DONE")) < order.index(("t-3", "READY"))


def test_the_plan_gate_evaluates_the_real_declared_dependency_graph(flow, monkeypatch) -> None:
    """The plan gate's `plan_acyclic` criterion must see the conductor's actual edges. With deps
    dropped it would evaluate an empty graph and pass vacuously."""
    _decomposition(monkeypatch, [{"desc": "analyse the roster", "capability": "reasoning"},
                                 {"desc": "review the analysis", "capability": "review", "deps": [1]}])
    trace = flow["flow"].run(OBJECTIVE)
    assert trace["plan_gate"]["verdict"] == "PASS"
    assert trace["decomposition"]["tasks"][1]["deps"] == ["t-1"]


# --- the LIVE leg: gated, and skip-with-record ---------------------------------------

def _denied_auth(tmp_path):
    """DENIED-by-absence: the repo's real config is NEVER used by tests (the loop must not
    self-authorize, invariant 1)."""
    return load_live_authorization(tmp_path / "no-such-live_operation.json")


def test_live_flow_skips_with_record_when_live_authorization_is_absent(flow, tmp_path) -> None:
    outcome = attempt_live_flow(
        objective=OBJECTIVE, server=flow["srv"], conductor_file_refs=flow["manifest"],
        governor=SubscriptionGovernor(), subscription_ref="sub-anthropic",
        live_auth=_denied_auth(tmp_path), profile_loader=ProfileLoader(DeploymentProfile("cloud")),
        operator_terms_confirmed=True, node_id="conductor-live")

    assert outcome.skipped_with_record and not outcome.ran and not outcome.published
    assert outcome.acceptance_packet is None
    assert outcome.legs == {"conductor": "skipped", "workers": "skipped"}
    # surfaced on EVERY outcome, including the refusals (never silent)
    assert outcome.model_resolution is not None
    assert outcome.conductor_selection["selection"]["model"] == "fable-5"
    assert outcome.conductor_selection["executing"]["verified"] is False


def test_live_flow_skips_with_record_when_operator_terms_are_unconfirmed(flow, tmp_path) -> None:
    """The R8 §6 [OPERATOR] live-terms gate — which the loop cannot self-discharge (§10.4)."""
    cfg = tmp_path / "live_operation.json"
    cfg.write_text(json.dumps(_VALID_AUTH), encoding="utf-8")

    outcome = attempt_live_flow(
        objective=OBJECTIVE, server=flow["srv"], conductor_file_refs=flow["manifest"],
        governor=SubscriptionGovernor(), subscription_ref="sub-anthropic",
        live_auth=load_live_authorization(cfg), profile_loader=ProfileLoader(DeploymentProfile("cloud")),
        operator_terms_confirmed=False, node_id="conductor-live")

    assert outcome.skipped_with_record and not outcome.published
    assert "LiveTermsNotConfirmed" in outcome.reason
    assert outcome.legs["conductor"] == "skipped"


def test_governed_live_path_runs_the_whole_flow_with_an_injected_mock_backend(flow, tmp_path) -> None:
    """MOCK-FIRST: every live gate is satisfied and the flow runs through the REAL supervised
    spawn path (`spawn_claude_code_conductor`) — but with an injected mock backend, so NO `claude`
    process is spawned and the leg is recorded `mock`, never `live`."""
    cfg = tmp_path / "live_operation.json"
    cfg.write_text(json.dumps(_VALID_AUTH), encoding="utf-8")
    governor = SubscriptionGovernor()

    outcome = attempt_live_flow(
        objective=OBJECTIVE, server=flow["srv"], conductor_file_refs=flow["manifest"],
        governor=governor, subscription_ref="sub-anthropic",
        live_auth=load_live_authorization(cfg), profile_loader=ProfileLoader(DeploymentProfile("cloud")),
        operator_terms_confirmed=True, node_id="conductor-live",
        backend=MockClaudeCliBackend(), worker_ids=("worker-A", "worker-B"))

    assert outcome.ran and outcome.published and not outcome.skipped_with_record
    assert outcome.acceptance_packet.startswith("m-")
    assert outcome.legs["conductor"] == "mock"          # an injected mock is NEVER called live
    assert outcome.conductor_selection["executing"]["verified"] is False
    # the terminal was released — the governed count never wedges
    status = governor.status()["sub-anthropic"]
    assert status["provider"] == "claude_code"
    assert status["in_use"] == 0 and status["allowance"] == 2


def test_a_mock_conductor_does_not_advertise_a_vendor_identity(flow) -> None:
    """Invariant 3: the SELECTION label is preserved, but the resolution must describe what is
    actually BOUND. Emitting the claude_code roster descriptor for a MockReasoningBackend run
    would assert a frontier, subscription-backed vendor node that never participated."""
    trace = flow["flow"].run(OBJECTIVE)
    res = trace["model_resolution"]
    assert res["subscription_backed"] is False
    assert res["locality"] == "local"
    assert "claude_code" not in res["adapter"]
    assert res["model_ref"]["verified"] is False
    # the operator's selection label is still preserved, separately
    assert trace["conductor_selection"]["selection"]["model"] == "fable-5"


def test_a_run_that_reached_the_model_is_never_reported_as_skipped(flow, tmp_path) -> None:
    """§6 honesty in the under-reporting direction: a live-classified backend that already counted
    a call and then failed has SPENT the subscription. Reporting that as `skipped` (nothing spent)
    is the same dishonesty the `calls` counters exist to prevent."""
    from control_plane.orchestration.live_flow import ATTEMPTED_LEG

    cfg = tmp_path / "live_operation.json"
    cfg.write_text(json.dumps(_VALID_AUTH), encoding="utf-8")

    def _explode(prompt, *, max_tokens=256):
        backend.calls += 1
        raise BackendAuthPause("session expired mid-run")

    # Instance-level replacement on a GENUINE `ClaudeCliBackend`, not a subclass: since
    # `phase-15d.gate` (U45) a subclass classifies `mock`, because a subclass can override
    # `generate` and spawn nothing. Exact type constrains the class, not the behaviour (U43), so
    # this is how a live-classified backend is exercised without spawning a process.
    backend = ClaudeCliBackend(model="fable-5")
    backend.generate = _explode

    outcome = attempt_live_flow(
        objective=OBJECTIVE, server=flow["srv"], conductor_file_refs=flow["manifest"],
        governor=SubscriptionGovernor(), subscription_ref="sub-anthropic",
        live_auth=load_live_authorization(cfg), profile_loader=ProfileLoader(DeploymentProfile("cloud")),
        operator_terms_confirmed=True, node_id="conductor-live",
        backend=backend, cli_present=True)

    assert not outcome.published
    assert outcome.legs["conductor"] == ATTEMPTED_LEG      # NOT "skipped" — a call was spent
    assert outcome.ran is True


def test_an_unreadable_spend_counter_fails_closed_to_attempted(flow) -> None:
    """`_spent_calls` returning None means UNREADABLE, which is not the same as zero. Treating an
    unreadable counter as 'nothing was spent' is the exact under-reporting the attempted-leg
    machinery exists to prevent, so it must fail closed."""
    from control_plane.orchestration.live_flow import ATTEMPTED_LEG, ConductorHandle, _failure_legs

    class _Unreadable:
        def export_session_state(self):
            raise RuntimeError("counter unavailable")

    live = ConductorHandle(adapter=None, leg="live")
    assert _failure_legs(live, _Unreadable())["conductor"] == ATTEMPTED_LEG
    # a mock leg is still honestly 'skipped' — the fail-closed rule applies to live legs only
    assert _failure_legs(ConductorHandle(adapter=None, leg="mock"), _Unreadable())["conductor"] == "skipped"


def test_an_auth_pause_before_any_call_is_not_reported_as_a_run(flow, tmp_path) -> None:
    """`ran` is derived from counted-call evidence, not from which branch we exited. A backend
    that pauses without ever reaching a model did not run, and claiming it did would be the
    mirror image of the under-reporting this unit fixes."""
    cfg = tmp_path / "live_operation.json"
    cfg.write_text(json.dumps(_VALID_AUTH), encoding="utf-8")

    class _PauseBeforeCalling(MockClaudeCliBackend):
        """Mock-classified backend that pauses WITHOUT counting a call."""

        def generate(self, prompt, *, max_tokens=256):
            raise BackendAuthPause("expired before any request was made")

    outcome = attempt_live_flow(
        objective=OBJECTIVE, server=flow["srv"], conductor_file_refs=flow["manifest"],
        governor=SubscriptionGovernor(), subscription_ref="sub-anthropic",
        live_auth=load_live_authorization(cfg), profile_loader=ProfileLoader(DeploymentProfile("cloud")),
        operator_terms_confirmed=True, node_id="conductor-live",
        backend=_PauseBeforeCalling(), cli_present=True)

    assert not outcome.published
    assert outcome.ran is False              # nothing was spent, so nothing "ran"
    assert outcome.legs["conductor"] == "skipped"


def test_the_acceptance_packet_is_content_addressed_to_the_bytes_mcp_stored(flow) -> None:
    """I-M1 applied to the conductor's OWN artifact: the gate re-reads the published bytes rather
    than trusting the author's in-process buffer, so the artifact_id it content-addresses is the
    digest of what MCP really holds.

    The two canonicalisations are byte-identical today, so this asserts the OUTCOME (the digest
    matches the stored bytes) rather than the mechanism — the mechanism is defence in depth
    against them diverging.
    """
    import hashlib

    trace = flow["flow"].run(OBJECTIVE)
    reader = _reader(flow["srv"])
    try:
        stored = base64.b64decode(
            reader.call("get_content", entry_id=trace["acceptance_packet"])["content_b64"])
    finally:
        reader.close()

    assert trace["acceptance_gate"]["verdict"] == "PASS"
    assert stored, "the packet must actually be stored in MCP"
    # the id the gate content-addressed is the digest of the bytes an INDEPENDENT reader fetched
    assert trace["acceptance_artifact_id"] == "sha256:" + hashlib.sha256(stored).hexdigest()


def test_a_zero_accepted_packet_does_not_cite_itself_as_its_own_evidence(flow, monkeypatch) -> None:
    """A vacuous claim satisfied by the packet's own id would let `claims_cite_evidence` pass on a
    run that accomplished nothing. The claim is dropped instead."""
    from adapters.conductor import adapter as adapter_mod

    real = adapter_mod.ConductorAdapter.run_cycle

    def unparseable(self, objective):
        out = real(self, objective)
        out["decision"] = dict(out["decision"], parse_mode="unstructured", proposed_tasks=[])
        return out

    monkeypatch.setattr(adapter_mod.ConductorAdapter, "run_cycle", unparseable)
    trace = flow["flow"].run(OBJECTIVE)

    assert trace["packet"]["accepted_count"] == 0
    assert trace["packet"]["accepted_confirmed_in_mcp"] == 0

    # the load-bearing assertion: the packet's own entry id appears NOWHERE in the evidence it is
    # judged against — not in the gate record's evidence array, not as a claim's evidence_ref
    packet_entry = trace["acceptance_packet"]
    assert packet_entry not in (trace["acceptance_gate"].get("evidence") or [])
    assert trace["acceptance_gate"]["evidence"] == []

    reader = _reader(flow["srv"])
    try:
        body = json.loads(base64.b64decode(
            reader.call("get_content", entry_id=packet_entry)["content_b64"]))
    finally:
        reader.close()
    # the packet is published and gated, but claims nothing it cannot evidence
    assert body["accepted"] == []
    assert body["operator_disposition"] == "pending"


def test_an_unverified_live_run_degrades_its_leg_instead_of_discarding_the_run(flow, tmp_path) -> None:
    """MAJOR case: on the live path the workers' artifacts are already gated and promoted in MCP.
    If the CLI returns no verifiable checkpoint, refusing to synthesize would destroy that whole
    governed record over an unprovable label. The leg degrades to `attempted` and the packet is
    still published — report less than was claimed, never discard the evidence."""
    from control_plane.orchestration.live_flow import ATTEMPTED_LEG

    cfg = tmp_path / "live_operation.json"
    cfg.write_text(json.dumps(_VALID_AUTH), encoding="utf-8")

    def _silent(prompt, *, max_tokens=256):
        """Replies that name no model — exactly the `extract_reported_model` -> None case the live
        smoke has not yet resolved. A call IS spent."""
        backend.calls += 1
        backend.reported_model = None
        return json.dumps({"proposed_tasks": [{"desc": "analyse", "capability": "reasoning"}]})

    # genuine class + instance-level generate (see the note in the attempted-leg test above)
    backend = ClaudeCliBackend(model="fable-5")
    backend.generate = _silent

    outcome = attempt_live_flow(
        objective=OBJECTIVE, server=flow["srv"], conductor_file_refs=flow["manifest"],
        governor=SubscriptionGovernor(), subscription_ref="sub-anthropic",
        live_auth=load_live_authorization(cfg), profile_loader=ProfileLoader(DeploymentProfile("cloud")),
        operator_terms_confirmed=True, node_id="conductor-live",
        backend=backend, cli_present=True)

    assert outcome.published, "the governed run must not be discarded"
    assert outcome.legs["conductor"] == ATTEMPTED_LEG      # never silently 'live'
    assert outcome.trace["leg_degraded"]
    assert outcome.trace["packet"]["legs"]["conductor"] == ATTEMPTED_LEG
    # the operator-facing PROSE must report the degraded leg too — not the leg we hoped for
    assert "live" not in outcome.reason
    assert ATTEMPTED_LEG in outcome.reason


def test_a_non_spawning_subclass_cannot_reach_a_live_leg(flow, tmp_path) -> None:
    """U45 site 1, end to end through the REAL entrypoint. Pre-fix, `_leg_for_backend` used
    `isinstance`, so this backend — which inherits the vendor class, spawns nothing, and sets its
    own instrumentation — was classified `live` and its checkpoint published as verified. That is a
    mock presented as a real-provider result (§6/§10.4)."""
    cfg = tmp_path / "live_operation.json"
    cfg.write_text(json.dumps(_VALID_AUTH), encoding="utf-8")

    class _NonSpawningSubclass(ClaudeCliBackend):
        def generate(self, prompt, *, max_tokens=256):
            self.calls += 1
            self.reported_model = "claude-fable-5-20260101"
            self.reported_model_at_call = self.calls
            return json.dumps({"proposed_tasks": [{"desc": "analyse", "capability": "reasoning"}]})

    outcome = attempt_live_flow(
        objective=OBJECTIVE, server=flow["srv"], conductor_file_refs=flow["manifest"],
        governor=SubscriptionGovernor(), subscription_ref="sub-anthropic",
        live_auth=load_live_authorization(cfg), profile_loader=ProfileLoader(DeploymentProfile("cloud")),
        operator_terms_confirmed=True, node_id="conductor-live",
        backend=_NonSpawningSubclass(), cli_present=True)

    assert outcome.published, "the governed run itself is still valid — only the live CLAIM is not"
    assert outcome.legs["conductor"] == "mock"
    assert outcome.trace["packet"]["legs"]["conductor"] == "mock"
    assert outcome.conductor_selection["executing"]["verified"] is False
    assert outcome.conductor_selection["executing"]["model"] is None


def test_a_mock_backed_conductor_names_its_actual_backend(flow) -> None:
    """The descriptor must name what is BOUND. A hard-coded literal would hide a backend swap."""
    trace = flow["flow"].run(OBJECTIVE)
    assert trace["model_resolution"]["adapter"] not in ("unknown_backend", "")
    assert "mock" in trace["model_resolution"]["adapter"].lower()


def test_worker_reported_reasons_are_not_attributed_to_the_gate_engine(flow, monkeypatch) -> None:
    """Invariants 11/18: a node-authored explanation must not be written into a record whose
    `decided_by` is `gate_engine`. It is carried in a separate, clearly-attributed field."""
    from adapters.local import worker as worker_mod

    real_execute = worker_mod.LocalWorkerAdapter.execute

    def refuse(self):
        out = real_execute(self)
        return {**out, "published": False, "reasons": ["node authored this"]}

    monkeypatch.setattr(worker_mod.LocalWorkerAdapter, "execute", refuse)
    trace = flow["flow"].run(OBJECTIVE)

    local = [g for g in trace["gate_records"] if g["kind"] == "local"]
    assert local
    for record in local:
        assert record["decided_by"] == "gate_engine"
        assert "node authored this" not in record.get("reasons", [])
        # gate@1.0 is frozen with additionalProperties=false — the record must stay conformant
        assert "node_reported_reasons" not in record

    refusals = trace["node_refusals"]
    assert refusals and all(r["node_reported_reasons"] == ["node authored this"] for r in refusals)
    assert {r["gate_id"] for r in refusals} == {g["gate_id"] for g in local}


def test_an_entry_whose_promotion_lost_a_cas_race_is_not_reported_as_accepted(flow, monkeypatch) -> None:
    """Invariant 13: conflicts are explicit objects, never silent last-write-wins. MemoryService
    reports `applied: False` with the parked fork ref when a concurrent writer advanced the head.
    Discarding that report would count an entry whose MCP status never changed as ACCEPTED."""
    from mcp_server.protocol import McpClient

    real_call = McpClient.call

    def lose_promotion(self, op, **kw):
        out = real_call(self, op, **kw)
        if op == "transition" and kw.get("requested_status") == "ACCEPTED":
            return {**out, "applied": False, "conflict": "c-seeded", "status": "UNDER_REVIEW"}
        return out

    monkeypatch.setattr(McpClient, "call", lose_promotion)
    trace = flow["flow"].run(OBJECTIVE)

    assert trace["promotion_conflicts"], "a lost CAS must surface as an explicit conflict object"
    assert all(c["conflict"] == "c-seeded" for c in trace["promotion_conflicts"])
    # nothing that lost its promotion is counted as accepted
    assert trace["packet"]["accepted"] == []
    assert trace["packet"]["accepted_count"] == 0
    conflicted = {c["task_id"] for c in trace["promotion_conflicts"]}
    assert conflicted <= set(trace["packet"]["failed_tasks"])

    # the conflict must reach the DURABLE artifact: otherwise an operator reading the published
    # packet sees a task both DONE and failed with nothing explaining why
    assert trace["packet"]["promotion_conflicts"], "conflicts must be in the packet, not just the trace"
    assert {c["conflict"] for c in trace["packet"]["promotion_conflicts"]} == {"c-seeded"}


def test_every_gate_record_the_flow_produces_stays_schema_conformant(flow) -> None:
    """`gate@1.0` is frozen with additionalProperties=false. Any record the flow emits — including
    the synthetic node-local one — must validate, so nothing it produces can be a non-conformant
    envelope (schemas/ is the single source of truth, frozen @1.0)."""
    import jsonschema

    schema = json.loads((ROOT / "schemas" / "gate.schema.json").read_text(encoding="utf-8"))
    trace = flow["flow"].run(OBJECTIVE)

    records = trace["gate_records"]
    assert {g["kind"] for g in records} >= {"plan", "stage", "acceptance"}
    for record in records:
        jsonschema.validate(record, schema)


def test_a_node_local_gate_failure_carries_a_verdict_into_the_packet(flow, monkeypatch) -> None:
    """Buildout §4 observability: a task that failed its node-local gate must not appear in the
    packet as a failure with no verdict explaining it."""
    from adapters.local import worker as worker_mod

    real_execute = worker_mod.LocalWorkerAdapter.execute

    def refuse(self):
        out = real_execute(self)
        return {**out, "published": False, "reasons": ["seeded node-local refusal"]}

    monkeypatch.setattr(worker_mod.LocalWorkerAdapter, "execute", refuse)
    trace = flow["flow"].run(OBJECTIVE)

    import jsonschema

    assert trace["failed_tasks"]
    local = [g for g in trace["gate_records"] if g["kind"] == "local"]
    assert local, "a node-local refusal produced no gate record"
    assert {g["task_id"] for g in local} <= set(trace["failed_tasks"])
    assert all(g["verdict"] != "PASS" for g in local)
    # the synthetic record is a real gate@1.0 envelope, not an ad-hoc dict
    schema = json.loads((ROOT / "schemas" / "gate.schema.json").read_text(encoding="utf-8"))
    for record in local:
        jsonschema.validate(record, schema)


def test_a_mock_run_cannot_be_packaged_as_a_live_result(flow) -> None:
    """The structural honesty guarantee behind every skip-with-record above."""
    trace = flow["flow"].run(OBJECTIVE)
    with pytest.raises(AcceptancePacketError):
        build_acceptance_packet(
            objective=OBJECTIVE, conductor_selection=trace["conductor_selection"],
            decomposition=trace["decomposition"], accepted=trace["packet"]["accepted"],
            failed_tasks=[], queued_tasks=[], task_states={}, gate_records=[],
            legs={"conductor": "live", "workers": "live"},
            synthesized_by="conductor-fable5", ts="2026-07-19T00:00:00+00:00")


def test_no_live_subprocess_is_reachable_from_this_suite(flow, tmp_path, monkeypatch) -> None:
    """Refutation probe: if any path in this suite spawned a real CLI, this fails."""
    import subprocess

    def forbidden(*a, **k):  # pragma: no cover - must never run
        raise AssertionError(f"a live subprocess was spawned: {a!r}")

    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    outcome = attempt_live_flow(
        objective=OBJECTIVE, server=flow["srv"], conductor_file_refs=flow["manifest"],
        governor=SubscriptionGovernor(), subscription_ref="sub-anthropic",
        live_auth=_denied_auth(tmp_path), profile_loader=ProfileLoader(DeploymentProfile("cloud")),
        operator_terms_confirmed=True, node_id="conductor-live")
    assert outcome.skipped_with_record


def test_decompose_plan_consumes_the_real_conductor_decision_shape(flow) -> None:
    """The decomposition unit is wired to the REAL backend output, not a hand-made fixture."""
    trace = flow["flow"].run(OBJECTIVE)
    reader = _reader(flow["srv"])
    try:
        body = json.loads(base64.b64decode(
            reader.call("get_content", entry_id=trace["plan_decision"])["content_b64"]))
    finally:
        reader.close()
    again = decompose_plan(body if "proposed_tasks" in body else body.get("decision", body))
    assert again.usable
    assert [t.task_id for t in again.tasks] == [t["task_id"] for t in trace["decomposition"]["tasks"]]


# --- W-72: load accounting on failure paths -------------------------------------------------

def test_load_is_released_when_a_worker_raises_mid_wave(flow) -> None:
    """Red 1: the scheduler acquires the node's load slot BEFORE the wave; the release sat after
    run_task() on the success path only, so a worker that RAISED kept the slot forever."""
    from scheduler.scheduler import Assignment

    f = flow["flow"]
    node = f._spawn_worker("worker-A")
    f._graph.add_task("t-explode", {"capability": "any"})
    f._graph.assign("t-explode", "worker-A", rationale="test")  # scheduler half: READY -> ASSIGNED

    def _explode(*a, **k):
        raise RuntimeError("worker died mid-task")

    node.adapter.execute = _explode
    assignment = Assignment(task_id="t-explode", node_id="worker-A", rationale="test")
    f._registry.acquire_load("worker-A")  # the other scheduler half: the slot is held
    with pytest.raises(RuntimeError):
        f._run_wave([assignment], "obj", "entry-ref", frozenset(), [], [], [])
    held = [x.active_tasks for x in f._registry.all_nodes() if x.node_id == "worker-A"]
    assert held == [0], f"load slot leaked across a raising worker: {held}"


def test_a_failed_handoff_compensates_by_reacquiring_for_the_predecessor() -> None:
    """Red 2: perform_handoff released the predecessor then tried the successor; when the
    acquire FAILED, the subscription was left with neither holder and nothing restored it."""

    class _Gov:
        def __init__(self):
            self.calls = []

        def release(self, ref, node):
            self.calls.append(("release", node))

        def acquire(self, ref, node):
            self.calls.append(("acquire", node))
            if node == "succ":
                raise RuntimeError("successor acquire failed")

    from control_plane.recovery.succession import SuccessionManager

    g = _Gov()
    with pytest.raises(RuntimeError):
        SuccessionManager.perform_handoff(g, "sub-1", "pred", "succ")
    assert g.calls == [("release", "pred"), ("acquire", "succ"), ("acquire", "pred")], (
        f"handoff left the subscription inconsistent with no compensation: {g.calls}")
