"""U330/U416/U332 — one write path, an abort path, and a gate that cannot be skipped.

The cold audit's M2 (2026-08-06): the store's `mutate_operational_task` opens a
`BEGIN IMMEDIATE` boundary that read/modify/write on a shared record needs, and **five of the
seven orchestration writers did not use it** — `create_task`, `update_task`, `open_debate`,
`post_debate_turn`, `close_debate` all read a record into Python, built a successor from that
snapshot, and blind-wrote it back through an `ON CONFLICT DO UPDATE` that overwrites whatever
landed in between. Two nodes posting a turn to one debate is the ordinary case, not the exotic
one, and the loser's turn vanished with no conflict record — the silent last-write-wins
invariant 13 forbids.

Three properties are tested here, and the third one is why the first two are not enough:

  1. **the fence exists** (§1) — the store's create/mutate entry points, and the absence of the
     blind ones. Structural: it says the bypass is not merely unused but unreachable.
  2. **the successor is computed INSIDE the fence** (§2) — a competing writer commits between
     the service's read and its write, and its work survives. This is the property that
     actually fails on the shipped-before code, and it fails for `{**snapshot, ...}` even if
     that snapshot is written through a transactional method: routing the *call* through the
     fence while still building the record from a stale read looks identical in a diff and
     loses the same turn.
  3. **the rules the fence now guards are re-asked inside it** (§2 also) — the round limit, the
     close quorum and the update authority were all evaluated against the snapshot.

§3 is U416 (a debate whose participant can no longer answer had no terminal state but CLOSED,
which needs a turn from everyone — so it stayed OPEN forever) and §4 is U332 (an empty
`debate_ids` walked past the closed-debate gate, because the gate was a loop over the caller's
own list).

The genuinely concurrent falsification — two OS processes, not two threads — is
`tests/integration/test_operational_concurrent_processes.py`. It is the load-bearing one; these
are the fast, deterministic pins that say *which* property broke.
"""
from __future__ import annotations

import json
import pathlib
from typing import Any, Callable

import pytest

from control_plane.policy import Identity, SovereignPolicy
from mcp_server.collaboration_service import CollaborationError, CollaborationService
from mcp_server.sovereign_tools import TOOLS, SovereignToolRuntime, ToolError
from persistence import SovereignStore, StoreError
from tools.live.emit_operational_state import build_feed

COND = Identity("cond-1", "conductor", "proj")
W1 = Identity("worker-1", "worker", "proj")
W2 = Identity("worker-2", "worker", "proj")


@pytest.fixture()
def store(tmp_path: pathlib.Path):
    s = SovereignStore(tmp_path / "sovereign.db")
    yield s
    s.close()


@pytest.fixture()
def service(store: SovereignStore) -> CollaborationService:
    return CollaborationService(store, SovereignPolicy())


def _task(service: CollaborationService, **kw: Any) -> dict[str, Any]:
    return service.create_task(COND, objective="rank the integration risks",
                               owner_node_ids=[W1.node_id, W2.node_id], **kw)


def _debate(service: CollaborationService, task: dict[str, Any], **kw: Any) -> dict[str, Any]:
    return service.open_debate(COND, task_id=task["task_id"], proposition="risk A outranks risk B",
                               participant_node_ids=[W1.node_id, W2.node_id], **kw)


def _candidate(node_id: str, task_id: str) -> dict[str, Any]:
    return {"task_id": task_id, "worker_node_id": node_id, "provider": "p", "model": "m",
            "summary": "ranked risks", "claims": ["risk one"], "evidence_refs": ["file.py:1"],
            "peer_messages_considered": [], "debates_considered": [], "limitations": [],
            "status": "CANDIDATE", "artifact_ref": "sha256:c", "content_hash": "sha256:c"}


# ---------------------------------------------------------------------------
# 1. the fence exists, and the blind writers are gone
# ---------------------------------------------------------------------------

class TestTheStoreOffersOnlyTheFencedWritePath:
    def test_the_blind_write_methods_no_longer_exist(self, store: SovereignStore) -> None:
        """`put_operational_task`/`put_operational_debate` were the bypass. Deleting them is the
        structural half of the fix: a future writer cannot reach the unfenced path by habit.
        (Structural only — §2 is what proves the surviving path is used correctly.)"""
        assert not hasattr(store, "put_operational_task")
        assert not hasattr(store, "put_operational_debate")

    def test_creating_a_task_twice_is_refused_rather_than_overwriting(self, store: SovereignStore) -> None:
        """The `ON CONFLICT DO UPDATE` the create path used would have silently replaced an
        existing task — including its candidates — with a fresh empty one."""
        task = {"task_id": "t-1", "project_id": "proj", "thread_id": "th-1", "objective": "o",
                "status": "ASSIGNED", "owner_node_ids": [W1.node_id]}
        store.create_operational_task(task)
        with pytest.raises(StoreError, match="already exists"):
            store.create_operational_task({**task, "objective": "clobbered"})
        assert store.get_operational_task("proj", "t-1")["objective"] == "o"

    def test_creating_a_debate_twice_is_refused_rather_than_overwriting(self, store: SovereignStore) -> None:
        debate = {"debate_id": "d-1", "project_id": "proj", "task_id": "t-1", "thread_id": "th-1",
                  "state": "OPEN", "turns": []}
        store.create_operational_debate(debate)
        with pytest.raises(StoreError, match="already exists"):
            store.create_operational_debate({**debate, "state": "CLOSED"})
        assert store.get_operational_debate("proj", "d-1")["state"] == "OPEN"

    def test_creating_a_task_over_an_existing_id_is_refused_at_the_service(
            self, service: CollaborationService) -> None:
        """The store's refusal has to REACH the caller. A create path that swallowed it would
        return a task record the store never wrote — the conductor would then assign work against
        an id whose durable content is someone else's task."""
        task = _task(service)
        with pytest.raises(StoreError, match="already exists"):
            service.create_task(COND, objective="a different objective",
                                owner_node_ids=[W1.node_id], task_id=task["task_id"])
        assert service.get_task(COND, task["task_id"])["objective"] == "rank the integration risks"

    def test_mutating_an_absent_debate_is_refused(self, store: SovereignStore) -> None:
        with pytest.raises(StoreError, match="no such operational debate"):
            store.mutate_operational_debate("proj", "d-missing", lambda current: current)

    def test_a_mutation_may_not_change_the_debate_identity(self, store: SovereignStore) -> None:
        store.create_operational_debate({"debate_id": "d-2", "project_id": "proj", "task_id": "t-1",
                                         "thread_id": "th-1", "state": "OPEN", "turns": []})
        with pytest.raises(StoreError, match="changed debate identity"):
            store.mutate_operational_debate(
                "proj", "d-2", lambda current: {**current, "debate_id": "d-elsewhere"})
        assert store.get_operational_debate("proj", "d-2")["debate_id"] == "d-2"

    def test_a_mutation_may_not_move_a_debate_to_another_task(self, store: SovereignStore) -> None:
        """`task_id` is the scope every debate read is filtered by, so a mutation that changes it
        would move a debate out of the task whose synthesis gate counts it (§4)."""
        store.create_operational_debate({"debate_id": "d-3", "project_id": "proj", "task_id": "t-1",
                                         "thread_id": "th-1", "state": "OPEN", "turns": []})
        with pytest.raises(StoreError, match="changed debate identity"):
            store.mutate_operational_debate(
                "proj", "d-3", lambda current: {**current, "task_id": "t-other"})


# ---------------------------------------------------------------------------
# 2. the successor is computed inside the fence — a competing commit survives
# ---------------------------------------------------------------------------

class _InterposingStore(SovereignStore):
    """Commits a competing writer's work in the window between the service's read and its own
    transactional write — the window a second OS process occupies for real.

    The competitor runs on its OWN `SovereignStore` over the same file (a separate connection,
    committed before the fence opens), so this is not a Python-level illusion: after it returns,
    the durable record genuinely differs from the snapshot the service read.
    """

    def __init__(self, db_path: pathlib.Path) -> None:
        super().__init__(db_path)
        self._competitor: Callable[[], None] | None = None

    def arm(self, competitor: Callable[[], None]) -> None:
        self._competitor = competitor

    def _fire(self) -> None:
        competitor, self._competitor = self._competitor, None
        if competitor is not None:
            competitor()

    def mutate_operational_task(self, project_id: str, task_id: str, mutator: Any) -> dict[str, Any]:
        self._fire()
        return super().mutate_operational_task(project_id, task_id, mutator)

    def mutate_operational_debate(self, project_id: str, debate_id: str, mutator: Any) -> dict[str, Any]:
        self._fire()
        return super().mutate_operational_debate(project_id, debate_id, mutator)


@pytest.fixture()
def racing(tmp_path: pathlib.Path):
    """The service under test, plus a factory for an independent peer on the same database."""
    db = tmp_path / "sovereign.db"
    interposing = _InterposingStore(db)
    peers: list[SovereignStore] = []

    def peer() -> CollaborationService:
        s = SovereignStore(db)
        peers.append(s)
        return CollaborationService(s, SovereignPolicy())

    yield CollaborationService(interposing, SovereignPolicy()), interposing, peer
    for s in peers:
        s.close()
    interposing.close()


class TestAConcurrentCommitIsNotOverwritten:
    def test_a_candidate_landing_after_the_tool_read_cannot_be_dropped_from_synthesis(
            self, racing) -> None:
        """U430's exact race: the tool snapshot saw W1 only; W2 commits before the synthesis
        transaction. The in-fence check must refuse rather than complete a task omitting W2."""
        service, interposing, peer = racing
        task = _task(service)
        service.record_candidate(W1, task_id=task["task_id"],
                                 candidate=_candidate(W1.node_id, task["task_id"]))
        stale_synthesis = {
            "status": "SYNTHESIS",
            "contributions": [{"node_id": W1.node_id,
                               "candidate_content_hash": "sha256:c",
                               "contribution": "w1 said"}],
            "candidate_node_ids": [W1.node_id],
        }
        other = peer()
        interposing.arm(lambda: other.record_candidate(
            W2, task_id=task["task_id"], candidate=_candidate(W2.node_id, task["task_id"])))
        with pytest.raises(CollaborationError, match=f"write fence; missing: {W2.node_id}"):
            service.record_synthesis(COND, task_id=task["task_id"], synthesis=stale_synthesis,
                                     contribution_bindings=stale_synthesis["contributions"])
        committed = service.get_task(COND, task["task_id"])
        assert committed["status"] == "CANDIDATE_READY"
        assert sorted(committed["candidates"]) == [W1.node_id, W2.node_id]

    def test_a_debate_turn_that_lands_first_is_not_lost(self, racing) -> None:
        """The ordinary two-worker case. `post_debate_turn` read the debate, appended to the
        snapshot's turn list, and wrote the whole record back: whoever committed second erased
        the other's turn, with no conflict record and no error to either node."""
        service, interposing, peer = racing
        task = _task(service)
        debate = _debate(service, task, max_rounds=3)
        other = peer()
        interposing.arm(lambda: other.post_debate_turn(W2, debate_id=debate["debate_id"], body="peer"))
        service.post_debate_turn(W1, debate_id=debate["debate_id"], body="mine")
        turns = service.get_debate(COND, debate["debate_id"])["turns"]
        assert [t["body"] for t in turns] == ["peer", "mine"]

    def test_the_round_limit_is_evaluated_against_the_committed_record(self, racing) -> None:
        """The limit was read off the snapshot, so a node's own last turn could be admitted twice
        under contention. Inside the fence the count is the durable one."""
        service, interposing, peer = racing
        task = _task(service)
        debate = _debate(service, task, max_rounds=1)
        other = peer()
        interposing.arm(lambda: other.post_debate_turn(W1, debate_id=debate["debate_id"], body="first"))
        with pytest.raises(CollaborationError, match="bounded debate round limit reached"):
            service.post_debate_turn(W1, debate_id=debate["debate_id"], body="second")
        assert len(service.get_debate(COND, debate["debate_id"])["turns"]) == 1

    def test_a_candidate_published_first_survives_a_status_update(self, racing) -> None:
        """`update_task` wrote `{**snapshot, status}` — the exact shape that erases a candidate
        `record_candidate` had already committed through the fence. The two writers this unit is
        named for are a worker publishing and the conductor advancing lifecycle."""
        service, interposing, peer = racing
        task = _task(service)
        other = peer()
        interposing.arm(lambda: other.record_candidate(
            W1, task_id=task["task_id"], candidate=_candidate(W1.node_id, task["task_id"])))
        updated = service.update_task(COND, task_id=task["task_id"], status="UNDER_REVIEW")
        assert updated["status"] == "UNDER_REVIEW"
        assert W1.node_id in (updated.get("candidates") or {})
        assert W1.node_id in (service.get_task(COND, task["task_id"]).get("candidates") or {})

    def test_a_peer_candidate_published_first_is_not_overwritten(self, racing) -> None:
        """`record_candidate` was ALREADY inside the fence before this unit — and graded by
        nothing (gate-validator MAJOR-1, round 1: the defect could be spliced back into it and the
        whole suite stayed green). It is the first property the unit's charter names, so it is
        pinned here deterministically as well as in the two-process test."""
        service, interposing, peer = racing
        task = _task(service)
        other = peer()
        interposing.arm(lambda: other.record_candidate(
            W2, task_id=task["task_id"], candidate=_candidate(W2.node_id, task["task_id"])))
        updated = service.record_candidate(
            W1, task_id=task["task_id"], candidate=_candidate(W1.node_id, task["task_id"]))
        assert sorted(updated["candidates"]) == [W1.node_id, W2.node_id]
        # and the completeness status is derived from BOTH, not from the writer's own view
        assert updated["status"] == "CANDIDATE_READY"

    def test_a_turn_that_lands_during_closure_is_carried_into_the_record(self, racing) -> None:
        """A closing debate is the worst case for a stale snapshot: the closed record's `claims`
        and `turn_evidence_refs` ARE the debate's evidence, so a turn lost here is lost from the
        acceptance packet the synthesis rests on."""
        service, interposing, peer = racing
        task = _task(service)
        debate = _debate(service, task, max_rounds=2)
        service.post_debate_turn(W1, debate_id=debate["debate_id"], body="one")
        other = peer()
        interposing.arm(lambda: other.post_debate_turn(
            W2, debate_id=debate["debate_id"], body="two", evidence_refs=["late.py:9"]))
        closed = service.close_debate(COND, debate_id=debate["debate_id"], decision="A outranks B")
        assert closed["claims"] == ["one", "two"]
        assert closed["turn_evidence_refs"] == ["late.py:9"]

    def test_a_second_abort_that_races_the_first_is_refused(self, racing) -> None:
        """Two conductors — or one conductor and the operator — noticing the same dead pane. The
        first abort's reason is the durable one; the second is refused rather than overwriting it.
        The refusal comes from INSIDE the fence: the pre-transaction state check that reads the
        same way cannot see a commit that has not happened yet."""
        service, interposing, peer = racing
        task = _task(service)
        debate = _debate(service, task, max_rounds=2)
        other = peer()
        interposing.arm(lambda: other.abort_debate(
            COND, debate_id=debate["debate_id"], reason="peer noticed first"))
        with pytest.raises(CollaborationError, match="debate is not open"):
            service.abort_debate(COND, debate_id=debate["debate_id"], reason="second abort")
        assert service.get_debate(COND, debate["debate_id"])["abort_reason"] == "peer noticed first"

    def test_the_close_quorum_is_evaluated_against_the_committed_record(self, racing) -> None:
        """The mirror of the previous test: the quorum rule must not be satisfiable by a snapshot
        that a concurrent commit has already invalidated. Here the peer ABORTS mid-close."""
        service, interposing, peer = racing
        task = _task(service)
        debate = _debate(service, task, max_rounds=2)
        service.post_debate_turn(W1, debate_id=debate["debate_id"], body="one")
        service.post_debate_turn(W2, debate_id=debate["debate_id"], body="two")
        other = peer()
        interposing.arm(lambda: other.abort_debate(
            COND, debate_id=debate["debate_id"], reason="peer pane died"))
        with pytest.raises(CollaborationError, match="debate is not open"):
            service.close_debate(COND, debate_id=debate["debate_id"], decision="too late")
        assert service.get_debate(COND, debate["debate_id"])["state"] == "ABORTED"


# ---------------------------------------------------------------------------
# 3. U416 — a debate whose participant can no longer answer has a terminal state
# ---------------------------------------------------------------------------

class TestADebateCanBeAbortedWhenAParticipantCannotAnswer:
    def test_a_debate_missing_a_participants_turn_can_never_be_closed(self, service) -> None:
        """The state U416 describes, asserted rather than argued: this is what the surviving peer
        and its stall timer are stuck behind, and why an abort path is needed at all."""
        task = _task(service)
        debate = _debate(service, task, max_rounds=2)
        service.post_debate_turn(W1, debate_id=debate["debate_id"], body="one")
        with pytest.raises(CollaborationError, match="without a turn from every participant"):
            service.close_debate(COND, debate_id=debate["debate_id"], decision="d")

    def test_abort_gives_it_a_terminal_state_that_preserves_what_was_said(self, service) -> None:
        task = _task(service)
        debate = _debate(service, task, max_rounds=2)
        service.post_debate_turn(W1, debate_id=debate["debate_id"], body="one")
        aborted = service.abort_debate(COND, debate_id=debate["debate_id"],
                                       reason="worker-2 pane exited")
        assert aborted["state"] == "ABORTED"
        assert aborted["abort_reason"] == "worker-2 pane exited"
        assert aborted["aborted_by_node_id"] == COND.node_id and aborted["aborted_at"]
        assert [t["body"] for t in aborted["turns"]] == ["one"]
        assert aborted["decision"] is None, "an aborted debate reached no decision"

    def test_an_aborted_debate_accepts_no_further_turns_and_cannot_be_closed(self, service) -> None:
        task = _task(service)
        debate = _debate(service, task, max_rounds=2)
        service.post_debate_turn(W1, debate_id=debate["debate_id"], body="one")
        service.abort_debate(COND, debate_id=debate["debate_id"], reason="pane exited")
        with pytest.raises(CollaborationError, match="debate is not open"):
            service.post_debate_turn(W2, debate_id=debate["debate_id"], body="late")
        with pytest.raises(CollaborationError, match="debate is not open"):
            service.close_debate(COND, debate_id=debate["debate_id"], decision="d")
        with pytest.raises(CollaborationError, match="debate is not open"):
            service.abort_debate(COND, debate_id=debate["debate_id"], reason="again")

    def test_a_worker_participant_may_not_abort_the_debate_it_is_arguing(self, service) -> None:
        """Ending a deliberation without a conclusion is a governance act, so abort is the
        conductor/operator pair exactly as closure is, and the rule lives in
        `control_plane/policy.py` like every other one. Note what this pins and what it does NOT:
        the refused identity here is a WORKER, and the rule refuses it by ROLE — see the next
        test for the case the role rule admits."""
        task = _task(service)
        debate = _debate(service, task, max_rounds=2)
        with pytest.raises(CollaborationError, match="only conductor/operator may abort a debate"):
            service.abort_debate(W1, debate_id=debate["debate_id"], reason="I would rather not")
        assert service.get_debate(COND, debate["debate_id"])["state"] == "OPEN"

    def test_the_conductor_may_abort_a_debate_it_is_arguing_in(self, service) -> None:
        """The honest converse, pinned rather than left to a docstring (19.5 spec-auditor
        MAJOR-1). `authorize_debate_abort` restricts by role, so a DIRECTING node that is also a
        participant is admitted — and the conductor usually is one, because a task's participant
        set includes its creator. That is **U350**'s open question (recorded there for
        `close_debate`, whose shape this rule copies), not a protection this build provides.
        A rule that refused every participant would restore the stall U416 exists to end: the
        conductor's own debate with a dead worker would be permanent again. The test asserts the
        behaviour AS IT IS, so U350's eventual answer turns it red instead of passing quietly."""
        task = _task(service)
        debate = service.open_debate(
            COND, task_id=task["task_id"], proposition="my own proposition",
            participant_node_ids=[COND.node_id, W1.node_id], max_rounds=2)
        assert COND.node_id in debate["participant_node_ids"]
        service.post_debate_turn(W1, debate_id=debate["debate_id"], body="I disagree")
        aborted = service.abort_debate(
            COND, debate_id=debate["debate_id"], reason="I do not like where this went")
        assert aborted["state"] == "ABORTED" and aborted["decision"] is None
        # what stops this being a gate override is downstream, not here: the turn survives and
        # the synthesis gate will not count an aborted debate as a considered one (§4)
        assert [t["body"] for t in aborted["turns"]] == ["I disagree"]

    def test_an_abort_must_say_why(self, service) -> None:
        task = _task(service)
        debate = _debate(service, task, max_rounds=2)
        with pytest.raises(CollaborationError, match="abort reason must be non-empty"):
            service.abort_debate(COND, debate_id=debate["debate_id"], reason="  ")


# ---------------------------------------------------------------------------
# 4. U332 — the closed-debate gate is not the caller's own list
# ---------------------------------------------------------------------------

class _FakeApp:
    def __init__(self, identity: Identity) -> None:
        self._details = {"node_id": identity.node_id, "role": identity.role,
                         "project_id": identity.project_id, "provider_id": "p", "model_id": "m"}

    def identity_details(self) -> dict[str, Any]:
        return dict(self._details)

    def call(self, operation: str, arguments: dict[str, Any] | None = None) -> Any:
        return {"delivered": operation}


def _synthesis_args(task_id: str, debate_ids: list[str],
                    contributions: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """A complete argument set, so a refusal under test is the gate and not shape validation.

    19.6 ([[U333]]): the two vendor-named fields this used to carry (`gemini_contribution`,
    `grok_contribution`) are gone. The default names the two workers `_ready_for_synthesis`
    publishes candidates for, because the rule is now "every candidate node is accounted for".
    """
    return {"task_id": task_id,
            "contributions": [{"node_id": W1.node_id, "contribution": "w1 said"},
                              {"node_id": W2.node_id, "contribution": "w2 said"}]
            if contributions is None else contributions,
            "points_of_agreement": ["a"], "points_of_disagreement": [], "debate_outcome": "o",
            "evidence_used": ["e"], "limitations": [], "conductor_judgment": "j",
            "recommended_next_action": "n", "debate_ids": debate_ids}


@pytest.fixture()
def conductor_runtime(tmp_path: pathlib.Path):
    runtime = SovereignToolRuntime(_FakeApp(COND), tmp_path, policy=SovereignPolicy())
    yield runtime
    runtime.close()


def _closed_debate(service: CollaborationService, task: dict[str, Any],
                   proposition: str = "risk A outranks risk B") -> dict[str, Any]:
    debate = service.open_debate(COND, task_id=task["task_id"], proposition=proposition,
                                 participant_node_ids=[W1.node_id, W2.node_id], max_rounds=2)
    service.post_debate_turn(W1, debate_id=debate["debate_id"], body="one")
    service.post_debate_turn(W2, debate_id=debate["debate_id"], body="two")
    return service.close_debate(COND, debate_id=debate["debate_id"], decision="A outranks B")


def _ready_for_synthesis(service: CollaborationService, task: dict[str, Any]) -> dict[str, Any]:
    """Both workers' candidates published, so a test about the DEBATE gate is not stopped one
    rule later by the completeness rule."""
    for worker in (W1, W2):
        service.record_candidate(worker, task_id=task["task_id"],
                                 candidate=_candidate(worker.node_id, task["task_id"]))
    return service.get_task(COND, task["task_id"])


class TestTheSynthesisDebateGateCannotBeSkipped:
    def test_an_empty_debate_id_list_no_longer_walks_past_the_gate(self, conductor_runtime) -> None:
        """U332 exactly: the gate was `for debate_id in debate_ids`, so the empty list satisfied
        it vacuously and a conductor could publish a synthesis while claiming to have considered
        the debate it never mentioned. `_nonempty_strings` is the refusal that arrives first, as
        the directive specifies; the next test covers the cross-check behind it, which is what
        makes naming a SUBSET no better than naming none."""
        service = conductor_runtime.collaboration
        task = _task(service)
        _closed_debate(service, task)
        _ready_for_synthesis(service, task)
        with pytest.raises(ToolError, match="debate_ids must not be empty"):
            conductor_runtime.call("publish_synthesis", _synthesis_args(task["task_id"], []))

    def test_omitting_one_closed_debate_is_refused_and_the_refusal_names_it(
            self, conductor_runtime) -> None:
        """A caller told only "no" cannot act on it (invariant 27): the refusal names the debate
        that was left out."""
        service = conductor_runtime.collaboration
        task = _task(service)
        named = _closed_debate(service, task, "first proposition")
        omitted = _closed_debate(service, task, "second proposition")
        _ready_for_synthesis(service, task)
        with pytest.raises(ToolError, match=f"must name every closed debate.*{omitted['debate_id']}"):
            conductor_runtime.call(
                "publish_synthesis", _synthesis_args(task["task_id"], [named["debate_id"]]))

    def test_an_open_debate_blocks_the_synthesis_even_when_unnamed(self, conductor_runtime) -> None:
        """Omission was the bypass, so the gate is computed from the TASK's debates, not from the
        caller's list: a debate still being argued blocks the acceptance packet that would
        summarise it."""
        service = conductor_runtime.collaboration
        task = _task(service)
        _debate(service, task, max_rounds=2)
        with pytest.raises(ToolError, match="still open"):
            conductor_runtime.call("publish_synthesis", _synthesis_args(task["task_id"], []))

    def test_a_closed_debate_from_another_task_does_not_satisfy_the_gate(self, conductor_runtime) -> None:
        """`get_debate` is project-scoped, not task-scoped, so before the cross-check any closed
        debate anywhere in the project satisfied a named id."""
        service = conductor_runtime.collaboration
        other_task = _task(service)
        borrowed = _closed_debate(service, other_task)
        task = _task(service)
        with pytest.raises(ToolError, match="does not belong to this task"):
            conductor_runtime.call(
                "publish_synthesis", _synthesis_args(task["task_id"], [borrowed["debate_id"]]))

    def test_a_task_whose_debates_are_all_closed_and_named_is_published(self, conductor_runtime) -> None:
        service = conductor_runtime.collaboration
        task = _task(service)
        closed = _closed_debate(service, task)
        _ready_for_synthesis(service, task)
        result = conductor_runtime.call(
            "publish_synthesis", _synthesis_args(task["task_id"], [closed["debate_id"]]))
        assert result["synthesis"]["debate_ids"] == [closed["debate_id"]]
        assert result["synthesis"]["aborted_debate_ids"] == []
        assert result["task"]["status"] == "COMPLETED"

    def test_a_task_with_no_debates_may_still_be_synthesised(self, conductor_runtime) -> None:
        """The honest limit of `_nonempty_strings` on its own: a task that never needed a debate
        must not become unsynthesisable. Nothing is skipped here because nothing exists to skip —
        the cross-check, not the list's length, is what makes the empty case safe."""
        service = conductor_runtime.collaboration
        task = _task(service)
        _ready_for_synthesis(service, task)
        result = conductor_runtime.call("publish_synthesis", _synthesis_args(task["task_id"], []))
        assert result["synthesis"]["debate_ids"] == []

    def test_an_aborted_debate_is_disclosed_and_never_counted_as_considered(
            self, conductor_runtime) -> None:
        """U416 meets U332: an aborted debate must neither block the task forever nor be
        presentable as a deliberation that concluded. It is refused as a considered debate and
        recorded, from the store rather than from the caller, as an aborted one."""
        service = conductor_runtime.collaboration
        task = _task(service)
        debate = _debate(service, task, max_rounds=2)
        service.post_debate_turn(W1, debate_id=debate["debate_id"], body="one")
        service.abort_debate(COND, debate_id=debate["debate_id"], reason="worker-2 pane exited")
        _ready_for_synthesis(service, task)
        with pytest.raises(ToolError, match="every considered debate to be closed"):
            conductor_runtime.call(
                "publish_synthesis", _synthesis_args(task["task_id"], [debate["debate_id"]]))
        result = conductor_runtime.call("publish_synthesis", _synthesis_args(task["task_id"], []))
        assert result["synthesis"]["aborted_debate_ids"] == [debate["debate_id"]]
        assert result["synthesis"]["debate_ids"] == []

    def test_the_abort_path_is_reachable_as_a_tool(self, conductor_runtime) -> None:
        """A rule a live node cannot invoke is not a path. The pane that dies belongs to a node,
        and the conductor that notices is the caller."""
        service = conductor_runtime.collaboration
        task = _task(service)
        debate = _debate(service, task, max_rounds=2)
        aborted = conductor_runtime.call(
            "abort_debate", {"debate_id": debate["debate_id"], "reason": "worker-2 pane exited"})
        assert aborted["state"] == "ABORTED"

    def test_the_operational_feed_counts_an_aborted_debate_as_its_own_thing(
            self, tmp_path: pathlib.Path) -> None:
        """The Inspector's feed. `open_debate_count` alone would let an aborted debate read as a
        concluded one by subtraction, which is the same untruth in arithmetic form (invariant 27).
        The feed is a CLI emitter, not shell code — the Inspector's own rendering of the new state
        is ungraded until the in-runtime self-check that owns it exists (U412)."""
        store = SovereignStore(tmp_path / "sovereign.db")
        try:
            service = CollaborationService(store, SovereignPolicy())
            task = _task(service)
            _closed_debate(service, task, "concluded")
            aborted = _debate(service, task, max_rounds=2)
            service.abort_debate(COND, debate_id=aborted["debate_id"], reason="pane exited")
            _debate(service, task, max_rounds=2)
        finally:
            store.close()
        feed = build_feed(project_id="proj", store_root=tmp_path)
        assert feed["summary"]["debate_count"] == 3
        assert feed["summary"]["open_debate_count"] == 1
        assert feed["summary"]["aborted_debate_count"] == 1

    def test_the_catalog_advertises_the_abort_tool_with_its_reason(self) -> None:
        """A tool a node cannot discover is not reachable either: the catalog is how a live CLI
        learns the path exists, and `reason` is required so an abort is never unexplained."""
        entry = next(t for t in TOOLS if t["name"] == "abort_debate")
        assert sorted(entry["inputSchema"]["required"]) == ["debate_id", "reason"]


class TestSynthesisIsKeyedByNodeNotByVendor:
    """§5 — U333: the synthesis record was structurally bound to two vendors.

    The cold audit's M4 (2026-08-06): `_publish_synthesis` built the record with hardcoded
    `gemini_contribution` and `grok_contribution` fields, both in the `required_text` tuple whose
    absence raises, and both `required` in the published tool schema. A task completed by any other
    pair — two Codex workers, a Claude worker and a local Ollama worker, one worker, three — could
    not be synthesised at all, and the conductor's only way to comply was to file a node's work
    under another vendor's name. I-SC1: work is dispatched by capability descriptor and reported by
    node identity, never by model name.

    The replacement is not merely a rename. `contributions` is cross-checked against the task's own
    candidate set in BOTH directions, which is the same shape as the debate gate one section up: a
    contribution for a node that published no candidate is refused, and a candidate node left
    unmentioned is refused. The old two-field form could express neither check — with exactly two
    slots, a third worker's result had nowhere to go and a missing second worker was invisible.
    """

    def test_the_vendor_fields_are_gone_from_the_published_schema(self) -> None:
        entry = next(t for t in TOOLS if t["name"] == "publish_synthesis")
        schema = entry["inputSchema"]
        assert "gemini_contribution" not in schema["properties"]
        assert "grok_contribution" not in schema["properties"]
        assert "contributions" in schema["properties"]
        assert "contributions" in schema["required"]
        item = schema["properties"]["contributions"]["items"]
        assert sorted(item["required"]) == ["contribution", "node_id"]
        # The description a live CLI reads must not teach the vendor shape back.
        assert "gemini" not in entry["description"].lower()
        assert "grok" not in entry["description"].lower()

    def test_a_two_worker_task_publishes_contributions_keyed_by_node_id(
            self, conductor_runtime) -> None:
        service = conductor_runtime.collaboration
        task = _ready_for_synthesis(service, _task(service))
        result = conductor_runtime.call("publish_synthesis", _synthesis_args(task["task_id"], []))
        synthesis = result["synthesis"]
        assert synthesis["contributions"] == [
            {"node_id": W1.node_id, "candidate_content_hash": "sha256:c",
             "contribution": "w1 said"},
            {"node_id": W2.node_id, "candidate_content_hash": "sha256:c",
             "contribution": "w2 said"},
        ]
        assert "gemini_contribution" not in synthesis
        assert "grok_contribution" not in synthesis
        assert synthesis["candidate_node_ids"] == [W1.node_id, W2.node_id]

    def test_a_contribution_naming_a_node_that_published_nothing_is_refused(
            self, conductor_runtime) -> None:
        service = conductor_runtime.collaboration
        task = _ready_for_synthesis(service, _task(service))
        args = _synthesis_args(task["task_id"], [], contributions=[
            {"node_id": W1.node_id, "contribution": "w1 said"},
            {"node_id": W2.node_id, "contribution": "w2 said"},
            {"node_id": "worker-9", "contribution": "invented"},
        ])
        with pytest.raises(ToolError) as exc:
            conductor_runtime.call("publish_synthesis", args)
        assert "worker-9" in str(exc.value)

    def test_a_candidate_node_left_unmentioned_is_refused_and_the_refusal_names_it(
            self, conductor_runtime) -> None:
        """The direction the two-slot form could not fail in: a worker whose candidate exists but
        whose contribution is silently dropped from the synthesis."""
        service = conductor_runtime.collaboration
        task = _ready_for_synthesis(service, _task(service))
        args = _synthesis_args(task["task_id"], [], contributions=[
            {"node_id": W1.node_id, "contribution": "w1 said"}])
        with pytest.raises(ToolError) as exc:
            conductor_runtime.call("publish_synthesis", args)
        assert W2.node_id in str(exc.value)

    def test_each_contribution_is_bound_to_the_candidate_content_hash(
            self, conductor_runtime) -> None:
        service = conductor_runtime.collaboration
        task = _ready_for_synthesis(service, _task(service))
        stale = {
            "status": "SYNTHESIS",
            "contributions": [
                {"node_id": W1.node_id, "candidate_content_hash": "sha256:stale",
                 "contribution": "w1 said"},
                {"node_id": W2.node_id, "candidate_content_hash": "sha256:c",
                 "contribution": "w2 said"},
            ],
        }
        with pytest.raises(CollaborationError, match=f"content_hash: {W1.node_id}"):
            service.record_synthesis(COND, task_id=task["task_id"], synthesis=stale,
                                     contribution_bindings=stale["contributions"])

    def test_an_empty_or_malformed_contribution_set_is_refused(self, conductor_runtime) -> None:
        service = conductor_runtime.collaboration
        task = _ready_for_synthesis(service, _task(service))
        malformed: list[Any] = [
            [],
            "w1 said",
            [{"node_id": W1.node_id}],
            [{"node_id": W1.node_id, "contribution": "   "},
             {"node_id": W2.node_id, "contribution": "w2"}],
            [{"node_id": "", "contribution": "x"}],
            [{"node_id": W1.node_id, "contribution": "a"},
             {"node_id": W1.node_id, "contribution": "b"}],
        ]
        for bad in malformed:
            with pytest.raises(ToolError):
                conductor_runtime.call(
                    "publish_synthesis", _synthesis_args(task["task_id"], [], contributions=bad))

    def test_the_empty_list_and_duplicate_guards_are_load_bearing_on_their_own(
            self, conductor_runtime) -> None:
        """The round-1 gate-validator (MINOR-1) spliced out the `not raw` guard and the duplicate
        guard and this file stayed GREEN: every case above that exercised them was ALSO refused by
        the missing-candidate rule, so two guards were graded by nothing.

        The two cases that isolate them: a task with candidates from both workers whose
        contributions name one worker TWICE and the other once — complete by count, so `missing` is
        empty and only the duplicate rule can refuse it — and the same task with an empty list,
        which must be refused with the LIST's own message rather than by enumeration.
        """
        service = conductor_runtime.collaboration
        task = _ready_for_synthesis(service, _task(service))
        with pytest.raises(ToolError, match="named twice"):
            conductor_runtime.call("publish_synthesis", _synthesis_args(
                task["task_id"], [], contributions=[
                    {"node_id": W1.node_id, "contribution": "a"},
                    {"node_id": W1.node_id, "contribution": "b"},
                    {"node_id": W2.node_id, "contribution": "c"}]))
        # Driven at the SERVICE, not through `runtime.call`, since W-33. The published schema
        # carries `minItems: 1` and is now enforced before dispatch, so the MCP path refuses an
        # empty list with the SCHEMA's message and the service's own guard is never reached through
        # it. Defence in depth — but this test's claim is that the service guard is load-bearing ON
        # ITS OWN, and a claim about that guard has to be made where the guard is. The sibling test
        # below covers the schema half. Asserting the schema message here instead would have
        # silently converted this into a second test of the outer layer, leaving the inner one
        # unproven while still looking green.
        with pytest.raises(ToolError, match="contributions list"):
            conductor_runtime._contributions(task, [])

    def test_the_published_schema_refuses_an_empty_list_too(self) -> None:
        """The runtime refuses it; a CLI that validates only against the published schema was not
        told (gate-validator MINOR-4). `minItems` says the same thing where the conductor reads."""
        entry = next(t for t in TOOLS if t["name"] == "publish_synthesis")
        assert entry["inputSchema"]["properties"]["contributions"]["minItems"] == 1

    def test_a_task_worked_by_a_single_node_is_synthesisable(self, conductor_runtime) -> None:
        """Under the two-field rule this was impossible: one worker could not fill two required
        vendor slots without inventing the other."""
        service = conductor_runtime.collaboration
        task = service.create_task(COND, objective="rank the integration risks",
                                   owner_node_ids=[W1.node_id])
        service.record_candidate(W1, task_id=task["task_id"],
                                 candidate=_candidate(W1.node_id, task["task_id"]))
        task = service.get_task(COND, task["task_id"])
        result = conductor_runtime.call("publish_synthesis", _synthesis_args(
            task["task_id"], [], contributions=[{"node_id": W1.node_id, "contribution": "only"}]))
        assert result["synthesis"]["contributions"] == [
            {"node_id": W1.node_id, "candidate_content_hash": "sha256:c",
             "contribution": "only"}]

    def test_a_genuinely_dissenting_outcome_does_not_require_invented_agreement(
            self, conductor_runtime) -> None:
        service = conductor_runtime.collaboration
        task = _ready_for_synthesis(service, _task(service))
        args = _synthesis_args(task["task_id"], [])
        args["points_of_agreement"] = []
        args["points_of_disagreement"] = ["the workers rank the risk differently"]
        result = conductor_runtime.call("publish_synthesis", args)
        assert result["synthesis"]["points_of_agreement"] == []
        assert result["synthesis"]["points_of_disagreement"]

    def test_the_synthesis_artifact_carries_the_node_keyed_record(self, conductor_runtime) -> None:
        """The artifact is what the acceptance packet and the Inspector read; a record keyed by
        node only in the returned dict would still publish the vendor shape to everything that
        reads the CAS."""
        service = conductor_runtime.collaboration
        task = _ready_for_synthesis(service, _task(service))
        result = conductor_runtime.call("publish_synthesis", _synthesis_args(task["task_id"], []))
        stored = conductor_runtime.call(
            "read_artifact", {"artifact_id": result["synthesis"]["artifact_ref"]})
        body = json.dumps(stored)
        assert "gemini_contribution" not in body
        assert "grok_contribution" not in body
        assert W1.node_id in body and W2.node_id in body


# ---- W-78d: the Inspector feed must not issue one message query PER TASK ----

def test_build_feed_does_not_scale_message_queries_with_task_count(store, tmp_path, monkeypatch):
    """W-78d. build_feed used to call list_operational_messages once PER TASK - each call opening
    its own SQLite connection - so a project with T tasks paid T+1 queries for its feed. The
    property: fetching the messages of a whole project does not scale a per-task query with the
    task count."""
    import tools.live.emit_operational_state as feed_mod

    for i in range(6):
        store.create_operational_task({
            "task_id": f"t-{i}", "project_id": "proj", "thread_id": "th-feed", "objective": "o",
            "status": "CREATED", "owner_node_ids": [], "candidates": [], "synthesis": None,
        })

    calls = []
    real = type(store).list_operational_messages

    def _counting(self, project_id, task_id):
        calls.append(task_id)
        return real(self, project_id, task_id)

    monkeypatch.setattr(type(store), "list_operational_messages", _counting)
    feed = feed_mod.build_feed(project_id="proj", store_root=tmp_path)
    assert len(feed["tasks"]) == 6
    assert len(calls) <= 1, (
        f"build_feed issued {len(calls)} per-task message queries for 6 tasks - "
        "the N+1 the punch list named")


def test_build_feed_message_order_is_stable_across_tasks_with_tied_timestamps(store, tmp_path):
    """Control for the W-78d repair: collapsing the queries may not reorder the feed. Messages
    come back grouped by task in the TASKS' own order, ties broken by insertion rowid - the exact
    ordering the per-task loop produced."""
    import tools.live.emit_operational_state as feed_mod

    for i in range(3):
        store.create_operational_task({
            "task_id": f"tk-{i}", "project_id": "proj", "thread_id": "th-feed", "objective": "o",
            "status": "CREATED", "owner_node_ids": [], "candidates": [], "synthesis": None,
        })
        for j in range(2):
            store.append_operational_message({
                "message_id": f"m-{i}-{j}", "project_id": "proj", "task_id": f"tk-{i}",
                "sender_node_id": "w", "recipient_node_ids": ["c"], "thread_id": "th-feed",
                "message_kind": "progress", "body": f"{i}-{j}",
            })

    feed = feed_mod.build_feed(project_id="proj", store_root=tmp_path)
    bodies = [m["body"] for m in feed["messages"]]
    assert bodies == ["0-0", "0-1", "1-0", "1-1", "2-0", "2-1"], bodies
