"""Phase 15D `.flow` — pure units: conductor decomposition -> task graph inputs, and the
acceptance packet the conductor synthesizes from the ACCEPTED set.

Both are DETERMINISTIC and FAIL CLOSED (Buildout §4). The decomposition never invents a task
and never defaults an unknown capability; the packet cannot be built claiming a live leg that
did not verifiably execute (directive §6 / §10.4 — a mock leg is never presented as live).
"""
from __future__ import annotations

import pytest

from control_plane.orchestration.live_flow import (
    ACCEPTANCE_PACKET_KEYS,
    ACCEPTANCE_PACKET_SCHEMA,
    ATTEMPTED_LEG,
    CAPABILITY_REQUIREMENTS,
    AcceptancePacketError,
    DecompositionError,
    build_acceptance_packet,
    decompose_plan,
)

TS = "2026-07-19T12:00:00+00:00"


def _plan(tasks, **extra):
    return {"model": "mock-reasoner-v1", "cycle": 1, "objective_ack": "obj",
            "proposed_tasks": tasks, "rationale": "r", **extra}


# --- decomposition -----------------------------------------------------------------

def test_proposed_tasks_become_deterministic_graph_inputs() -> None:
    d = decompose_plan(_plan([{"desc": "analyse the roster", "capability": "reasoning"},
                              {"desc": "review the result", "capability": "review"}]))

    assert [t.task_id for t in d.tasks] == ["t-1", "t-2"]
    assert [t.capability for t in d.tasks] == ["reasoning", "review"]
    assert d.tasks[0].description == "analyse the roster"
    # requirements come from the pinned capability table, not from model output
    assert d.tasks[0].capability_req == {"capability": "reasoning",
                                         "requirements": CAPABILITY_REQUIREMENTS["reasoning"]}
    assert d.usable and not d.refused
    # deterministic: same input, same ids
    assert [t.task_id for t in decompose_plan(_plan([{"desc": "analyse the roster", "capability": "reasoning"},
                                                     {"desc": "review the result", "capability": "review"}])).tasks] \
        == ["t-1", "t-2"]


def test_task_ids_number_only_accepted_tasks_no_gaps() -> None:
    d = decompose_plan(_plan([{"desc": "ok one", "capability": "reasoning"},
                              {"desc": "bad", "capability": "telepathy"},
                              {"desc": "ok two", "capability": "review"}]))
    assert [t.task_id for t in d.tasks] == ["t-1", "t-2"]
    assert [t.description for t in d.tasks] == ["ok one", "ok two"]
    assert len(d.refused) == 1 and d.refused[0]["index"] == 1


@pytest.mark.parametrize("bad, why", [
    ({"desc": "x", "capability": "telepathy"}, "unknown capability"),
    ({"desc": "x", "capability": ""}, "blank capability"),
    ({"desc": "x"}, "missing capability"),
    ({"capability": "reasoning"}, "missing description"),
    ({"desc": "   ", "capability": "reasoning"}, "blank description"),
    ({"desc": "x", "capability": ["reasoning"]}, "non-string capability"),
    ("not a mapping", "non-mapping element"),
    (None, "null element"),
])
def test_malformed_element_is_refused_never_defaulted(bad, why) -> None:
    """A capability is NEVER guessed or defaulted to 'reasoning' — an element that does not
    name a known capability with a real description is refused and RECORDED (never silent)."""
    d = decompose_plan(_plan([bad]))
    assert d.tasks == () and not d.usable, why
    assert len(d.refused) == 1
    assert d.refused[0]["index"] == 0 and d.refused[0]["reason"]


def test_unstructured_parse_mode_yields_no_tasks_even_if_tasks_present() -> None:
    """The live conductor backend fails closed to parse_mode='unstructured' when the CLI reply
    could not be parsed. A decomposition that could not be parsed decomposes NOTHING — tasks
    that arrived alongside an unparseable verdict are not trusted."""
    d = decompose_plan(_plan([{"desc": "x", "capability": "reasoning"}], parse_mode="unstructured"))
    assert d.tasks == () and not d.usable
    assert d.parse_mode == "unstructured"
    assert any("unstructured" in r["reason"] for r in d.refused)


def test_unknown_parse_mode_fails_closed() -> None:
    d = decompose_plan(_plan([{"desc": "x", "capability": "reasoning"}], parse_mode="creative"))
    assert d.tasks == () and not d.usable


def test_missing_or_malformed_proposed_tasks_is_empty_not_a_crash() -> None:
    for payload in ({"model": "m"}, {"proposed_tasks": None}, {"proposed_tasks": "t-1,t-2"},
                    {"proposed_tasks": {}}):
        d = decompose_plan(payload)
        assert d.tasks == () and not d.usable and d.refused


def test_non_mapping_decision_raises() -> None:
    for bad in (None, "plan", ["t"], 7):
        with pytest.raises(DecompositionError):
            decompose_plan(bad)


def test_decomposition_record_is_serialisable_and_counts_match() -> None:
    d = decompose_plan(_plan([{"desc": "a", "capability": "reasoning"},
                              {"desc": "b", "capability": "nope"}]))
    rec = d.as_record()
    assert rec["accepted_count"] == 1 and rec["refused_count"] == 1
    assert rec["tasks"][0]["task_id"] == "t-1"
    assert rec["refused"][0]["index"] == 1


# --- declared ordering (deps) ------------------------------------------------------

def test_declared_deps_reach_the_task_graph_as_task_ids() -> None:
    """The conductor's declared ORDERING is part of what it proposed. `deps` arrive as 1-based
    indices over the PROPOSED list and must be resolved to the assigned task ids — otherwise the
    plan gate's `plan_acyclic` criterion evaluates an empty dependency graph and the Scheduler
    starts dependent work in parallel with its own prerequisite."""
    d = decompose_plan(_plan([{"desc": "analyse", "capability": "reasoning"},
                              {"desc": "review the analysis", "capability": "review", "deps": [1]}]))
    assert [t.task_id for t in d.tasks] == ["t-1", "t-2"]
    assert d.tasks[0].deps == ()
    assert d.tasks[1].deps == ("t-1",)
    assert d.as_record()["tasks"][1]["deps"] == ["t-1"]


def test_deps_are_renumbered_to_assigned_ids_when_an_earlier_element_was_refused() -> None:
    """Task ids number only ACCEPTED tasks, so a proposed index is NOT the task number. A dep
    naming proposed element 1 must resolve to whatever id that element actually received."""
    d = decompose_plan(_plan([{"desc": "bad", "capability": "telepathy"},
                              {"desc": "analyse", "capability": "reasoning"},
                              {"desc": "review", "capability": "review", "deps": [2]}]))
    assert [t.task_id for t in d.tasks] == ["t-1", "t-2"]
    assert d.tasks[0].description == "analyse"
    assert d.tasks[1].deps == ("t-1",)          # proposed index 2 -> assigned id t-1


def test_dep_on_a_refused_element_refuses_the_dependent_task() -> None:
    """A prerequisite that never entered the graph cannot be satisfied. Running the dependent task
    anyway would execute work out of order, so it is refused and RECORDED (fail closed) — and the
    refusal cascades to anything depending on it in turn."""
    d = decompose_plan(_plan([{"desc": "bad", "capability": "telepathy"},
                              {"desc": "needs the bad one", "capability": "reasoning", "deps": [1]},
                              {"desc": "needs the dependent one", "capability": "review", "deps": [2]}]))
    assert d.tasks == () and not d.usable
    assert len(d.refused) == 3
    assert d.refused[1]["index"] == 1 and "refused" in d.refused[1]["reason"]
    assert d.refused[2]["index"] == 2            # cascaded, never silently kept


@pytest.mark.parametrize("deps, why", [
    ([2], "forward reference — dep names a LATER element"),
    ([1], "self reference"),
    ([0], "0 is not a 1-based index"),
    ([-1], "negative index"),
    ([99], "index past the end of the proposed list"),
    (["1"], "string index"),
    ([1.0], "float index"),
    ([True], "bool is an int subclass and must not pass as an index"),
    ("1", "deps is not a list"),
    ({"1": 2}, "deps is a mapping"),
])
def test_malformed_or_unsatisfiable_deps_are_refused_never_dropped(deps, why) -> None:
    """A dependency edge is never silently discarded: an element whose `deps` cannot be resolved
    is refused and recorded. Forward references are refused specifically because the task graph
    requires a dep to be defined before its dependent, which also makes a cycle structurally
    impossible from this path (`plan_acyclic` remains an independent check, not the sole guard)."""
    d = decompose_plan(_plan([{"desc": "first", "capability": "reasoning", "deps": deps},
                              {"desc": "second", "capability": "review"}]))
    assert all(t.deps == () for t in d.tasks), why
    assert any(r["index"] == 0 for r in d.refused), why
    assert not any(t.description == "first" for t in d.tasks), why


@pytest.mark.parametrize("deps, fragment", [
    ([99], "outside the proposed list"),
    ([0], "outside the proposed list"),
    ([-1], "outside the proposed list"),
    ([2], "strictly earlier"),
    ([1], "strictly earlier"),
    (["1"], "not an integer"),
    ("1", "must be a list"),
])
def test_the_recorded_refusal_reason_identifies_the_actual_fault(deps, fragment) -> None:
    """The reason is operator-facing evidence, so it must name the REAL fault. Asserting only that
    a refusal occurred lets distinct checks collapse into one another and report a wrong cause —
    e.g. an out-of-range index being reported as 'its prerequisite was refused'."""
    d = decompose_plan(_plan([{"desc": "first", "capability": "reasoning", "deps": deps},
                              {"desc": "second", "capability": "review"}]))
    reason = next(r["reason"] for r in d.refused if r["index"] == 0)
    assert fragment in reason, reason


def test_a_dep_on_a_refused_element_reports_that_specific_cause() -> None:
    d = decompose_plan(_plan([{"desc": "bad", "capability": "telepathy"},
                              {"desc": "depends on it", "capability": "reasoning", "deps": [1]}]))
    reason = next(r["reason"] for r in d.refused if r["index"] == 1)
    assert "itself refused" in reason, reason


def test_absent_deps_field_is_an_empty_dep_list_never_a_guessed_edge() -> None:
    d = decompose_plan(_plan([{"desc": "a", "capability": "reasoning"},
                              {"desc": "b", "capability": "review", "deps": []}]))
    assert [t.deps for t in d.tasks] == [(), ()]


def test_multiple_deps_are_all_resolved_and_order_preserved() -> None:
    d = decompose_plan(_plan([{"desc": "a", "capability": "reasoning"},
                              {"desc": "b", "capability": "coding"},
                              {"desc": "c", "capability": "review", "deps": [1, 2]}]))
    assert d.tasks[2].deps == ("t-1", "t-2")


def test_duplicate_dep_indices_are_deduplicated_deterministically() -> None:
    d = decompose_plan(_plan([{"desc": "a", "capability": "reasoning"},
                              {"desc": "b", "capability": "review", "deps": [1, 1]}]))
    assert d.tasks[1].deps == ("t-1",)


# --- acceptance packet -------------------------------------------------------------

def _packet(**over):
    base = dict(
        objective="Design the offline conductor roster",
        conductor_selection={"selection": {"model": "fable-5", "reason": "operator_selected"},
                             "executing": {"model": None, "verified": False},
                             "label_mismatch": False},
        decomposition=decompose_plan(_plan([{"desc": "a", "capability": "reasoning"}])).as_record(),
        accepted=[{"entry_id": "m-1", "task_id": "t-1", "content_hash": "sha256:aa"}],
        failed_tasks=[], queued_tasks=[], task_states={"t-1": "DONE"},
        gate_records=[{"gate_id": "g-1", "kind": "stage", "verdict": "PASS", "task_id": "t-1"}],
        legs={"conductor": "mock", "workers": "mock"},
        synthesized_by="conductor-fable5", ts=TS)
    base.update(over)
    return build_acceptance_packet(**base)


def test_packet_shape_is_pinned_and_counts_are_derived() -> None:
    p = _packet()
    assert set(p) == set(ACCEPTANCE_PACKET_KEYS)
    assert p["schema"] == ACCEPTANCE_PACKET_SCHEMA
    assert p["accepted_count"] == 1                      # derived from `accepted`, not passed in
    assert p["accepted"][0]["entry_id"] == "m-1"
    assert p["conductor_selection"]["selection"]["model"] == "fable-5"
    assert p["gate_records"][0]["verdict"] == "PASS"


def test_packet_refuses_to_claim_a_live_leg_the_conductor_did_not_verifiably_execute() -> None:
    """The load-bearing honesty rule (directive §6/§10.4): declaring a LIVE conductor leg
    requires a VERIFIED executing checkpoint reported by the CLI itself. A mock run (executing
    model None / unverified) can never be packaged as live."""
    with pytest.raises(AcceptancePacketError):
        _packet(legs={"conductor": "live", "workers": "mock"})

    # the same packet is fine once the executing checkpoint is verified
    p = _packet(legs={"conductor": "live", "workers": "mock"},
                conductor_selection={"selection": {"model": "fable-5", "reason": "operator_selected"},
                                     "executing": {"model": "claude-fable-5-20260101", "verified": True},
                                     "label_mismatch": True})
    assert p["legs"]["conductor"] == "live"
    assert p["conductor_selection"]["executing"]["verified"] is True


def test_packet_refuses_a_live_leg_that_carries_no_verification_record() -> None:
    """Only the conductor leg has a verification record (a VERIFIED executing checkpoint). Any
    other leg declaring `live` is an UNBACKED claim and must be unrepresentable, not merely
    unchecked — otherwise `workers: live` sails through with no evidence at all."""
    with pytest.raises(AcceptancePacketError):
        _packet(legs={"conductor": "mock", "workers": "live"})
    with pytest.raises(AcceptancePacketError):
        _packet(legs={"conductor": "mock", "workers": "mock", "coder": "live"})

    # ...even alongside a genuinely verified conductor checkpoint
    with pytest.raises(AcceptancePacketError):
        _packet(legs={"conductor": "live", "workers": "live"},
                conductor_selection={"selection": {"model": "fable-5", "reason": "operator_selected"},
                                     "executing": {"model": "claude-fable-5-20260101", "verified": True},
                                     "label_mismatch": True})


def test_packet_reconciliation_count_is_carried_and_defaults_to_zero() -> None:
    assert _packet()["accepted_confirmed_in_mcp"] == 0
    assert _packet(accepted_confirmed_in_mcp=1)["accepted_confirmed_in_mcp"] == 1


@pytest.mark.parametrize("bad", [2, 99, -1])
def test_packet_refuses_a_reconciliation_count_that_exceeds_the_set_it_reconciles(bad) -> None:
    """The count reconciles the accepted set against MCP; it cannot exceed it or go negative.
    A reconciliation number larger than the set it reconciles is worse than no number."""
    with pytest.raises(AcceptancePacketError):
        _packet(accepted_confirmed_in_mcp=bad)


def test_an_attempted_conductor_leg_is_representable_and_needs_no_checkpoint() -> None:
    """A real call that returned no verifiable checkpoint must still be recordable: refusing to
    build the packet would discard the whole governed run over an unprovable label. `attempted`
    says exactly what happened — spent, but not verified."""
    p = _packet(legs={"conductor": ATTEMPTED_LEG, "workers": "mock"})
    assert p["legs"]["conductor"] == ATTEMPTED_LEG
    assert p["conductor_selection"]["executing"]["verified"] is False


def test_only_the_conductor_leg_may_be_attempted() -> None:
    with pytest.raises(AcceptancePacketError):
        _packet(legs={"conductor": "mock", "workers": ATTEMPTED_LEG})


def test_packet_records_that_the_operator_has_not_accepted_it() -> None:
    """Invariant 1: the gate engine may promote this packet in MCP, but that is not operator
    acceptance and an ACCEPTED packet must never be readable as an operator decision."""
    assert _packet()["operator_disposition"] == "pending"


def test_packet_refuses_an_unknown_leg_value() -> None:
    with pytest.raises(AcceptancePacketError):
        _packet(legs={"conductor": "probably-live", "workers": "mock"})
    with pytest.raises(AcceptancePacketError):
        _packet(legs={"workers": "mock"})               # conductor leg must be declared


def test_packet_refuses_malformed_inputs() -> None:
    with pytest.raises(AcceptancePacketError):
        _packet(objective="   ")
    with pytest.raises(AcceptancePacketError):
        _packet(ts="")
    with pytest.raises(AcceptancePacketError):
        _packet(accepted=[{"task_id": "t-1"}])          # an accepted item must name its entry
    with pytest.raises(AcceptancePacketError):
        _packet(accepted="m-1")


def test_packet_is_deterministic_for_identical_inputs() -> None:
    assert _packet() == _packet()
