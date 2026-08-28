"""Phase 17B `.legs` — a LIVE WORKER publishes CANDIDATE over MCP through the governed loop, and
its leg is DERIVED from its own evidence rather than asserted (directive §16 track 17B; closes the
worker half of U58).

Two things are under test and they are separable:

  1. **The wiring** — an injected `WorkerHandle` is registered in the capability registry, resolved
     BY DESCRIPTOR by the real Scheduler, executes the assignment, publishes a CANDIDATE over the
     real MCP server, and is gated by the real gate engine into the conductor's synthesis.
  2. **The leg honesty** — `derive_worker_legs` / `_assert_legs_honest` make a `live` worker leg
     UNREPRESENTABLE without that node's own verification record, refuse a declared leg that
     contradicts the evidence in EITHER direction, and refuse contradictory evidence outright.

MOCK-FIRST (§10.4): every test here binds a deterministic backend or a fake verifier. No `claude`
process is spawned by this suite — the live run is the operator-gated emitter, whose receipt is the
evidence. A mock can never be recorded live, and that is itself asserted below.
"""
from __future__ import annotations

import base64
from pathlib import Path

import pytest
from control_plane.profiles.loader import ProfileViolation

from adapters.conductor import publish_conductor_files
from adapters.frontier.claude_code import MockClaudeCliBackend
from control_plane.orchestration.live_flow import (
    ATTEMPTED_LEG,
    AcceptancePacketError,
    LiveGovernedFlow,
    WorkerHandle,
    build_acceptance_packet,
    derive_worker_legs,
    live_claude_worker_handle,
)
from control_plane.profiles.live_authorization import load_live_authorization
from control_plane.profiles.loader import DeploymentProfile, ProfileLoader
from mcp_server.protocol import McpClient
from mcp_server.server import MCPServer
from node_runtime.supervisor.subscription_governor import SubscriptionGovernor

ROOT = Path(__file__).resolve().parents[2]
CONDUCTOR_DIR = ROOT / "conductor"
OBJECTIVE = "Design the offline conductor roster"

_VALID_AUTH = {"config_version": "1.1", "live_operation_authorized": True, "register_row": "OP-6",
               "scope": {"providers": ["claude_code", "openai_codex_cli"],
                         "terminals_per_subscription": 2}}


# --- fixtures ----------------------------------------------------------------------

@pytest.fixture()
def srv(tmp_path):
    s = MCPServer(tmp_path / "store")
    s.start()
    op = McpClient("127.0.0.1", s.port, s.credentials.issue("op-boot", "operator", "proj"))
    op.connect()
    manifest = publish_conductor_files(op, "op-boot", CONDUCTOR_DIR)
    op.close()
    yield {"srv": s, "manifest": manifest}
    s.stop()


def _auth(tmp_path, payload=None):
    p = tmp_path / "live_operation.json"
    import json
    p.write_text(json.dumps(payload if payload is not None else _VALID_AUTH), encoding="utf-8")
    return load_live_authorization(p)


def _loader():
    return ProfileLoader(DeploymentProfile("cloud"))


class _FakeWorkerAdapter:
    """A worker adapter shaped like the real one: reads scoped context from MCP, publishes a
    CANDIDATE. It exists so the FLOW can be driven without a vendor CLI — its evidence comes from
    the handle's verifier, never from anything it says about itself."""

    def __init__(self, mcp_client, node_id, *, capability="reasoning", min_context=128000):
        self._mcp = mcp_client
        self._node_id = node_id
        self._capability = capability
        self._min_context = min_context
        self._task_id = None
        self._entry = None
        self.calls = 0

    def capability_descriptors(self):
        return [{"capability": self._capability,
                 "requirements": {"tool_use": True, "structured_output": True,
                                  "min_context": self._min_context, "locality": "frontier_ok"}}]

    def capability(self):
        from adapters.base.contract import AdapterCapability
        return AdapterCapability(adapter="fake_live_worker", node_class="worker_reasoning",
                                 locality="frontier", offline_profile_eligible=False,
                                 requires_network=True, local_runtime=False,
                                 capabilities=(self._capability,), subscription_backed=True)

    def assign(self, task_id, context_entry_id):
        self._task_id, self._entry = task_id, context_entry_id

    def execute(self, **_kw):
        import hashlib
        self.calls += 1
        ctx = self._mcp.call("get_content", entry_id=self._entry)
        objective = base64.b64decode(ctx["content_b64"]).decode("utf-8")
        content = f"# {self._task_id} from {self._node_id}\n\n{objective}\n".encode("utf-8")
        digest = "sha256:" + hashlib.sha256(content).hexdigest()
        structured = {
            "summary": f"{self._task_id} complete",
            "claims": [{"text": "objective read from MCP", "evidence_refs": [self._entry]},
                       {"text": "artifact content-addressed", "evidence_refs": [digest]}],
            "artifact": {"artifact_id": digest, "media_type": "text/markdown",
                         "size_bytes": len(content), "created_by_node": self._node_id,
                         "task_id": self._task_id, "ts": "2026-07-26T00:00:00+00:00",
                         "schema": "artifact@1.0"},
        }
        pub = self._mcp.call("publish", kind="finding", tier="shared_project",
                             content_b64=base64.b64encode(content).decode("ascii"),
                             provenance={"author_node": self._node_id, "task_id": self._task_id,
                                         "ts": "2026-07-26T00:00:00+00:00",
                                         "directive_version": "v2.4", "confidence": "medium"},
                             status="CANDIDATE")
        return {"published": True, "local_gate": "PASS", "entry_id": pub["entry_id"],
                "content_hash": digest, "structured": structured}


def _handle(srv, node_id="frontier-live-1", *, leg="live", verified_model="claude-fable-5-x",
            spent=True, released=None, capability="reasoning"):
    client = McpClient("127.0.0.1", srv["srv"].port,
                       srv["srv"].credentials.issue(node_id, "worker", "proj"))
    client.connect()
    adapter = _FakeWorkerAdapter(client, node_id, capability=capability)
    return WorkerHandle(
        node_id=node_id, adapter=adapter, leg=leg,
        descriptors=tuple(adapter.capability_descriptors()),
        locality="frontier", cost_class="subscription", offline_profile_eligible=False,
        execute=lambda: adapter.execute(),
        verify=(lambda: {"model": verified_model, "verified": True}) if verified_model else (lambda: None),
        spent=lambda: spent,
        release=released)


# --- 1. the wiring: a live worker runs the governed loop -----------------------------

def test_an_injected_live_worker_is_routed_by_descriptor_and_gate_accepted(srv) -> None:
    handle = _handle(srv)
    flow = LiveGovernedFlow(srv["srv"], srv["manifest"], worker_ids=(), worker_handles=(handle,))
    try:
        trace = flow.run(OBJECTIVE)
    finally:
        flow.close()

    # routed BY DESCRIPTOR to the injected node (invariant 4) — never by name
    assert trace["assignments"], "the live worker was never assigned any task"
    assert all("by descriptor" in a["rationale"] for a in trace["assignments"])
    assert {a["node"] for a in trace["assignments"]} == {"frontier-live-1"}

    # its CANDIDATE went through the REAL stage gate and was promoted by the GATE node
    stage = [g for g in trace["gate_records"] if g["kind"] == "stage"]
    assert stage and all(g["verdict"] == "PASS" for g in stage)
    assert trace["packet"]["accepted_count"] >= 1
    assert trace["acceptance_gate"]["verdict"] == "PASS"

    # and the leg is LIVE, derived from the node's own verification record
    assert trace["legs"]["workers"] == "live"
    assert trace["legs"]["worker:frontier-live-1"] == "live"
    row = trace["packet"]["worker_evidence"][0]
    assert row["node_id"] == "frontier-live-1" and row["verified"] is True
    assert row["model"] == "claude-fable-5-x" and row["tasks"]


def test_a_capability_the_live_worker_cannot_serve_is_queued_not_dropped(srv) -> None:
    """The pool is one frontier reasoning node, so the mock conductor's `coding`/`review` subtasks
    resolve to nobody. They must be QUEUED with a reason, never silently dropped."""
    handle = _handle(srv)
    flow = LiveGovernedFlow(srv["srv"], srv["manifest"], worker_ids=(), worker_handles=(handle,))
    try:
        trace = flow.run(OBJECTIVE)
    finally:
        flow.close()
    assert trace["queued"], "unroutable subtasks vanished instead of being queued"
    assert all("no node meets" in q["reason"] for q in trace["queued"])


def test_a_live_worker_that_reported_no_checkpoint_is_attempted_never_live(srv) -> None:
    handle = _handle(srv, verified_model=None, spent=True)
    flow = LiveGovernedFlow(srv["srv"], srv["manifest"], worker_ids=(), worker_handles=(handle,))
    try:
        trace = flow.run(OBJECTIVE)
    finally:
        flow.close()
    assert trace["legs"]["workers"] == ATTEMPTED_LEG
    assert trace["legs"]["worker:frontier-live-1"] == ATTEMPTED_LEG
    assert trace["packet"]["worker_evidence"][0]["verified"] is False


def test_a_verifier_that_raises_is_not_a_verification(srv) -> None:
    handle = _handle(srv)
    def _boom():
        raise RuntimeError("counter unreadable")
    handle = WorkerHandle(**{**handle.__dict__, "verify": _boom})
    flow = LiveGovernedFlow(srv["srv"], srv["manifest"], worker_ids=(), worker_handles=(handle,))
    try:
        trace = flow.run(OBJECTIVE)
    finally:
        flow.close()
    assert trace["legs"]["workers"] == ATTEMPTED_LEG      # spend still over-reported, never live


def test_a_spawned_but_unused_live_worker_is_skipped_not_live(srv) -> None:
    """A handle whose capability nothing routes to still held an I-X3 slot — recorded, but its leg
    is `skipped` and it can never lift the aggregate."""
    unused = _handle(srv, node_id="frontier-idle", capability="synthesis")
    used = _handle(srv, node_id="frontier-live-1")
    flow = LiveGovernedFlow(srv["srv"], srv["manifest"], worker_ids=(),
                            worker_handles=(unused, used))
    try:
        trace = flow.run(OBJECTIVE)
    finally:
        flow.close()
    assert trace["legs"]["worker:frontier-idle"] == "skipped"
    assert trace["legs"]["worker:frontier-live-1"] == "live"
    assert trace["legs"]["workers"] == "live"
    idle = [r for r in trace["packet"]["worker_evidence"] if r["node_id"] == "frontier-idle"][0]
    assert idle["executed"] is False and idle["spent"] is False and idle["verified"] is False


def test_a_mixed_pool_reports_attempted_not_mock_and_not_live(srv) -> None:
    """Live + mock workers both ran: the aggregate can be neither `live` (some work was a mock's)
    nor `mock` (a real subscription call was spent). The per-node legs carry the detail."""
    live = _handle(srv, node_id="frontier-live-1")
    mocked = _handle(srv, node_id="mock-worker-1", leg="mock", verified_model=None, spent=False,
                     capability="coding")
    flow = LiveGovernedFlow(srv["srv"], srv["manifest"], worker_ids=(),
                            worker_handles=(live, mocked))
    try:
        trace = flow.run(OBJECTIVE)
    finally:
        flow.close()
    legs = trace["legs"]
    executed = {r["node_id"] for r in trace["packet"]["worker_evidence"] if r["executed"]}
    assert executed == {"frontier-live-1", "mock-worker-1"}, "both nodes must have run"
    assert legs["worker:frontier-live-1"] == "live"
    assert legs["worker:mock-worker-1"] == "mock"
    assert legs["workers"] == ATTEMPTED_LEG


def test_the_default_mock_pool_still_reports_a_mock_worker_leg(srv) -> None:
    """`.legs` is additive: a run with no injected handles keeps the historical leg and emits no
    worker evidence rows at all."""
    flow = LiveGovernedFlow(srv["srv"], srv["manifest"])
    try:
        trace = flow.run(OBJECTIVE)
    finally:
        flow.close()
    assert trace["legs"]["workers"] == "mock"
    assert trace["packet"]["worker_evidence"] == []
    assert not any(k.startswith("worker:") for k in trace["legs"])


def test_the_live_terminal_is_released_when_the_flow_closes(srv) -> None:
    """D-LOOP-1: a live worker's I-X3 terminal is given back inside the unit."""
    released: list[str] = []
    first = _handle(srv, node_id="frontier-live-1", released=lambda: released.append("a"))
    def _bad_release():
        raise RuntimeError("release failed")
    second = WorkerHandle(**{**_handle(srv, node_id="frontier-live-2").__dict__,
                             "release": _bad_release})
    third = _handle(srv, node_id="frontier-live-3", released=lambda: released.append("c"))
    flow = LiveGovernedFlow(srv["srv"], srv["manifest"], worker_ids=(),
                            worker_handles=(first, second, third))
    flow.begin(OBJECTIVE)
    flow.close()
    # a failing release in the middle never strands the handles after it
    assert released == ["a", "c"]


def test_a_handle_id_colliding_with_the_mock_pool_is_refused(srv) -> None:
    with pytest.raises(ValueError, match="collide"):
        LiveGovernedFlow(srv["srv"], srv["manifest"], worker_ids=("worker-A",),
                         worker_handles=(_handle(srv, node_id="worker-A"),))


def test_a_backend_fault_reaches_the_packet_instead_of_vanishing(srv) -> None:
    """A LIVE worker whose vendor call fails must say WHY in the operator-facing packet.

    `ModelWorkerAdapter` reports a transport/CLI fault as `backend_error`, not `reasons` — so the
    refusal recorder, which only read `reasons`, produced a failed task with an EMPTY explanation.
    That is precisely the live path: the first `.legs` dispatch failed and the packet could not say
    what the CLI had objected to. A failure whose cause is unrecorded is not observable
    (Buildout §4), and the leg still may not read `live` (nothing was verified).
    """
    # `verified_model=None` mirrors the real failure: a call that raised set no `reported_model`,
    # so `verify_reported_checkpoint` yields nothing to verify against.
    handle = _handle(srv, verified_model=None)
    detail = "RuntimeError: claude CLI exited 1: There's an issue with the selected model"
    handle = WorkerHandle(**{**handle.__dict__,
                             "execute": lambda: {"published": False, "backend_error": detail}})
    flow = LiveGovernedFlow(srv["srv"], srv["manifest"], worker_ids=(), worker_handles=(handle,))
    try:
        trace = flow.run(OBJECTIVE)
    finally:
        flow.close()

    refusals = trace["packet"]["node_refusals"]
    assert refusals, "the live worker's backend fault left no refusal record at all"
    reported = " ".join(refusals[0]["node_reported_reasons"])
    assert detail in reported, f"the CLI's own objection never reached the packet: {refusals[0]}"
    # the node is still attributed as the author of that text (invariants 11/18), and a run whose
    # only worker failed is `attempted` — a counted call with nothing verified — never `live`
    assert refusals[0]["node_id"] == "frontier-live-1"
    assert trace["legs"]["workers"] == ATTEMPTED_LEG


# --- 2. leg honesty: unfakeable in both directions -----------------------------------

def _packet(legs, evidence=()):
    return build_acceptance_packet(
        objective="o", conductor_selection=None, decomposition={}, accepted=[], failed_tasks=[],
        queued_tasks=[], task_states={}, gate_records=[], legs=legs, synthesized_by="x",
        ts="2026-07-26T00:00:00+00:00", worker_evidence=evidence)


_VERIFIED_ROW = {"node_id": "w1", "leg": "live", "executed": True, "spent": True,
                 "verified": True, "model": "claude-fable-5-x", "tasks": ["t-1"]}


def test_a_live_worker_leg_with_no_evidence_at_all_is_unrepresentable() -> None:
    with pytest.raises(AcceptancePacketError, match="no worker evidence"):
        _packet({"conductor": "mock", "workers": "live"})
    with pytest.raises(AcceptancePacketError, match="no worker evidence"):
        _packet({"conductor": "mock", "workers": ATTEMPTED_LEG})


def test_a_declared_worker_leg_that_contradicts_its_evidence_is_refused() -> None:
    # over-claim: evidence derives `attempted`, the packet says `live`
    unverified = {**_VERIFIED_ROW, "verified": False, "model": None}
    with pytest.raises(AcceptancePacketError, match="contradicts the worker evidence"):
        _packet({"conductor": "mock", "workers": "live", "worker:w1": ATTEMPTED_LEG}, [unverified])
    # under-claim: evidence derives `live`, the packet says `mock` — hiding real spend
    with pytest.raises(AcceptancePacketError, match="contradicts the worker evidence"):
        _packet({"conductor": "mock", "workers": "mock", "worker:w1": "live"}, [_VERIFIED_ROW])


def test_a_node_leg_the_evidence_derives_may_not_be_dropped_from_the_packet() -> None:
    with pytest.raises(AcceptancePacketError, match="does not declare"):
        _packet({"conductor": "mock", "workers": "live"}, [_VERIFIED_ROW])


def test_contradictory_worker_evidence_is_refused_outright() -> None:
    bad = [
        ({**_VERIFIED_ROW, "model": None}, "no reported checkpoint"),
        ({**_VERIFIED_ROW, "model": "   "}, "no reported checkpoint"),
        ({**_VERIFIED_ROW, "leg": "mock"}, "verified against a 'mock' binding"),
        ({**_VERIFIED_ROW, "spent": False}, "no counted call"),
        ({**_VERIFIED_ROW, "executed": False}, "never executed a task"),
        ({**_VERIFIED_ROW, "leg": "attempted"}, "must classify its backing"),
        ({**_VERIFIED_ROW, "node_id": " "}, "must name its node_id"),
        ({**_VERIFIED_ROW, "verified": "yes"}, "must carry a boolean"),
    ]
    for row, expected in bad:
        with pytest.raises(AcceptancePacketError, match=expected):
            _packet({"conductor": "mock", "workers": "live", "worker:w1": "live"}, [row])


def test_two_rows_for_one_node_are_refused() -> None:
    with pytest.raises(AcceptancePacketError, match="duplicate worker evidence"):
        _packet({"conductor": "mock", "workers": "live", "worker:w1": "live"},
                [_VERIFIED_ROW, {**_VERIFIED_ROW, "verified": False, "model": None}])


def test_a_non_worker_leg_still_cannot_be_declared_live() -> None:
    with pytest.raises(AcceptancePacketError, match="unbacked"):
        _packet({"conductor": "mock", "workers": "live", "worker:w1": "live", "debaters": "live"},
                [_VERIFIED_ROW])


def test_derive_worker_legs_is_the_single_source_of_the_aggregate() -> None:
    assert derive_worker_legs([])["workers"] == "skipped"
    assert derive_worker_legs([{**_VERIFIED_ROW, "executed": False, "verified": False,
                                "spent": False, "model": None}])["workers"] == "skipped"
    assert derive_worker_legs([_VERIFIED_ROW])["workers"] == "live"
    assert derive_worker_legs([{**_VERIFIED_ROW, "verified": False, "model": None}]
                              )["workers"] == ATTEMPTED_LEG
    # A live-bound node that executed but counted NO call reached no model. Not `attempted` (nothing
    # was spent) and not `mock` (no mock backend produced this work) — `skipped`. The evidence row
    # still says `leg: "live"`, so what it was BOUND to stays readable (spec-audit MINOR-1).
    nothing_ran = [{**_VERIFIED_ROW, "verified": False, "spent": False, "model": None}]
    assert derive_worker_legs(nothing_ran)["workers"] == "skipped"
    assert derive_worker_legs(nothing_ran)["worker:w1"] == "skipped"


# --- 3. the real governed spawn path --------------------------------------------------

def test_live_claude_worker_handle_runs_the_whole_flow_but_a_mock_is_never_live(srv, tmp_path) -> None:
    """The REAL governed spawn path (`spawn_claude_code_terminal`: profile+live gate, provider-live,
    R8 terms, I-X3) with an INJECTED mock backend: the whole governed loop runs and a CANDIDATE is
    published, yet the leg is `mock` — a substituted result can never be packaged as live."""
    gov = SubscriptionGovernor()
    client = McpClient("127.0.0.1", srv["srv"].port,
                       srv["srv"].credentials.issue("frontier-w1", "worker", "proj"))
    client.connect()
    handle = live_claude_worker_handle(
        mcp_client=client, governor=gov, subscription_ref="sub-claude", node_id="frontier-w1",
        permission_profile_id="pp-worker", live_auth=_auth(tmp_path), profile_loader=_loader(),
        operator_terms_confirmed=True, backend=MockClaudeCliBackend(), max_tokens=64)
    assert handle.leg == "mock"
    assert gov.status().get("sub-claude", {}).get("in_use") == 1        # I-X3 slot really held

    flow = LiveGovernedFlow(srv["srv"], srv["manifest"], worker_ids=(), worker_handles=(handle,))
    try:
        trace = flow.run(OBJECTIVE)
    finally:
        flow.close()
    assert trace["assignments"] and trace["packet"]["accepted_count"] >= 1
    assert trace["legs"]["workers"] == "mock"
    assert trace["legs"]["worker:frontier-w1"] == "mock"
    assert trace["packet"]["worker_evidence"][0]["verified"] is False
    # D-LOOP-1: closing the flow gave the terminal back
    assert gov.status().get("sub-claude", {}).get("in_use", 0) == 0
    client.close()


def test_live_worker_spawn_refuses_when_live_authorization_is_absent(srv, tmp_path) -> None:
    denied = _auth(tmp_path, {"config_version": "1.1", "live_operation_authorized": False,
                              "register_row": "OP-6",
                              "scope": {"providers": [], "terminals_per_subscription": 1}})
    gov = SubscriptionGovernor()
    client = McpClient("127.0.0.1", srv["srv"].port,
                       srv["srv"].credentials.issue("frontier-w2", "worker", "proj"))
    client.connect()
    with pytest.raises(ProfileViolation):
        live_claude_worker_handle(
            mcp_client=client, governor=gov, subscription_ref="sub-claude", node_id="frontier-w2",
            permission_profile_id="pp-worker", live_auth=denied, profile_loader=_loader(),
            operator_terms_confirmed=True, backend=MockClaudeCliBackend())
    assert gov.status().get("sub-claude", {}).get("in_use", 0) == 0      # nothing acquired on a refused spawn
    client.close()


def test_live_worker_spawn_refuses_when_operator_terms_are_unconfirmed(srv, tmp_path) -> None:
    gov = SubscriptionGovernor()
    client = McpClient("127.0.0.1", srv["srv"].port,
                       srv["srv"].credentials.issue("frontier-w3", "worker", "proj"))
    client.connect()
    with pytest.raises(Exception, match="live-terms|LiveTerms"):
        live_claude_worker_handle(
            mcp_client=client, governor=gov, subscription_ref="sub-claude", node_id="frontier-w3",
            permission_profile_id="pp-worker", live_auth=_auth(tmp_path), profile_loader=_loader(),
            operator_terms_confirmed=False, backend=MockClaudeCliBackend())
    assert gov.status().get("sub-claude", {}).get("in_use", 0) == 0
    client.close()


def test_an_injected_REAL_cli_backend_is_still_gated_on_cli_presence(srv, tmp_path) -> None:
    """Gate (4) keyed on `backend is None`, so the product's own live worker path — which MUST inject
    a backend to widen the call timeout — computed `cli_present` and had it silently ignored. A
    documented gate was provably not on the chain, and an I-X3 terminal was taken before the missing
    CLI surfaced (spec-audit MAJOR-2). A REAL CLI backend now faces the gate; a mock still skips it.
    """
    from adapters.frontier.claude_code import ClaudeCliBackend
    gov = SubscriptionGovernor()
    client = McpClient("127.0.0.1", srv["srv"].port,
                       srv["srv"].credentials.issue("frontier-w5", "worker", "proj"))
    client.connect()
    with pytest.raises(Exception, match="not detected|Unavailable"):
        live_claude_worker_handle(
            mcp_client=client, governor=gov, subscription_ref="sub-claude", node_id="frontier-w5",
            permission_profile_id="pp-worker", live_auth=_auth(tmp_path), profile_loader=_loader(),
            operator_terms_confirmed=True, cli_present=False,
            backend=ClaudeCliBackend())          # a REAL CLI backend — the gate must apply
    assert gov.status().get("sub-claude", {}).get("in_use", 0) == 0, "an I-X3 terminal was acquired"

    # the mock proof is unaffected: it supplies its own backend and needs no host CLI
    handle = live_claude_worker_handle(
        mcp_client=client, governor=gov, subscription_ref="sub-claude", node_id="frontier-w5",
        permission_profile_id="pp-worker", live_auth=_auth(tmp_path), profile_loader=_loader(),
        operator_terms_confirmed=True, cli_present=False, backend=MockClaudeCliBackend())
    assert handle.leg == "mock"
    gov.release("sub-claude", "frontier-w5")
    client.close()


def test_no_live_subprocess_is_reachable_from_this_suite(srv, tmp_path, monkeypatch) -> None:
    """Belt and braces: any real subprocess launch from this suite is a bug, not a live proof."""
    import subprocess
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("a live subprocess was launched"))
    gov = SubscriptionGovernor()
    client = McpClient("127.0.0.1", srv["srv"].port,
                       srv["srv"].credentials.issue("frontier-w4", "worker", "proj"))
    client.connect()
    handle = live_claude_worker_handle(
        mcp_client=client, governor=gov, subscription_ref="sub-claude", node_id="frontier-w4",
        permission_profile_id="pp-worker", live_auth=_auth(tmp_path), profile_loader=_loader(),
        operator_terms_confirmed=True, backend=MockClaudeCliBackend())
    flow = LiveGovernedFlow(srv["srv"], srv["manifest"], worker_ids=(), worker_handles=(handle,))
    try:
        flow.run(OBJECTIVE)
    finally:
        flow.close()
    client.close()
