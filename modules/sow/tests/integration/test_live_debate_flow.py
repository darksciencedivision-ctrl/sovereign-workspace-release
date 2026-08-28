"""Phase 15D `.debate` — ONE bounded debate end to end over a REAL MCP server, the REAL Debate
Service (Phase 7), the REAL Permission Broker, the REAL cost governor and the REAL live-spawn
gates, driven through the LIVE-capable model binding.

Directive §11 15D / §2.8: ≤5 rounds, evidence-cited assertions, dissent preserved VERBATIM,
per-debate budget + per-caller quota + global cap with a clean budget-exhaustion cutoff, and a
NON-CONDUCTOR caller (the service is not conductor-coupled).

MOCK-FIRST (§10.4): no `claude` process is spawned by this suite. Every live gate still runs —
a mock proof needs an authorized `live_auth` and confirmed operator terms exactly like a live
run — and a mock debate can never be packaged as live (`build_debate_report` refuses).
"""
from __future__ import annotations

import base64
import json
from unittest.mock import patch

import pytest

import adapters.frontier.claude_code as claude_code_module
from adapters.frontier.claude_code import ClaudeCliBackend, MockClaudeCliBackend
from adapters.frontier.process_tree import ManagedCompletedProcess
from control_plane.orchestration.live_debate import (
    ATTEMPTED_LEG,
    DEBATE_REPORT_KEYS,
    BackendDebater,
    DebaterSpec,
    attempt_live_debate,
)
from control_plane.profiles.live_authorization import load_live_authorization
from control_plane.profiles.loader import DeploymentProfile, ProfileLoader
from mcp_server.protocol import McpClient
from mcp_server.server import MCPServer
from node_runtime.supervisor.subscription_governor import SubscriptionGovernor

TOPIC = "Does the candidate artifact satisfy the acceptance criteria?"

# OP-6 two-provider live scope (identical to the adapter/conductor/flow suites)
_VALID_AUTH = {"config_version": "1.1", "live_operation_authorized": True, "register_row": "OP-6",
               "scope": {"providers": ["claude_code", "openai_codex_cli"],
                         "terminals_per_subscription": 2}}


@pytest.fixture()
def srv(tmp_path):
    s = MCPServer(tmp_path / "store")
    s.start()
    yield s
    s.stop()


@pytest.fixture()
def auth_cfg(tmp_path):
    cfg = tmp_path / "live_operation.json"
    cfg.write_text(json.dumps(_VALID_AUTH), encoding="utf-8")
    return cfg


def _seed_evidence(srv, text: str = "the artifact meets every criterion") -> str:
    """Publish a REAL memory entry the debaters may cite, so `SUPPORTED` means a citation that
    actually resolved in MCP — not a string that merely looked like a ref."""
    c = McpClient("127.0.0.1", srv.port, srv.credentials.issue("seed", "operator", "proj"))
    c.connect()
    pub = c.call("publish", kind="evidence", tier="shared_project",
                 content_b64=base64.b64encode(text.encode()).decode("ascii"),
                 provenance={"author_node": "seed", "task_id": None,
                             "ts": "2026-07-19T00:00:00+00:00",
                             "directive_version": "v2.4", "confidence": "high"},
                 status="CANDIDATE")
    c.close()
    return pub["entry_id"]


class _ScriptedCliMock(MockClaudeCliBackend):
    """Mock-classified backend (never live) returning a scripted, well-formed statement."""

    def __init__(self, position: str, refs: list[str], name: str = "scripted") -> None:
        super().__init__(name=name)
        self._position = position
        self._refs = refs

    def generate(self, prompt: str, *, max_tokens: int = 256) -> str:
        self.calls += 1
        return json.dumps({"position": self._position, "evidence_refs": self._refs})


def _cli_response(returncode: int = 0, stdout: str = "", stderr: str = ""):
    """A stubbed CLI transport result — the ONLY thing stubbed when a test needs the REAL
    `ClaudeCliBackend`.

    `attempted` and `live` are claims about the real CLI *class* (a subclass now classifies `mock`),
    so those branches cannot be reached by a mock at all. Stubbing the adapter's process boundary
    keeps its own `generate`, JSON parsing and checkpoint stamping on the real code path while
    spawning nothing. No test in this suite asserts a `live` leg — see
    `test_no_leg_in_this_MOCK_FIRST_suite_can_reach_live`.

    U163: this used to stub `subprocess.run`, which the adapter STOPPED calling on 2026-07-28 (it
    moved to `run_managed_process`). The stub then intercepted nothing and these tests spent real
    subscription calls — one of them reporting the `live` leg it exists to prove impossible. The
    stub must name the seam the adapter actually uses, and `tests/conftest.py` now refuses a
    provider spawn outright if it ever drifts again.
    """
    return ManagedCompletedProcess(args=["claude"], returncode=returncode,
                                   stdout=stdout, stderr=stderr, spawned_pids=())


def _specs(a_backend, b_backend) -> list[DebaterSpec]:
    return [DebaterSpec("worker-A", backend=a_backend), DebaterSpec("worker-B", backend=b_backend)]


def _run(srv, auth_cfg, *, specs, governor=None, terms=True, **kw):
    return attempt_live_debate(
        topic=TOPIC, server=srv, governor=governor or SubscriptionGovernor(),
        subscription_ref="sub-anthropic", live_auth=load_live_authorization(auth_cfg),
        profile_loader=ProfileLoader(DeploymentProfile("cloud")),
        operator_terms_confirmed=terms, debaters=specs, cli_present=True, **kw)


# --- the governed bounded debate ------------------------------------------------------------

def test_bounded_debate_runs_publishes_a_debate_record_and_reports_honest_legs(srv, auth_cfg) -> None:
    ref = _seed_evidence(srv)
    out = _run(srv, auth_cfg,
               specs=_specs(_ScriptedCliMock("it satisfies them", [ref], "A"),
                            _ScriptedCliMock("it satisfies them", [ref], "B")),
               evidence_refs=[ref])

    assert out.ran and out.published and not out.skipped_with_record
    assert out.debate_id.startswith("d-")
    assert out.mcp_entry.startswith("m-")
    # an INJECTED mock is never packaged as live, even though every live gate passed
    assert out.legs == {"worker-A": "mock", "worker-B": "mock"}
    assert out.report["debater_models"] == {}
    assert out.report["operator_disposition"] == "pending"
    assert out.report["caller_node"] == "worker-A"       # non-conductor caller (§2.8)


def test_the_request_names_participants_by_EACH_SPEC_S_OWN_CAPABILITY_DESCRIPTOR(srv, auth_cfg) -> None:
    """Invariant 4 / I-SC1: participants are declared by capability descriptor, never by node or
    vendor name — and the descriptor recorded is the one the SPEC declared, not a constant. A
    debate over a coding artifact whose record says every participant was a `reasoning` node
    misdescribes what was consulted.
    """
    ref = _seed_evidence(srv)
    out = _run(srv, auth_cfg,
               specs=[DebaterSpec("worker-A", backend=_ScriptedCliMock("a", [ref], "A"),
                                  capability="coding", requirements={"tool_use": True}),
                      DebaterSpec("worker-B", backend=_ScriptedCliMock("b", [ref], "B"),
                                  capability="review", requirements={"structured_output": True})],
               evidence_refs=[ref])

    reader = McpClient("127.0.0.1", srv.port, srv.credentials.issue("audit", "operator", "proj"))
    reader.connect()
    try:
        content = json.loads(base64.b64decode(
            reader.call("get_content", entry_id=out.mcp_entry)["content_b64"]))
    finally:
        reader.close()

    participants = content["request"]["participants"]
    assert participants == [{"capability": "coding", "requirements": {"tool_use": True}},
                            {"capability": "review", "requirements": {"structured_output": True}}]
    # no node or vendor name leaked into the participant declaration
    assert "worker-A" not in json.dumps(participants)


def test_the_published_record_is_a_readable_CANDIDATE_debate_entry_in_MCP(srv, auth_cfg) -> None:
    ref = _seed_evidence(srv)
    out = _run(srv, auth_cfg,
               specs=_specs(_ScriptedCliMock("yes", [ref], "A"), _ScriptedCliMock("yes", [ref], "B")),
               evidence_refs=[ref])

    reader = McpClient("127.0.0.1", srv.port, srv.credentials.issue("audit", "operator", "proj"))
    reader.connect()
    try:
        head = reader.call("get_head", entry_id=out.mcp_entry)
        content = json.loads(base64.b64decode(
            reader.call("get_content", entry_id=out.mcp_entry)["content_b64"]))
    finally:
        reader.close()

    assert head["status"] == "CANDIDATE"        # workers publish CANDIDATE, never self-canonize
    assert content["schema"] == "debate@1.0"
    assert content["debate_id"] == out.debate_id


def test_a_citation_that_resolves_in_MCP_is_SUPPORTED_and_a_fabricated_one_is_not(srv, auth_cfg) -> None:
    """Evidence-based, not a popularity contest: support comes from a ref that actually resolves."""
    ref = _seed_evidence(srv)
    out = _run(srv, auth_cfg,
               specs=_specs(_ScriptedCliMock("backed", [ref], "A"),
                            _ScriptedCliMock("unbacked", ["m-does-not-exist"], "B")),
               evidence_refs=[ref, "m-does-not-exist"])

    emap = out.report["evidence_map"]
    assert emap["worker-A@r1"]["status"] == "SUPPORTED"
    assert emap["worker-B@r1"]["status"] == "UNSUPPORTED"
    assert emap["worker-B@r1"]["unresolved_refs"] == ["m-does-not-exist"]


# --- bounds: rounds, budget, quota, cap -----------------------------------------------------

def test_debate_converges_early_and_does_not_burn_the_round_cap(srv, auth_cfg) -> None:
    ref = _seed_evidence(srv)
    out = _run(srv, auth_cfg,
               specs=_specs(_ScriptedCliMock("agreed", [ref], "A"), _ScriptedCliMock("agreed", [ref], "B")),
               evidence_refs=[ref], max_rounds=5, budget_units=1_000)

    assert out.report["outcome"] == "CONVERGED"
    assert out.report["rounds_used"] == 1        # early stop — real tokens are not spent for show
    assert out.report["dissent"] is None


def test_dissent_is_PRESERVED_VERBATIM_when_participants_do_not_converge(srv, auth_cfg) -> None:
    ref = _seed_evidence(srv)
    out = _run(srv, auth_cfg,
               specs=_specs(_ScriptedCliMock("it satisfies them", [ref], "A"),
                            _ScriptedCliMock("it does NOT satisfy criterion 3", [ref], "B")),
               evidence_refs=[ref], max_rounds=2, budget_units=1_000)

    assert out.report["outcome"] == "DISSENT_PRESERVED"
    assert out.report["rounds_used"] == 2
    # verbatim — both positions survive, neither is smoothed into a consensus (invariant 15)
    assert "it satisfies them" in out.report["dissent"]
    assert "it does NOT satisfy criterion 3" in out.report["dissent"]


def test_exhausted_budget_cuts_off_CLEANLY_with_the_partial_record_kept(srv, auth_cfg) -> None:
    """Invariant 17: the budget is a HARD cap. Exhaustion is a clean cutoff, never a silent
    truncation and never an overrun."""
    ref = _seed_evidence(srv)
    out = _run(srv, auth_cfg,
               specs=_specs(_ScriptedCliMock("A position", [ref], "A"),
                            _ScriptedCliMock("B position", [ref], "B")),
               evidence_refs=[ref], max_rounds=5, budget_units=150, round_cost=100)

    assert out.published                                  # the partial record IS kept
    assert out.report["outcome"] == "BUDGET_EXHAUSTED"
    assert out.report["rounds_used"] == 1                 # a 2nd round would exceed 150
    assert out.report["cost_actual"]["usage_units"] == 100     # charged once, never over the cap
    assert out.report["cost_actual"]["usage_units"] <= out.report["budget"]["usage_units"]


def test_a_request_over_the_five_round_hard_cap_is_REFUSED(srv, auth_cfg) -> None:
    """Invariant 14: ≤5 rounds. The request is refused outright rather than quietly clamped."""
    ref = _seed_evidence(srv)
    out = _run(srv, auth_cfg,
               specs=_specs(_ScriptedCliMock("a", [ref], "A"), _ScriptedCliMock("b", [ref], "B")),
               evidence_refs=[ref], max_rounds=9)

    assert not out.published and out.skipped_with_record
    assert "max_rounds" in out.reason


def test_a_debate_whose_only_participant_is_the_caller_is_REFUSED(srv, auth_cfg) -> None:
    """Invariant 18: no node solely judges its own work."""
    with pytest.raises(ValueError, match="at least two"):
        _run(srv, auth_cfg, specs=[DebaterSpec("worker-A", backend=MockClaudeCliBackend())])


def test_the_DebateService_still_refuses_a_caller_that_is_its_own_sole_judge(srv, auth_cfg) -> None:
    """Invariant 18 is enforced authoritatively by the Debate Service, not re-implemented here.

    `attempt_live_debate` cannot construct the violating case (unique ids + ≥2 participants make
    "every participant is the caller" unconstructible), so the service's own check is exercised
    directly — otherwise nothing would pin that the enforcement still exists.
    """
    from control_plane.policy import Identity, SovereignPolicy
    from debate_service.cost_governor.governor import CostGovernor
    from debate_service.evidence_manager.manager import EvidenceManager, mcp_resolver
    from debate_service.service import DebateAuthorizationError, DebateService

    from control_plane.orchestration.live_debate import BackendDebater

    client = McpClient("127.0.0.1", srv.port, srv.credentials.issue("worker-A", "worker", "proj"))
    client.connect()
    try:
        service = DebateService(SovereignPolicy(), CostGovernor(),
                                EvidenceManager(mcp_resolver(client)), client)
        with pytest.raises(DebateAuthorizationError, match="invariant 18"):
            service.request_debate(
                Identity(node_id="worker-A", role="worker", project_id="proj"),
                {"topic": TOPIC, "max_rounds": 2, "budget": {"tokens": 200},
                 "participants": [{"capability": "reasoning", "requirements": {}}]},
                [BackendDebater("worker-A", _ScriptedCliMock("solo", [], "A"))])
    finally:
        client.close()


# --- the live gates: unmet ⇒ skip-with-record, NO live call ---------------------------------

def test_unconfirmed_operator_terms_skips_with_record_and_makes_NO_call(srv, auth_cfg) -> None:
    specs = _specs(_ScriptedCliMock("a", [], "A"), _ScriptedCliMock("b", [], "B"))
    out = _run(srv, auth_cfg, specs=specs, terms=False)

    assert out.skipped_with_record and not out.ran and not out.published
    assert "LiveTermsNotConfirmed" in out.reason
    assert out.legs == {"worker-A": "skipped", "worker-B": "skipped"}
    assert all(s.backend.calls == 0 for s in specs)      # nothing was spent


def test_absent_live_authorization_skips_with_record(srv, tmp_path) -> None:
    missing = tmp_path / "no_such_live_operation.json"
    out = attempt_live_debate(
        topic=TOPIC, server=srv, governor=SubscriptionGovernor(), subscription_ref="sub-anthropic",
        live_auth=load_live_authorization(missing),          # absence ⇒ DENIED, not an error
        profile_loader=ProfileLoader(DeploymentProfile("cloud")), operator_terms_confirmed=True,
        debaters=_specs(_ScriptedCliMock("a", [], "A"), _ScriptedCliMock("b", [], "B")),
        cli_present=True)

    assert out.skipped_with_record and not out.published
    assert out.legs == {"worker-A": "skipped", "worker-B": "skipped"}


def test_a_completed_debate_RELEASES_its_I_X3_terminals(srv, auth_cfg) -> None:
    """Teardown is inside the unit (D-LOOP-1): every acquired terminal is released, so the next
    spawn on the same subscription is not blocked by a debate that already ended.

    Uses DISTINCT node ids per round. Reusing ids would make this vacuous —
    `SubscriptionGovernor.acquire` early-returns when the node is already active, so a run that
    released nothing would still pass. Fresh ids force a real release.
    """
    governor = SubscriptionGovernor()
    ref = _seed_evidence(srv)
    for i in range(3):                     # allowance is 2 — a leak fails on the 2nd round
        out = attempt_live_debate(
            topic=TOPIC, server=srv, governor=governor, subscription_ref="sub-anthropic",
            live_auth=load_live_authorization(auth_cfg),
            profile_loader=ProfileLoader(DeploymentProfile("cloud")), operator_terms_confirmed=True,
            caller_node_id=f"caller-{i}",
            debaters=[DebaterSpec(f"w{i}-A", backend=_ScriptedCliMock("a", [ref], f"A{i}")),
                      DebaterSpec(f"w{i}-B", backend=_ScriptedCliMock("b", [ref], f"B{i}"))],
            evidence_refs=[ref], cli_present=True)
        assert out.published, out.reason

    assert governor.status()["sub-anthropic"]["in_use"] == 0
    assert governor.status()["sub-anthropic"]["active"] == []


def test_a_debate_REFUSED_after_spawning_also_releases_its_terminals(srv, auth_cfg) -> None:
    """The release must not be on the success path only — a refused debate that held its slots
    would wedge the subscription just as thoroughly."""
    governor = SubscriptionGovernor()
    out = _run(srv, auth_cfg, governor=governor,
               specs=_specs(_ScriptedCliMock("a", [], "A"), _ScriptedCliMock("b", [], "B")),
               max_rounds=9)                       # refused by the ≤5 hard cap, after spawning

    assert not out.published
    assert governor.status()["sub-anthropic"]["in_use"] == 0


def test_a_failure_AFTER_the_rounds_ran_still_releases_every_terminal(srv, auth_cfg) -> None:
    """The post-round tail (build + publish) must not escape without teardown.

    `_publish_report` is a real MCP round-trip on the live path; an unguarded raise there would
    leave every I-X3 terminal held — the same wedge the release fix closed on the paths above,
    relocated into the fix itself. Injected via a clock that fails after the debate has run.
    """
    governor = SubscriptionGovernor()
    ref = _seed_evidence(srv)

    def _exploding_clock():
        raise RuntimeError("clock failed after the rounds ran")

    out = _run(srv, auth_cfg, governor=governor,
               specs=_specs(_ScriptedCliMock("a", [ref], "A"), _ScriptedCliMock("b", [ref], "B")),
               evidence_refs=[ref], clock=_exploding_clock)

    assert governor.status()["sub-anthropic"]["in_use"] == 0     # nothing leaked
    # the run DEGRADES rather than being destroyed: the debate record is already durable
    assert out.published and out.debate_id and out.mcp_entry
    assert out.report_entry is None
    assert "could not be built or published" in out.reason
    assert "RuntimeError" in out.reason


def test_spend_from_an_EARLIER_debate_is_not_attributed_to_this_refused_one(
        srv, auth_cfg) -> None:
    """Legs describe THIS debate, not the backend's lifetime.

    An earlier version of this test asserted the opposite — that a backend handed in already-spent
    makes `ran=True` "observably correct", on the grounds that over-reporting spend is the honest
    direction (§6). That conflated two different things. Over-reporting is the safe direction for
    *whether* a call was spent; it is not a licence to bill THIS debate for calls another one made.
    `calls` is a lifetime counter, so the only way to describe this debate is to compare against a
    bind-time snapshot. Refused before any round ⇒ this debate spent nothing ⇒ `skipped`.
    """
    spent_a = _ScriptedCliMock("a", [], "A")
    spent_b = _ScriptedCliMock("b", [], "B")
    spent_a.calls = 7                       # reused backends, spent in a PREVIOUS debate
    spent_b.calls = 3

    out = _run(srv, auth_cfg, specs=_specs(spent_a, spent_b), max_rounds=9)   # refused: >5 cap

    assert not out.published and out.skipped_with_record
    assert out.legs == {"worker-A": "skipped", "worker-B": "skipped"}
    assert out.ran is False
    assert spent_a.calls == 7 and spent_b.calls == 3      # and nothing was spent here


def test_duplicate_debater_node_ids_are_REFUSED_before_anything_is_spawned(srv, auth_cfg) -> None:
    """Duplicates would collapse the per-debater leg map onto the last spec — erasing a real
    subscription-spending call — and `acquire` is idempotent per node id, so they would also
    under-count the I-X3 terminals actually spawned.
    """
    governor = SubscriptionGovernor()
    real = _ScriptedCliMock("a", [], "A")
    with pytest.raises(ValueError, match="unique"):
        _run(srv, auth_cfg, governor=governor,
             specs=[DebaterSpec("worker-A", backend=real),
                    DebaterSpec("worker-A", backend=_ScriptedCliMock("b", [], "B"))])
    assert real.calls == 0
    assert governor.status() == {}


@pytest.mark.parametrize("role", ["gate", "operator", "", "admin"])
def test_an_authority_bearing_or_unknown_DEBATER_role_is_REFUSED(srv, auth_cfg, role) -> None:
    """The MCP credential is minted from the role string, and `gate`/`operator` carry transition
    authority a debate worker has no need of — so the whitelist refuses them, fail closed.

    Honest scope (the module comment records the same): this closes no gap that was open.
    `SovereignPolicy` already refuses a gate promoting an entry it authored (invariant 18). It is
    defence in depth — minting an authority-bearing credential for a node that needs none is the
    wrong default — not a fix for a reachable escalation.
    """
    with pytest.raises(ValueError, match="not permitted"):
        _run(srv, auth_cfg,
             specs=[DebaterSpec("worker-A", backend=_ScriptedCliMock("a", [], "A"), role=role),
                    DebaterSpec("worker-B", backend=_ScriptedCliMock("b", [], "B"))])


@pytest.mark.parametrize("role", ["gate", "operator", "", "admin"])
def test_an_authority_bearing_or_unknown_CALLER_role_is_REFUSED(srv, auth_cfg, role) -> None:
    """The caller's role is whitelisted too: the caller's client publishes both the debate record
    and the report, so it is the identity stamped on the shared entries.

    Covered separately because parametrizing only debater roles left the caller branch of the
    whitelist unexercised. Same honest scope as the debater case — an earlier docstring here
    claimed a `gate` caller "could promote its own debate output", which `SovereignPolicy` already
    refuses (invariant 18). Defence in depth, not a closed escalation.
    """
    with pytest.raises(ValueError, match="not permitted"):
        _run(srv, auth_cfg,
             specs=_specs(_ScriptedCliMock("a", [], "A"), _ScriptedCliMock("b", [], "B")),
             caller_role=role)


def test_a_node_id_already_holding_a_terminal_is_REFUSED_not_silently_shared(srv, auth_cfg) -> None:
    """`governor.acquire` is idempotent per node id, so spawning onto an id someone else holds
    would piggyback on THEIR terminal and then release THEIR slot at teardown — under-counting
    live terminals, the dishonest I-X3 direction.
    """
    governor = SubscriptionGovernor()
    governor.register_subscription("sub-anthropic", "claude_code", allowance=2)
    governor.acquire("sub-anthropic", "worker-A")          # an external holder

    with pytest.raises(ValueError, match="already hold"):
        _run(srv, auth_cfg, governor=governor,
             specs=_specs(_ScriptedCliMock("a", [], "A"), _ScriptedCliMock("b", [], "B")))

    # the external holder's slot survives untouched
    assert governor.status()["sub-anthropic"]["active"] == ["worker-A"]


def test_two_debaters_sharing_ONE_backend_instance_are_REFUSED(srv, auth_cfg) -> None:
    """Invariant 18 in substance: one model agreeing with itself under two labels would converge
    trivially at round 1 and satisfy a node-id-based check on a technicality."""
    shared = _ScriptedCliMock("we agree", [], "shared")
    with pytest.raises(ValueError, match="share one backend"):
        _run(srv, auth_cfg,
             specs=[DebaterSpec("worker-A", backend=shared),
                    DebaterSpec("worker-B", backend=shared)])
    assert shared.calls == 0


def test_a_shared_cost_governor_binds_the_PER_CALLER_QUOTA_across_debates(srv, auth_cfg) -> None:
    """Invariant 17's per-caller quota is only meaningful ACROSS debates, which requires the
    governor to be INJECTABLE — a fresh one per call binds nothing.

    Named for the quota, which is what this pins. The GLOBAL CONCURRENT CAP is NOT proven here:
    these debates run strictly in sequence, so a cap of 4 is never approached. That remains
    unproven through this entrypoint and is recorded as owed rather than implied by the name.
    """
    from debate_service.cost_governor.governor import CostGovernor

    ref = _seed_evidence(srv)
    shared = CostGovernor(per_caller_quota=250, global_concurrent_cap=4)

    first = _run(srv, auth_cfg, cost_governor=shared,
                 specs=_specs(_ScriptedCliMock("a", [ref], "A1"), _ScriptedCliMock("a", [ref], "B1")),
                 evidence_refs=[ref], budget_units=200, round_cost=100)
    assert first.published and first.report["cost_actual"]["usage_units"] == 100

    # the caller's quota is now committed across debates, not reset
    assert int(shared.committed("worker-A")) == 100
    second = _run(srv, auth_cfg, cost_governor=shared,
                  specs=_specs(_ScriptedCliMock("x", [ref], "A2"), _ScriptedCliMock("y", [ref], "B2")),
                  evidence_refs=[ref], budget_units=200, round_cost=100, max_rounds=5)
    # Only 150 of the 250 quota remained, so `open_debate` reserved min(200, 150)=150 and just
    # ONE round could be charged. With a fresh governor per call the same request would have run
    # TWO rounds on its own 200 budget — that difference is the cross-debate binding.
    assert second.report["outcome"] == "BUDGET_EXHAUSTED"
    assert second.report["rounds_used"] == 1
    assert int(shared.committed("worker-A")) == 200


def test_exceeding_the_subscription_allowance_skips_with_record(srv, auth_cfg) -> None:
    """I-X3: allowance is 2 under OP-6. A third concurrent terminal is refused, fail closed.

    Also pins teardown on the PARTIAL-SPAWN-FAILURE path (loop constraint D-LOOP-1). Deleting the
    `_teardown()` call on this branch previously survived the whole suite: two terminals were
    acquired before the third was refused, and nothing asserted they came back. A wedged
    subscription sits permanently at allowance and the governor's count then describes terminals
    that no longer exist.
    """
    governor = SubscriptionGovernor()
    out = _run(srv, auth_cfg, governor=governor,
               specs=[DebaterSpec(f"worker-{i}", backend=_ScriptedCliMock("p", [], f"B{i}"))
                      for i in range(3)])

    assert out.skipped_with_record and not out.published
    assert out.legs["worker-2"] == "skipped"
    # the two terminals that WERE acquired before the refusal are released
    assert governor.status()["sub-anthropic"]["in_use"] == 0
    assert governor.status()["sub-anthropic"]["active"] == []


# --- leg honesty on the live-classified path ------------------------------------------------

def test_a_real_backend_that_spends_a_call_then_fails_is_ATTEMPTED_never_skipped(srv, auth_cfg) -> None:
    """Under-reporting spend is the dishonest direction (§6).

    Uses the REAL `ClaudeCliBackend` with only its subprocess transport stubbed: `attempted` is a
    claim about the real CLI class, and a subclass now classifies `mock`, so a subclass could not
    exercise this branch at all. The adapter's own `generate` runs — it counts the call BEFORE the
    transport, which is what makes a failed call still countable spend.
    """
    ref = _seed_evidence(srv)
    with patch.object(claude_code_module, "run_managed_process",
                      return_value=_cli_response(returncode=1, stderr="transport died")):
        out = _run(srv, auth_cfg,
                   specs=[DebaterSpec("worker-A", backend=ClaudeCliBackend()),
                          DebaterSpec("worker-B", backend=_ScriptedCliMock("b", [ref], "B"))],
                   evidence_refs=[ref])

    # the debate itself completes (a dead backend refuses, it does not abort the round manager)
    assert out.published
    assert out.legs["worker-A"] == ATTEMPTED_LEG      # a call WAS spent — not "skipped"
    assert out.legs["worker-B"] == "mock"
    assert out.report["debater_models"] == {}         # nothing verified ⇒ no checkpoint claimed
    assert any("RuntimeError" in n["note"] for n in out.report["debater_notes"])


def test_a_SUBCLASS_that_never_ran_the_CLI_cannot_be_packaged_as_LIVE(srv, auth_cfg) -> None:
    """REGRESSION — this is the defect this suite itself once asserted as correct behaviour.

    An earlier version of this test defined exactly the backend below, called it "the ONLY path to
    a `live` leg", and asserted `legs["worker-A"] == "live"`. It is a mock: it spawns no process
    and writes the checkpoint itself. `isinstance` accepted it because it inherits
    `ClaudeCliBackend`, so a substituted result was packaged as a real-provider one — precisely
    what §6/§10.4 forbid. Classification is now on EXACT type, so class identity cannot be
    inherited into a live claim.
    """
    class _ReportingCli(ClaudeCliBackend):
        def generate(self, prompt, *, max_tokens=256):
            self.calls += 1
            self.reported_model = "claude-opus-4-8-20260101"
            self.reported_model_at_call = self.calls      # forges the freshness stamp too
            return json.dumps({"position": "it satisfies them", "evidence_refs": []})

    out = _run(srv, auth_cfg,
               specs=[DebaterSpec("worker-A", backend=_ReportingCli()),
                      DebaterSpec("worker-B", backend=_ScriptedCliMock("other", [], "B"))])

    assert out.published
    assert out.legs["worker-A"] == "mock"            # NOT live, and not even `attempted`
    assert out.report["debater_models"] == {}        # no checkpoint claimed for anyone
    assert "live" not in out.report["legs"].values()


def test_a_STALE_checkpoint_from_an_earlier_debate_cannot_make_THIS_one_live(srv, auth_cfg) -> None:
    """`reported_model` is never cleared and `calls` is a LIFETIME counter.

    A real backend reused across debates therefore arrives carrying a checkpoint it earned
    elsewhere. If every call in THIS debate fails, nothing here ran — so `live` would attribute
    another debate's evidence to this one. Legs are judged against a bind-time snapshot.
    """
    ref = _seed_evidence(srv)
    cli = ClaudeCliBackend()
    cli.calls = 4                                     # spent in a previous debate...
    cli.reported_model = "claude-opus-4-8-20260101"   # ...which reported a checkpoint
    cli.reported_model_at_call = 4

    with patch.object(claude_code_module, "run_managed_process",
                      return_value=_cli_response(returncode=1, stderr="transport died")):
        out = _run(srv, auth_cfg,
                   specs=[DebaterSpec("worker-A", backend=cli),
                          DebaterSpec("worker-B", backend=_ScriptedCliMock("b", [ref], "B"))],
                   evidence_refs=[ref])

    assert out.published
    assert cli.calls > 4                              # this debate really did spend calls
    assert out.legs["worker-A"] == ATTEMPTED_LEG      # spent here, verified nothing here
    assert out.report["debater_models"] == {}         # the stale checkpoint is NOT claimed


def test_a_GENERIC_exception_out_of_the_debate_also_tears_down(srv, auth_cfg) -> None:
    """D-LOOP-1 on the generic-exception exit path.

    Teardown was pinned on the success, refusal, partial-spawn and report-tail paths, but deleting
    `_teardown()` from THIS branch survived the whole suite. Every exit must release: a wedged
    subscription sits permanently at allowance and the governor's count then describes terminals
    that no longer exist.
    """
    governor = SubscriptionGovernor()

    with patch.object(BackendDebater, "argue",
                      lambda self, *a, **kw: (_ for _ in ()).throw(RuntimeError("escaped"))):
        out = _run(srv, auth_cfg, governor=governor,
                   specs=_specs(_ScriptedCliMock("a", [], "A"), _ScriptedCliMock("b", [], "B")))

    assert out.skipped_with_record and not out.published
    assert "RuntimeError" in out.reason
    assert governor.status()["sub-anthropic"]["in_use"] == 0
    assert governor.status()["sub-anthropic"]["active"] == []


def test_no_leg_in_this_MOCK_FIRST_suite_can_reach_live(srv, auth_cfg) -> None:
    """The §10.4 posture, pinned rather than assumed.

    A `live` leg requires the real CLI class to report a checkpoint from its own JSON for a call
    made during the debate — which requires actually spawning `claude`. This suite spawns nothing,
    so `live` must be unreachable end to end here. If a future change makes a `live` leg
    constructible without a real call, this fails.
    """
    ref = _seed_evidence(srv)
    cli = ClaudeCliBackend()
    with patch.object(claude_code_module, "run_managed_process",
                      return_value=_cli_response(returncode=1, stderr="no CLI here")):
        out = _run(srv, auth_cfg,
                   specs=[DebaterSpec("worker-A", backend=cli),
                          DebaterSpec("worker-B", backend=_ScriptedCliMock("b", [ref], "B"))],
                   evidence_refs=[ref])

    assert set(out.report["legs"].values()) <= {ATTEMPTED_LEG, "mock", "skipped"}
    assert out.report["debater_models"] == {}


def test_a_mock_CANNOT_be_packaged_as_live_by_naming_itself_after_the_CLI(srv, auth_cfg) -> None:
    out = _run(srv, auth_cfg,
               specs=_specs(_ScriptedCliMock("a", [], name="claude_code:cli:opus-4.8"),
                            _ScriptedCliMock("b", [], "B")))
    assert out.legs["worker-A"] == "mock"
    assert out.report["debater_models"] == {}


# --- scoping (invariant 8) on the real path -------------------------------------------------

def test_a_debater_cannot_cite_evidence_outside_its_scoped_set(srv, auth_cfg) -> None:
    """The out-of-scope ref is dropped AND noted — never silently kept, never silently lost."""
    in_scope = _seed_evidence(srv, "in scope")
    out_of_scope = _seed_evidence(srv, "out of scope")    # a REAL entry it was not scoped to
    out = _run(srv, auth_cfg,
               specs=_specs(_ScriptedCliMock("a", [in_scope, out_of_scope], "A"),
                            _ScriptedCliMock("b", [in_scope], "B")),
               evidence_refs=[in_scope])

    positions = {p["node"]: p for p in out.report["positions"]}
    assert positions["worker-A"]["evidence_refs"] == [in_scope]
    assert any(out_of_scope in n["note"] for n in out.report["debater_notes"])


def test_dropped_citations_and_backend_refusals_reach_the_DURABLE_record_not_just_the_trace(
        srv, auth_cfg) -> None:
    """The frozen debate@1.0 record carries only FILTERED evidence_refs — an operator reading it
    alone would see a clean debate with no sign that a node cited out-of-scope evidence or that a
    backend died. The report is therefore published as its own CANDIDATE entry.
    """
    in_scope = _seed_evidence(srv, "in scope")
    out_of_scope = _seed_evidence(srv, "out of scope")

    class _DeadCli(MockClaudeCliBackend):
        def generate(self, prompt, *, max_tokens=256):
            self.calls += 1
            raise RuntimeError("backend died mid-debate")

    out = _run(srv, auth_cfg,
               specs=[DebaterSpec("worker-A", backend=_ScriptedCliMock("a", [in_scope, out_of_scope], "A")),
                      DebaterSpec("worker-B", backend=_DeadCli())],
               evidence_refs=[in_scope])

    assert out.published and out.report_entry and out.report_entry != out.mcp_entry

    reader = McpClient("127.0.0.1", srv.port, srv.credentials.issue("audit", "operator", "proj"))
    reader.connect()
    try:
        head = reader.call("get_head", entry_id=out.report_entry)
        durable = json.loads(base64.b64decode(
            reader.call("get_content", entry_id=out.report_entry)["content_b64"]))
        frozen = json.loads(base64.b64decode(
            reader.call("get_content", entry_id=out.mcp_entry)["content_b64"]))
    finally:
        reader.close()

    # The RETURNED report matches the pinned key set and is byte-identical to what was published:
    # stamping the report with its own entry id would add a key the guard already passed on, and
    # would make the in-process object diverge from the durable artifact an operator reads.
    assert tuple(out.report) == DEBATE_REPORT_KEYS
    assert durable == out.report

    assert head["status"] == "CANDIDATE"          # never self-canonized (invariant 10)
    assert durable["schema"] == "debate_report@1.0"
    assert durable["debate_id"] == out.debate_id
    # both deviations survive in the DURABLE artifact
    notes = json.dumps(durable["debater_notes"])
    assert out_of_scope in notes and "RuntimeError" in notes
    assert durable["legs"] == {"worker-A": "mock", "worker-B": "mock"}
    # ...and neither is visible in the frozen debate record alone — which is why this exists
    assert out_of_scope not in json.dumps(frozen)


def test_the_prompt_a_debater_receives_carries_only_the_scoped_tail(srv, auth_cfg) -> None:
    """Invariant 8 on the REAL debater object, not just the pure prompt builder."""
    seen: list[str] = []

    class _Recording(MockClaudeCliBackend):
        def generate(self, prompt, *, max_tokens=256):
            self.calls += 1
            seen.append(prompt)
            return json.dumps({"position": f"round {len(seen)}", "evidence_refs": []})

    d = BackendDebater("worker-A", _Recording(), allowed_evidence=("m-1",))
    transcript = [{"round": r, "positions": [{"node": "worker-B", "position": f"claim-r{r}"}]}
                  for r in (1, 2, 3)]
    d.argue(TOPIC, 4, transcript)

    assert "claim-r3" in seen[0]
    assert "claim-r1" not in seen[0] and "claim-r2" not in seen[0]
