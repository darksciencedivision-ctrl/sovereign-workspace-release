"""U45 discharge — the ONE checkpoint-verification rule, applied at every site (`phase-15d.gate`).

`.debate` established the rule that backs a `live` claim (exact vendor type + a non-blank checkpoint
the CLI itself reported + freshness against a bind-time snapshot + evidence a call was spent) but
applied it in ONE module. U45 recorded that three already-gated sites kept the pre-fix behaviour:

  1. `live_flow._leg_for_backend`        — subclass-permissive `isinstance`
  2. `selection.bind_conductor_selection` — verified from a caller-supplied string, no type, no freshness
  3. `claude_code.ClaudeCodeConductorBackend.propose_plan` — no freshness

These tests pin the discharge. They are written against the DIRECTION that matters: every route by
which a run that did NOT reach a real provider could be recorded as one must be refused. The
positive `live` contract is exercised only at the classifier level with fabricated instrumentation,
never end to end — reaching `live` for real requires spawning a `claude` process, which this
MOCK-FIRST suite must not do (the posture `.flow`/`.debate` adopted).
"""
from __future__ import annotations

import pytest

from adapters.frontier.claude_code import (
    ClaudeCliBackend,
    ClaudeCodeConductorBackend,
    MockClaudeCliBackend,
    bind_calls_snapshot,
    is_live_cli_backend,
    verify_reported_checkpoint,
)
from control_plane.conductor.selection import (
    ExecutingEvidence,
    ConductorSelectionError,
    bind_conductor_selection,
)
from control_plane.orchestration.live_flow import _leg_for_backend


# --------------------------------------------------------------------------------------
# helpers — every shape a NON-live backend can take while trying to look live
# --------------------------------------------------------------------------------------

class _SubclassBackend(ClaudeCliBackend):
    """The exact defect U45 names: inherits the vendor class, spawns nothing."""

    def generate(self, prompt: str, *, max_tokens: int = 256) -> str:  # noqa: D102
        self.calls += 1
        self.reported_model = "claude-fable-5-20260101"
        self.reported_model_at_call = self.calls
        return "canned"


class _DuckBackend:
    """Not the vendor class at all, but wears every instrumentation attribute."""

    def __init__(self) -> None:
        self.name = "claude_code:cli:fable-5"
        self.calls = 1
        self.reported_model = "claude-fable-5-20260101"
        self.reported_model_at_call = 1

    def generate(self, prompt: str, *, max_tokens: int = 256) -> str:  # noqa: D102
        return "canned"


def _genuine(*, reported: object = "claude-fable-5-20260101", at_call: object = 1,
             calls: int = 1) -> ClaudeCliBackend:
    """A REAL `ClaudeCliBackend` with instrumentation set by hand — never called, nothing spawned.

    This is how the positive path is tested: the object's CLASS is genuine (which is all exact-type
    checking establishes) while its behaviour is not. That gap is U43, stated, not closed here.
    """
    backend = ClaudeCliBackend(model="fable-5")
    backend.reported_model = reported  # type: ignore[assignment]
    backend.reported_model_at_call = at_call  # type: ignore[assignment]
    backend.calls = calls
    return backend


# --------------------------------------------------------------------------------------
# 1. the primitive
# --------------------------------------------------------------------------------------

def test_only_the_exact_vendor_class_is_a_live_cli_backend():
    assert is_live_cli_backend(ClaudeCliBackend()) is True
    # a subclass inherits the identity but may spawn nothing — the defect U45 names
    assert is_live_cli_backend(_SubclassBackend()) is False
    assert is_live_cli_backend(_DuckBackend()) is False
    assert is_live_cli_backend(MockClaudeCliBackend()) is False
    assert is_live_cli_backend(None) is False


def test_verification_requires_type_checkpoint_freshness_and_spend():
    # the positive contract, at classifier level only (no process spawned — see _genuine)
    assert verify_reported_checkpoint(_genuine(at_call=2, calls=2), calls_before=1) == {
        "model": "claude-fable-5-20260101", "verified": True}

    # (1) wrong type — a subclass that set both stamps itself
    sub = _SubclassBackend()
    sub.generate("x")
    assert verify_reported_checkpoint(sub, calls_before=0) is None

    # (2) no checkpoint, or a blank/non-string one
    for bad in (None, "", "   ", True, 0, {"model": "x"}, ["x"]):
        assert verify_reported_checkpoint(_genuine(reported=bad, at_call=2, calls=2),
                                          calls_before=1) is None

    # (3) STALE: the checkpoint predates this binding (an earlier run's, every call here failed)
    assert verify_reported_checkpoint(_genuine(at_call=1, calls=5), calls_before=3) is None
    # equal is not after — the snapshot is taken BEFORE the call that would stamp it
    assert verify_reported_checkpoint(_genuine(at_call=3, calls=5), calls_before=3) is None

    # (4) an unstamped or non-int stamp cannot date anything
    for bad_stamp in (None, "2", True, 1.5):
        assert verify_reported_checkpoint(_genuine(at_call=bad_stamp, calls=9),
                                          calls_before=1) is None

    # (5) no snapshot at all: the absence of evidence is not evidence
    assert verify_reported_checkpoint(_genuine(at_call=2, calls=2), calls_before=None) is None

    # (6) a checkpoint with no counted call is CONTRADICTORY (nothing ran, yet something reported)
    assert verify_reported_checkpoint(_genuine(at_call=2, calls=1), calls_before=1) is None


def test_bind_snapshot_resolves_the_same_object_verification_will_read():
    """Snapshot and verification must agree on WHICH counter they are talking about, or freshness
    compares two unrelated numbers. A conductor wrapper is resolved one documented level."""
    raw = ClaudeCliBackend(model="fable-5")
    raw.calls = 4
    assert bind_calls_snapshot(raw) == 4
    assert bind_calls_snapshot(ClaudeCodeConductorBackend(raw)) == 4, (
        "the wrapper's own `calls` counter is NOT the one that stamps checkpoints")
    # nothing vendor behind it => no snapshot => nothing can ever verify against it
    assert bind_calls_snapshot(MockClaudeCliBackend()) is None
    assert bind_calls_snapshot(ClaudeCodeConductorBackend(MockClaudeCliBackend())) is None
    # a wrapper is resolved, but only to a GENUINE inner backend
    assert bind_calls_snapshot(ClaudeCodeConductorBackend(_SubclassBackend())) is None


def test_verification_reads_through_a_conductor_wrapper_but_only_to_a_genuine_backend():
    raw = _genuine(at_call=2, calls=2)
    wrapper = ClaudeCodeConductorBackend(raw)
    assert verify_reported_checkpoint(wrapper, calls_before=1) == {
        "model": "claude-fable-5-20260101", "verified": True}
    # the wrapper cannot launder a non-genuine inner backend
    assert verify_reported_checkpoint(ClaudeCodeConductorBackend(_SubclassBackend()),
                                      calls_before=0) is None
    assert verify_reported_checkpoint(ClaudeCodeConductorBackend(_DuckBackend()),
                                      calls_before=0) is None


# --------------------------------------------------------------------------------------
# 2. site 1 — live_flow._leg_for_backend
# --------------------------------------------------------------------------------------

def test_leg_for_backend_refuses_a_subclass_the_pre_fix_defect():
    """U45 site 1. `isinstance` classified a non-spawning subclass as `live`; exact type does not."""
    assert _leg_for_backend(None) == "live"           # spawn constructs the REAL backend
    assert _leg_for_backend(ClaudeCliBackend()) == "live"
    assert _leg_for_backend(_SubclassBackend()) == "mock"
    assert _leg_for_backend(_DuckBackend()) == "mock"
    assert _leg_for_backend(MockClaudeCliBackend()) == "mock"


# --------------------------------------------------------------------------------------
# 3. site 2 — selection.bind_conductor_selection
# --------------------------------------------------------------------------------------

def test_a_bare_reported_string_can_no_longer_verify_an_executing_checkpoint():
    """U45 site 2. The pre-fix rule was `isinstance(reported_model, str) and strip()` — any caller
    holding a string could mint a verified checkpoint. Now only EVIDENCE verifies, and the raw
    claim is recorded as unverified rather than silently dropped."""
    binding = bind_conductor_selection(reported_model="claude-fable-5-20260101")
    assert binding.executing_verified is False
    assert binding.executing_model is None, "an unverified checkpoint must never reach executing.model"
    record = binding.as_record()
    assert record["executing"]["verified"] is False
    assert record["executing"]["model"] is None
    # not silently discarded: the operator can see a claim was made and was not backed
    assert record["executing"]["reported_unverified"] == "claude-fable-5-20260101"
    assert "unverified" in record["executing"]["note"]


def test_executing_evidence_is_the_only_route_to_verified():
    binding = bind_conductor_selection(
        executing_evidence=ExecutingEvidence("claude-fable-5-20260101"))
    assert binding.executing_verified is True
    assert binding.executing_model == "claude-fable-5-20260101"
    assert binding.as_record()["executing"]["verified"] is True
    # and it carries the checkpoint into the note, replacing the resolver's "unverified" text
    assert "unverified" not in binding.note


def test_executing_evidence_refuses_a_blank_or_non_string_checkpoint():
    for bad in (None, "", "   ", True, 1, ["x"]):
        with pytest.raises(ConductorSelectionError):
            ExecutingEvidence(bad)  # type: ignore[arg-type]


def test_evidence_and_a_conflicting_bare_claim_do_not_silently_disagree():
    """If both arrive and name different checkpoints, the record must not present one as the other."""
    with pytest.raises(ConductorSelectionError):
        bind_conductor_selection(reported_model="claude-opus-4-8",
                                 executing_evidence=ExecutingEvidence("claude-fable-5-20260101"))


def test_label_mismatch_still_only_speaks_about_a_verified_checkpoint():
    assert bind_conductor_selection(reported_model="claude-opus-4-8").label_mismatch() is False
    assert bind_conductor_selection(
        executing_evidence=ExecutingEvidence("claude-opus-4-8")).label_mismatch() is True


# --------------------------------------------------------------------------------------
# 4. site 3 — ClaudeCodeConductorBackend.propose_plan
# --------------------------------------------------------------------------------------

class _StaleReportingBackend:
    """A backend carrying a checkpoint from an EARLIER call, whose `generate` reports nothing new."""

    def __init__(self) -> None:
        self.name = "stale"
        self.calls = 7
        self.reported_model = "claude-fable-5-20260101"
        self.reported_model_at_call = 3          # stamped long before this propose_plan

    def generate(self, prompt: str, *, max_tokens: int = 256) -> str:  # noqa: D102
        self.calls += 1                          # a call IS spent — it just reports nothing
        return '{"proposed_tasks": [{"desc": "d", "capability": "reasoning"}]}'


def test_propose_plan_refuses_a_stale_checkpoint():
    """U45 site 3. Pre-fix, `model_verified` came from `reported_model` with no freshness check, so
    a checkpoint from an earlier call verified a decision in which the CLI reported nothing."""
    decision = ClaudeCodeConductorBackend(_StaleReportingBackend()).propose_plan("obj", {}, 1)
    assert decision["model_verified"] is False
    assert decision["model"] != "claude-fable-5-20260101", (
        "a stale checkpoint must not be recorded as the executing model")


def test_propose_plan_refuses_a_non_vendor_backend_that_reports_a_fresh_checkpoint():
    duck = _DuckBackend()

    def _generate(prompt: str, *, max_tokens: int = 256) -> str:
        duck.calls += 1
        duck.reported_model_at_call = duck.calls          # perfectly fresh, wrong class
        return '{"proposed_tasks": [{"desc": "d", "capability": "reasoning"}]}'

    duck.generate = _generate  # type: ignore[method-assign]
    decision = ClaudeCodeConductorBackend(duck).propose_plan("obj", {}, 1)
    assert decision["model_verified"] is False


def test_propose_plan_on_the_mock_path_stays_unverified_and_records_the_selection_label():
    decision = ClaudeCodeConductorBackend(MockClaudeCliBackend(), model_name="fable-5").propose_plan(
        "obj", {}, 1)
    assert decision["model_verified"] is False
    assert decision["model"] == "fable-5"
    assert decision["model_selection"] == "fable-5"


def test_propose_plan_verifies_only_a_checkpoint_stamped_by_THIS_call():
    """The positive contract, at classifier level. The genuine class is required, so the backend is
    a real `ClaudeCliBackend` whose `generate` is replaced — nothing spawns (U43 applies)."""
    backend = ClaudeCliBackend(model="fable-5")
    backend.calls = 5

    def _generate(prompt: str, *, max_tokens: int = 256) -> str:
        backend.calls += 1
        backend.reported_model = "claude-fable-5-20260101"
        backend.reported_model_at_call = backend.calls
        return '{"proposed_tasks": [{"desc": "d", "capability": "reasoning"}]}'

    backend.generate = _generate  # type: ignore[method-assign]
    decision = ClaudeCodeConductorBackend(backend).propose_plan("obj", {}, 1)
    assert decision["model_verified"] is True
    assert decision["model"] == "claude-fable-5-20260101"


def test_the_verified_path_is_reachable_with_process_spawning_banned(monkeypatch):
    """Scoped to what this body actually establishes.

    An earlier name claimed a suite-wide property ("no test in this suite spawns a claude
    process") that a single function monkeypatching itself cannot establish — a name stronger than
    its body, which a reviewer flagged. The suite-wide property is true and is verified externally
    by the gate-validator running the whole suite under a `subprocess.Popen` hook; it is recorded
    in the evidence report, not asserted here.

    What THIS test establishes: the full verified path — classifier, leg, and `propose_plan` — runs
    to completion with both spawn entrypoints banned, so none of them reaches a process."""
    import subprocess

    def _banned(*args, **kwargs):  # pragma: no cover - the point is that it never runs
        raise AssertionError(f"a live process was spawned by a mock-first test: {args!r}")

    monkeypatch.setattr(subprocess, "Popen", _banned)
    monkeypatch.setattr(subprocess, "run", _banned)
    assert verify_reported_checkpoint(_genuine(at_call=2, calls=2), calls_before=1) is not None
    assert _leg_for_backend(ClaudeCliBackend()) == "live"
    assert ClaudeCodeConductorBackend(MockClaudeCliBackend()).propose_plan("o", {}, 1)[
        "model_verified"] is False


def test_mock_handle_record_matches_the_binding_shape():
    """Auditor MINOR-3. `live_succession._mock_handle` hand-builds a selection record instead of
    calling `bind_conductor_selection`, and it had already drifted: this unit added
    `reported_unverified`/`verified_by` to `as_record()` and the hand copy did not follow, so a
    consumer reading both shapes saw fields appear and vanish by code path. Pin the key sets."""
    from control_plane.orchestration.live_succession import mock_predecessor_handle

    class _Mcp:
        def call(self, op, **kw):
            raise AssertionError("no MCP call is made while building the handle")

    handle = mock_predecessor_handle(_Mcp(), {})
    reference = bind_conductor_selection().as_record()
    assert set(handle.selection_record) == set(reference)
    assert set(handle.selection_record["executing"]) == set(reference["executing"])


def test_the_publish_time_backstop_requires_verified_to_be_exactly_true(tmp_path):
    """Validator R1 / mutant S3. `_leg_for_backend`'s docstring names `_assert_legs_honest` as the
    evidence backstop for a `live` conductor leg — and that backstop was untested at the public
    `build_acceptance_packet` boundary, where `conductor_selection` is an arbitrary Mapping. A
    truthy-but-not-True `verified` (e.g. `1`) must not satisfy it."""
    from control_plane.orchestration.live_flow import AcceptancePacketError, build_acceptance_packet

    def _packet(selection):
        return build_acceptance_packet(
            objective="o", ts="2026-07-20T00:00:00+00:00", synthesized_by="conductor-1",
            conductor_selection=selection, decomposition={}, accepted=[],
            accepted_confirmed_in_mcp=0, gate_records=[], failed_tasks=[], queued_tasks=[],
            promotion_conflicts=[], node_refusals=[], task_states={},
            legs={"conductor": "live", "workers": "mock"})

    good = {"executing": {"verified": True, "model": "claude-fable-5-20260101"}}
    assert _packet(good)["legs"]["conductor"] == "live"

    for bad in ({"executing": {"verified": 1, "model": "claude-x"}},        # truthy, not True
                {"executing": {"verified": "yes", "model": "claude-x"}},
                {"executing": {"verified": True, "model": ""}},             # verified, no model
                {"executing": {"verified": True, "model": "   "}},
                {"executing": None},
                None):
        with pytest.raises(AcceptancePacketError):
            _packet(bad)


def test_the_adapter_reported_model_property_stays_fail_closed():
    """Validator R2 / mutant S4. `ConductorAdapter.reported_model` is now inert for verification
    (it only feeds `reported_unverified`), so nothing pinned its blank/non-string guard while its
    docstring still promised one. A selection LABEL must never be promoted into that slot."""
    from adapters.base.contract import AdapterContext
    from adapters.conductor.adapter import ConductorAdapter

    class _Backend:
        model_name = "fable-5"
        calls = 0

    ctx = AdapterContext(node_id="c1", role="conductor", project_id="p",
                         permission_profile_id="pp", mcp_credential_id="ref",
                         spawned_by_supervisor=True)
    backend = _Backend()
    adapter = ConductorAdapter(ctx, object(), backend)

    for bad in (None, "", "   ", True, 5, {"model": "x"}):
        backend.reported_model = bad  # type: ignore[attr-defined]
        assert adapter.reported_model is None, f"{bad!r} must not become a checkpoint"
    backend.reported_model = "  claude-fable-5-20260101  "  # type: ignore[attr-defined]
    assert adapter.reported_model == "  claude-fable-5-20260101  "
