"""W-60 — the operational record family is unschematized: written down, not left implied.

`schemas/README.md` opened with "Single source of truth for EVERY governed object" — and the
operational record family (the operational tasks/messages/debates `mcp_server/collaboration_service.py`
writes through `persistence/store.py`) pins NO schema at all (U414; Phase 19 unit 5's residue table
named it: "the operational record family pins no schema at all"). The universal sentence and the
schemaless family coexisted; this unit writes the boundary down where the universal sentence lives.

Why the retraction path and not validation, decided mechanically rather than by taste:

  * The frozen twelve schemas describe OTHER record families. `debate@1.0` requires
    `debate_id` + `request` (caller_node/topic/participants-as-capability-descriptors/max_rounds/
    budget) and an outcome enum CONVERGED/DISSENT_PRESERVED/BUDGET_EXHAUSTED/CUT_OFF. The
    operational debate record carries `state` OPEN/CLOSED/ABORTED, `turns`, `participant_node_ids`,
    `proposition` — not one frozen key survives contact. `test_the_frozen_debate_schema_cannot_describe_an_operational_debate`
    pins that mismatch BEHAVIOURALLY, so a reconciliation is a visible act, not a silent drift.
  * Authoring a schema for the operational family would touch the Phase-0 freeze envelope: a new
    `schemas/*.schema.json` is picked up by the manifest's frozen glob, moves
    `freeze_integrity_sha256`, and resets the operator's signature to PENDING. Successor schemas
    are operator-ruled (the OP-12.1 pattern; schemas/README.md's own amendment discipline). Not a
    worker's to self-authorize.

What governs the family instead (recorded in the README boundary, pinned here): the service's
hand-written shape checks, TASK_STATES/MESSAGE_KINDS validated against on every write, the fenced
transition legality (`_assert_legal_transition`), and the tool-layer inputSchema. The README edit
is the retraction; these tests keep it from silently rotting.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
README = ROOT / "schemas" / "README.md"


# ---- negative: the defect -----------------------------------------------------------------------

def test_the_readme_states_the_operational_family_is_unschematized() -> None:
    """NEGATIVE. Pre-repair the README claimed to be the single source of truth for EVERY governed
    object and said nothing about the one governed family no schema describes. Repaired, the
    boundary is written where the universal sentence lives."""
    text = README.read_text(encoding="utf-8")
    lowered = text.lower()
    assert "operational record family" in lowered, (
        "schemas/README.md must name the operational record family explicitly")
    assert "collaboration_service" in text, (
        "the boundary must say WHO writes the unschematized family")
    assert "no schema" in lowered or "unschematized" in lowered, (
        "the boundary must state the family is unschematized, not imply it")
    opening = text.split("\n\n")[1].lower()          # the paragraph after the title
    assert "every governed object" not in opening, (
        "the OPENING claim must be rescoped — it was the sentence that diverged from the tree; "
        "the boundary section may quote it as history")


# ---- positive: the mechanical facts the retraction rests on --------------------------------------

def test_the_frozen_debate_schema_cannot_describe_an_operational_debate(tmp_path: Path) -> None:
    """POSITIVE / CONTROL (passed pre-repair as well — INHERITED fact, now pinned). The frozen
    `debate@1.0` and the operational debate record share no vocabulary: this is why 'validate the
    operational family against the frozen schemas' is not an available path without a
    successor-schema ruling, and why a future reconciliation must be a visible act."""
    from control_plane.policy import Identity, SovereignPolicy
    from mcp_server.collaboration_service import CollaborationService
    from persistence import SovereignStore

    schema = json.loads((ROOT / "schemas" / "debate.schema.json").read_text(encoding="utf-8"))
    frozen_outcomes = set(schema["properties"]["result"]["properties"]["outcome"]["enum"])
    frozen_required = set(schema["required"])

    store = SovereignStore(tmp_path / "sovereign.db")
    try:
        service = CollaborationService(store, SovereignPolicy())
        cond = Identity("cond-1", "conductor", "proj")
        w1 = Identity("worker-1", "worker", "proj")
        w2 = Identity("worker-2", "worker", "proj")
        task = service.create_task(cond, objective="w60 scope probe",
                                   owner_node_ids=[w1.node_id, w2.node_id])
        debate = service.open_debate(
            cond, task_id=task["task_id"], proposition="scope",
            participant_node_ids=[w1.node_id, w2.node_id], max_rounds=1)
        service.post_debate_turn(w1, debate_id=debate["debate_id"], body="a")
        service.post_debate_turn(w2, debate_id=debate["debate_id"], body="b")
        closed = service.close_debate(cond, debate_id=debate["debate_id"], decision="d")
        second = service.open_debate(
            cond, task_id=task["task_id"], proposition="scope again",
            participant_node_ids=[w1.node_id, w2.node_id], max_rounds=1)
        aborted = service.abort_debate(cond, debate_id=second["debate_id"], reason="probe")
    finally:
        store.close()

    operational_states = {closed["state"], aborted["state"], "OPEN"}
    assert operational_states == {"OPEN", "CLOSED", "ABORTED"}
    assert operational_states.isdisjoint(frozen_outcomes), (
        f"an operational state entered the frozen outcome enum — the families are no longer "
        f"disjoint and the retraction must be revisited: {operational_states & frozen_outcomes}")
    missing = frozen_required - closed.keys()
    assert missing, (
        "an operational debate record now satisfies ALL the frozen required keys — the families "
        "have converged; reconcile deliberately, under a successor-schema ruling")


def test_the_freeze_envelope_still_covers_exactly_the_schema_files() -> None:
    """POSITIVE / CONTROL (passed pre-repair — INHERITED). The frozen set is the `*.schema.json`
    glob; README.md is NOT frozen, which is what lets this unit edit it at all. If the envelope
    ever grows to cover the README, this unit's repair path changes and the pin must be argued."""
    import re as _re
    manifest_src = (ROOT / "tools" / "manifest" / "compute_manifest.py").read_text(encoding="utf-8")
    match = _re.search(r'"schemas":\s*\("schemas",\s*"([^"]+)"\)', manifest_src)
    assert match, "the manifest must still declare a schemas frozen set"
    assert match.group(1) == "*.schema.json", (
        f"the frozen schemas glob drifted: {match.group(1)!r}")
    assert not (README.name.endswith(".schema.json")), "README.md must stay outside the glob"
