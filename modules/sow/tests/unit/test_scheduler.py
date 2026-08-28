"""Phase 5: task graph + capability scheduling (pure/unit)."""
from __future__ import annotations

import pytest

from control_plane.tasks.graph import IllegalTaskTransition, TaskGraph, TaskState
from scheduler.capability_registry.registry import CapabilityRegistry
from scheduler.resolver.resolver import CapabilityResolver
from scheduler.scheduler import Scheduler


# ---------- task graph ----------

def _req(cap="reasoning"):
    return {"capability": cap, "requirements": {"structured_output": True, "min_context": 8000}}


def test_independent_task_is_ready_immediately() -> None:
    g = TaskGraph()
    g.add_task("t-1", _req())
    assert g.get("t-1").state is TaskState.READY


def test_dependent_task_waits_then_readies() -> None:
    g = TaskGraph()
    g.add_task("t-1", _req())
    g.add_task("t-2", _req(), deps=("t-1",))
    assert g.get("t-2").state is TaskState.PENDING
    g.assign("t-1", "n1", rationale="r"); g.transition("t-1", TaskState.IN_PROGRESS)
    g.transition("t-1", TaskState.AWAITING_GATE); g.transition("t-1", TaskState.GATED_PASS)
    g.transition("t-1", TaskState.DONE)
    assert g.get("t-2").state is TaskState.READY


def test_failed_dependency_blocks_dependent() -> None:
    """Invariant 16: a failed artifact cannot advance; dependents stay BLOCKED."""
    g = TaskGraph()
    g.add_task("t-1", _req())
    g.add_task("t-2", _req(), deps=("t-1",))
    g.assign("t-1", "n1", rationale="r"); g.transition("t-1", TaskState.IN_PROGRESS)
    g.transition("t-1", TaskState.AWAITING_GATE); g.transition("t-1", TaskState.GATED_FAIL)
    g.transition("t-1", TaskState.BLOCKED)
    assert g.get("t-2").state is TaskState.BLOCKED


def test_illegal_transition_refused() -> None:
    g = TaskGraph()
    g.add_task("t-1", _req())
    with pytest.raises(IllegalTaskTransition):
        g.transition("t-1", TaskState.DONE)  # cannot skip straight to DONE


def test_dependency_must_be_defined_first() -> None:
    g = TaskGraph()
    with pytest.raises(ValueError, match="not defined"):
        g.add_task("t-2", _req(), deps=("t-1",))


# ---------- scheduler ----------

def _registry_with(*nodes) -> CapabilityRegistry:
    reg = CapabilityRegistry()
    for nid, caps, kw in nodes:
        reg.register(nid, caps, **kw)
    return reg


REASONER_CAPS = [{"capability": "reasoning", "requirements": {"structured_output": True, "min_context": 32000}}]
CODER_CAPS = [{"capability": "coding", "requirements": {"tool_use": True, "min_context": 32000}}]


def test_resolver_picks_by_capability_not_name() -> None:
    # the INCAPABLE coder is registered FIRST: an order-based ("return first node") stub would
    # wrongly pick it and fail this test, so passing proves descriptor-based selection.
    reg = _registry_with(
        ("node-y", CODER_CAPS, dict(locality="local", cost_class="local", offline_profile_eligible=True)),
        ("node-x", REASONER_CAPS, dict(locality="local", cost_class="local", offline_profile_eligible=True)),
    )
    res = CapabilityResolver(reg).resolve(_req("reasoning"))
    assert res.resolved and res.node_id == "node-x"  # the reasoner, resolved by descriptor not order
    assert "node-x" in res.rationale and "reasoning" in res.rationale


def test_resolver_no_capable_node_queues_with_reason() -> None:
    reg = _registry_with(("node-y", CODER_CAPS, dict(locality="local", cost_class="local", offline_profile_eligible=True)))
    res = CapabilityResolver(reg).resolve(_req("reasoning"))
    assert not res.resolved and "no node meets" in res.rationale


def test_resolver_excludes_ineligible_under_airgapped() -> None:
    reg = _registry_with(
        ("frontier-1", REASONER_CAPS, dict(locality="frontier", cost_class="subscription", offline_profile_eligible=False)))
    res = CapabilityResolver(reg).resolve(_req("reasoning"), profile_airgapped=True)
    assert not res.resolved and "offline" in res.rationale


def test_scheduler_assigns_ready_tasks_over_graph() -> None:
    g = TaskGraph()
    g.add_task("t-1", _req("reasoning"))
    g.add_task("t-2", _req("reasoning"))
    reg = _registry_with(
        ("w-A", REASONER_CAPS, dict(locality="local", cost_class="local", offline_profile_eligible=True)),
        ("w-B", REASONER_CAPS, dict(locality="local", cost_class="local", offline_profile_eligible=True)),
    )
    assignments, queued = Scheduler(g, reg).schedule_ready()
    assert len(assignments) == 2 and not queued
    assert {a.node_id for a in assignments} <= {"w-A", "w-B"}
    assert all(g.get(a.task_id).state is TaskState.ASSIGNED for a in assignments)
