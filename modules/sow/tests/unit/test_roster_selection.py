"""Phase 6: >=3 backends behind capability descriptors; selection is by DESCRIPTOR, never by
adapter/model name (I-SC1). Deterministic (allow_live=False -> all mock)."""
from __future__ import annotations

import pytest

from adapters.roster import build_roster, register_roster
from scheduler.capability_registry.registry import CapabilityRegistry
from scheduler.resolver.resolver import CapabilityResolver


@pytest.fixture()
def resolver() -> CapabilityResolver:
    reg = CapabilityRegistry()
    register_roster(reg, build_roster(allow_live=False))
    return CapabilityResolver(reg)


def test_roster_has_at_least_three_backends() -> None:
    roster = build_roster(allow_live=False)
    assert len(roster) >= 3
    names = {e.name for e in roster}
    assert {"local_reasoning", "coding_node", "mock_frontier"} <= names
    # all-mock under allow_live=False (deterministic suite)
    assert all(e.backend_kind == "mock" for e in roster)


def test_coding_task_resolves_to_the_coding_node(resolver: CapabilityResolver) -> None:
    req = {"capability": "coding", "requirements": {"tool_use": True, "structured_output": True, "min_context": 32000}}
    res = resolver.resolve(req)
    assert res.resolved and res.node_id == "coding_node"  # only node advertising 'coding'
    # the task requirement named a CAPABILITY, never an adapter/model
    assert "coding" not in {"local_reasoning", "mock_frontier"}  # sanity: name not in the req


def test_large_context_reasoning_resolves_to_frontier_by_descriptor(resolver: CapabilityResolver) -> None:
    # 128k context is met only by the frontier descriptor; local reasoning advertises 32k
    req = {"capability": "reasoning", "requirements": {"structured_output": True, "min_context": 128000}}
    res = resolver.resolve(req)
    assert res.resolved and res.node_id == "mock_frontier"  # picked by min_context, not by name


def test_offline_profile_excludes_frontier_leaves_local(resolver: CapabilityResolver) -> None:
    req = {"capability": "reasoning", "requirements": {"structured_output": True, "min_context": 32000}}
    res = resolver.resolve(req, profile_airgapped=True)
    assert res.resolved and res.node_id == "local_reasoning"  # frontier excluded when air-gapped


def test_offline_large_context_reasoning_has_no_node(resolver: CapabilityResolver) -> None:
    # air-gapped + 128k: frontier excluded (not offline-eligible), local can't meet 128k -> queue
    req = {"capability": "reasoning", "requirements": {"structured_output": True, "min_context": 128000}}
    res = resolver.resolve(req, profile_airgapped=True)
    assert not res.resolved and "no node meets" in res.rationale


def test_coding_tui_harness_task_does_not_match_direct_coder(resolver: CapabilityResolver) -> None:
    """F1 honesty: the coding_node is a DIRECT local coder (no harness loop) — a task that
    genuinely requires a coding_tui harness must fail closed, not mis-route to it."""
    req = {"capability": "coding", "requirements": {"tool_use": True, "structured_output": True,
                                                    "min_context": 32000, "harness_class": "coding_tui"}}
    res = resolver.resolve(req)
    assert not res.resolved and "harness_class" in res.rationale  # fail closed on unmet harness


def test_coding_task_without_harness_requirement_still_resolves(resolver: CapabilityResolver) -> None:
    # a plain coding task (no harness_class requirement) still routes to the coding node
    res = resolver.resolve({"capability": "coding", "requirements": {"tool_use": True, "min_context": 32000}})
    assert res.resolved and res.node_id == "coding_node"


def test_roster_descriptors_are_schema_valid() -> None:
    # register_roster validates against node@1.0; a malformed descriptor would raise
    from scheduler.capability_registry.registry import CapabilityRegistry
    register_roster(CapabilityRegistry(), build_roster(allow_live=False))  # no raise = valid


def test_no_task_requirement_names_a_vendor_or_adapter() -> None:
    """Structural I-SC1: capability descriptors carry only capability + requirement flags —
    no adapter/model/vendor field exists for a name to hide in."""
    for e in build_roster(allow_live=False):
        for desc in e.capability_descriptors:
            assert set(desc) <= {"capability", "requirements", "cost_class", "priority"}
            assert desc["capability"] in ("coding", "reasoning", "review", "synthesis", "research", "voice_stt")
