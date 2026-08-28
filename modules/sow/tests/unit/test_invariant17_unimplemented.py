"""W-61 — invariant 17 is NOT implemented on the collaboration debate path: recorded, not silent.

U349, carried since Phase 19 unit 19.2's widening: `open_debate` on the collaboration path
range-checks `budget_units` and writes it into the debate record — and NO code in the repo reads
it back. There is no CostGovernor on this path, unlike `debate_service/service.py:74-84`, which
opens and closes against a global cap, a per-caller quota, and a per-debate budget. The cost is
real: `open_debate` reaches `apps/desktop/main.js controlNotifyDebate`, which writes a prompt into
every participant's pane and arms a turn deadline for each, so a project-wide caller can compel
turns uncapped. "A stored budget field that no code consults reads as governance to the next
reader, which is the part that must not stay silent" (U349).

W-61's disposition was "wire CostGovernor into the MCP debate path OR record invariant 17
unimplemented" (R10 watchlist). The recording path is taken, decided mechanically: wiring needs
self-authored governance — cap/quota values, a COST MODEL for asynchronous multi-session turns
(the governor's donor counts synchronous rounds at round_cost; collaboration turns span hours and
nothing measures them), exhaustion semantics, and it would preempt U349's explicit operator
alternative (revoke the gate role's debate authority instead). None of that is dictated by the
tree, the donor construct, or a recorded ruling, so choosing values would be self-authorization.
The silence, which IS inside the worker's authority to break, is broken here.

The behavioural pin below is the honesty anchor: a debate opened with budget_units=1 accepts turn
after turn with nothing refused. If a cost governor is ever wired in, that test fails and forces
the prose to be revisited deliberately — the same drift-trap pattern as W-60's schema-scope pin.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SERVICE = ROOT / "mcp_server" / "collaboration_service.py"
TOOLS = ROOT / "mcp_server" / "sovereign_tools.py"


# ---- negative: the defect -----------------------------------------------------------------------

def test_the_service_states_the_stored_budget_is_not_enforced() -> None:
    """NEGATIVE. Pre-repair the service wrote budget_units into every debate record, never read
    it back, and the module docstring called that a "budget range" — governance by implication,
    the exact silence U349 said must not stay silent. The marker phrase is the one AT THE WRITE
    (the open_debate range-check note), so deleting the note — not just the docstring sentence —
    is what the mutation row restores."""
    src = SERVICE.read_text(encoding="utf-8")
    lowered = src.lower()
    assert "written at the write" in lowered, (
        "the open_debate note must state the absence AT THE WRITE, where the field is stored")
    assert "U349" in src, (
        "the note must name U349 so the next reader reaches the full residue")
    assert "costgovernor" in lowered or "cost governor" in lowered, (
        "the note must say WHAT is absent on this path")


def test_the_open_debate_tool_description_does_not_advertise_governance_it_lacks() -> None:
    """NEGATIVE. The conductor sees budget_units in the tool schema; the description is where the
    expectation is set. Pre-repair it said nothing about enforcement."""
    src = TOOLS.read_text(encoding="utf-8")
    line = next(l for l in src.splitlines() if '"name": "open_debate"' in l)
    assert "not enforced" in line.lower(), (
        "the open_debate tool description must state the budget is recorded but not enforced")


# ---- positive: the behavioural facts the recording rests on -------------------------------------

def test_the_stored_budget_governs_nothing_behaviourally(tmp_path: Path) -> None:
    """POSITIVE / CONTROL (passed pre-repair as well — INHERITED, now pinned). A debate opened
    with budget_units=1 accepts turns with nothing refused: proof the field is storage, not
    governance. If a cost governor is ever wired into this path, this test fails FIRST and the
    W-61 prose must be revisited deliberately."""
    from control_plane.policy import Identity, SovereignPolicy
    from mcp_server.collaboration_service import CollaborationService
    from persistence import SovereignStore

    store = SovereignStore(tmp_path / "sovereign.db")
    try:
        service = CollaborationService(store, SovereignPolicy())
        cond = Identity("cond-1", "conductor", "proj")
        w1 = Identity("worker-1", "worker", "proj")
        w2 = Identity("worker-2", "worker", "proj")
        task = service.create_task(cond, objective="w61 probe",
                                   owner_node_ids=[w1.node_id, w2.node_id])
        debate = service.open_debate(
            cond, task_id=task["task_id"], proposition="p",
            participant_node_ids=[w1.node_id, w2.node_id], max_rounds=5, budget_units=1)
        assert debate["budget_units"] == 1
        for i in range(4):                              # four turns on a budget of ONE unit
            service.post_debate_turn(w1 if i % 2 == 0 else w2,
                                     debate_id=debate["debate_id"], body=f"turn {i}")
        row = service.get_debate(cond, debate_id=debate["debate_id"])
        assert len(row["turns"]) == 4, "nothing on this path refused on budget"
    finally:
        store.close()


def test_the_donor_cost_governor_still_enforces_on_its_own_path() -> None:
    """POSITIVE / CONTROL (passed pre-repair — INHERITED, re-pinned here so both halves of the
    asymmetry are visible in one place). The Phase-7 Debate Service's governor fails CLOSED once
    a caller's quota is spent — the governance that is ABSENT on the collaboration path."""
    from debate_service.cost_governor.governor import CostGovernor, DebateRefused

    g = CostGovernor(per_caller_quota=100, global_concurrent_cap=4)
    g.open_debate("d-1", "caller", budget_units=100)     # reserves the full budget at open
    assert g.charge("d-1", 100)                          # spends it all
    assert g.close_debate("d-1") == 100                  # commits it against the quota
    try:
        g.open_debate("d-2", "caller", budget_units=1)   # quota exhausted -> fail closed
        refused = False
    except DebateRefused:
        refused = True
    assert refused, "the donor governor must still refuse what this path never asks"
