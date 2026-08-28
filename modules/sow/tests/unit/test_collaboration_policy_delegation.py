"""U326 — the collaboration path must ask `control_plane/policy.py`, and only it.

Invariant 7: *MCP is access, not authority — no authorization logic inside `mcp_server/`.*
`mcp_server/memory_service.py` has always honoured that; `mcp_server/collaboration_service.py`
took a `SovereignPolicy` in its constructor, never read it, and made FIFTEEN role/permission
decisions inline instead (cold audit finding B1, 2026-08-06, which named twelve of them).

Four kinds of test live here, and all four are needed. A rule test alone cannot tell a
delegated rule from a duplicated one — the assertions pass either way. So:

  * **the rule tests** (§3) go through `CollaborationService` and pin each decision's behaviour.
    They are the mutation targets: a mutation to a rule in `control_plane/policy.py` must turn
    one of them RED, which is what proves the delegation is LIVE rather than decorative;
  * **the injected-policy tests** (§2) require the service to follow a policy that disagrees
    with the shipped one — in the PERMISSIVE direction, which is the only assertion a second
    copy of a rule inside `mcp_server/` cannot survive. There is one per entry point, because
    the first version of this file had one in total and the reviewer's answer to "could these
    tests pass against a duplicated rule set?" was "yes, for eleven of the twelve";
  * **the direct-policy tests** (§5) cover the clauses that are DEFENCE IN DEPTH — unreachable
    from the collaboration path because the store scopes its reads by project before the policy
    is asked. Labelling them honestly matters: a mutation row graded by one of these has not
    been proven through the collaboration path, and the harness says so at the row;
  * **the verdict matrix** (§7, U352) pins the WHOLE surface — every admitted role × every
    operation — as one table, because four consecutive review rounds each found a different
    membership set or scope clause that the one-off rule tests did not pin, always in the
    widening direction. A table cannot be widened one constant at a time without a cell moving.
"""
from __future__ import annotations

import ast
import io
import pathlib
import sys
from typing import Any

if __name__ == "__main__":      # the golden-table regeneration aid below needs the repo importable
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import pytest

from control_plane.policy import ROLES, Identity, SovereignPolicy, Verdict
from mcp_server.collaboration_service import CollaborationError, CollaborationService
from mcp_server.sovereign_tools import SovereignToolRuntime, ToolError
from persistence import SovereignStore

ROOT = pathlib.Path(__file__).resolve().parents[2]
SERVICE_SOURCE = ROOT / "mcp_server" / "collaboration_service.py"
TOOLS_SOURCE = ROOT / "mcp_server" / "sovereign_tools.py"


def _source(path: pathlib.Path) -> str:
    return io.open(path, encoding="utf-8").read()


@pytest.fixture()
def store(tmp_path: pathlib.Path):
    s = SovereignStore(tmp_path / "sovereign.db")
    yield s
    s.close()


@pytest.fixture()
def service(store: SovereignStore) -> CollaborationService:
    return CollaborationService(store, SovereignPolicy())


COND = Identity("cond-1", "conductor", "proj")
W1 = Identity("worker-1", "worker", "proj")
W2 = Identity("worker-2", "worker", "proj")
STRANGER = Identity("worker-out", "worker", "proj")
VOICE = Identity("voice-1", "voice", "proj")
GATE = Identity("gate-1", "gate", "proj")
MALFORMED = Identity("who-1", "hacker", "proj")


def _task(service: CollaborationService) -> dict[str, Any]:
    return service.create_task(
        COND, objective="rank the integration risks",
        owner_node_ids=[W1.node_id, W2.node_id],
        acceptance_criteria=["one candidate per worker"],
    )


def _debate(service: CollaborationService, task: dict[str, Any], **kw) -> dict[str, Any]:
    return service.open_debate(
        COND, task_id=task["task_id"], proposition="risk A outranks risk B",
        participant_node_ids=[W1.node_id, W2.node_id], **kw)


def _synthesis_args(task_id: str) -> dict[str, Any]:
    """A COMPLETE publish_synthesis argument set, so a test that removes the authority gate does
    not stop on shape validation instead.

    19.6 ([[U333]]): contributions are keyed by node id and cross-checked against the task's
    candidates, so "complete" now means the candidate set too — a caller that reaches the shape
    check must have seeded candidates for exactly these nodes.
    """
    return {"task_id": task_id,
            "contributions": [{"node_id": W1.node_id, "contribution": "w1"},
                              {"node_id": W2.node_id, "contribution": "w2"}],
            "points_of_agreement": ["a"], "points_of_disagreement": [], "debate_outcome": "o",
            "evidence_used": ["e"], "limitations": [], "conductor_judgment": "j",
            "recommended_next_action": "n", "debate_ids": []}


def _candidate(node_id: str, ref: str = "sha256:c") -> dict[str, Any]:
    return {
        "task_id": "set by caller", "worker_node_id": node_id, "provider": "p", "model": "m",
        "summary": "ranked risks", "claims": ["risk one"], "evidence_refs": ["file.py:1"],
        "peer_messages_considered": [], "debates_considered": [], "limitations": [],
        "status": "CANDIDATE", "artifact_ref": ref, "content_hash": ref,
    }


# ---------------------------------------------------------------------------
# 1. the structural half of invariant 7: no role decides anything in this package
# ---------------------------------------------------------------------------

def _role_is_inspected(source: str) -> bool:
    """True if the module reads a role at all — by attribute (`identity.role`), by name
    (`getattr(x, "role")`) or by key (`details["role"]`). Parsed, not grepped, so it catches the
    two evasions a substring check misses. It is not unevadable — `getattr(identity, "ro"+"le")`
    defeats it — which is why the load-bearing proof is §2, not this."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "role":
            return True
        if isinstance(node, ast.Constant) and node.value == "role":
            return True
    return False


class TestNoAuthorizationLogicSurvivesInsideMcpServer:
    def test_the_collaboration_service_never_inspects_a_role(self) -> None:
        """The exact grep the cold audit ran, inverted — and made evasion-proof by parsing."""
        assert _role_is_inspected(_source(SERVICE_SOURCE)) is False

    def test_the_collaboration_service_reads_the_policy_it_holds(self) -> None:
        """B1's fact was that `_policy` appeared once — the assignment. A count alone would be
        satisfied by dead calls, which is why §2 exists; this is the cheap corroboration."""
        assert _source(SERVICE_SOURCE).count("self._policy.") >= 12

    def test_the_tool_layer_never_inspects_the_authenticated_node_role(self) -> None:
        """`sovereign_tools.py` carried two duplicate role gates of its own. It legitimately
        mentions "role" in tool schemas (spawn_worker takes one) and reads it ONCE to build the
        `Identity` it hands to the policy, so the assertion is narrow rather than absolute — and
        the behavioural proof is `test_an_injected_permissive_policy_reaches_past_the_tool_layer_gate`,
        which no source check can stand in for."""
        source = _source(TOOLS_SOURCE)
        assert "self.identity.role" not in source
        assert source.count('identity_details["role"]') == 1  # the Identity constructor, only


# ---------------------------------------------------------------------------
# 2. the delegation half: the service follows an injected policy, both directions
# ---------------------------------------------------------------------------

DENIED = "denied by the injected test policy"
ALLOWED = "allowed by the injected test policy"
_ENTRY_POINTS = (
    "authorize_task_create", "authorize_task_read", "authorize_task_update",
    "authorize_send_message", "authorize_message_read", "authorize_read_task_transcript",
    "authorize_debate",  # the pre-existing I-DS1 caller rule; open_debate asks it first
    "authorize_open_debate", "authorize_debate_turn", "authorize_debate_close",
    "authorize_debate_read", "authorize_publish_candidate", "authorize_publish_synthesis",
    "authorize_debate_abort",   # U416's terminal state, added at unit 5 with its rule HERE
)


def _policy_answering(allow: bool, reason: str) -> SovereignPolicy:
    """A policy whose thirteen collaboration entry points all return the same verdict, built by
    name from `_ENTRY_POINTS`. `test_every_policy_call_the_service_makes_is_covered` asserts the
    converse — that the tuple names everything the service actually asks — so an entry point
    added later cannot escape these tests silently."""
    class _Injected(SovereignPolicy):
        pass
    for name in _ENTRY_POINTS:
        assert hasattr(SovereignPolicy, name), f"{name} is not a policy entry point"
        setattr(_Injected, name, staticmethod(lambda *a, _v=Verdict(allow, reason), **k: _v))
    return _Injected()


def _policy_calls(source: str) -> set[str]:
    """Every `self._policy.X(...)` / `self.policy.X(...)` name a module asks for, by parse."""
    names = set()
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Attribute) or not isinstance(node.value, ast.Attribute):
            continue
        if node.value.attr in ("_policy", "policy") and isinstance(node.value.value, ast.Name):
            names.add(node.attr)
    return names


class TestTheServiceObeysTheInjectedPolicy:
    def test_every_policy_call_the_service_makes_is_covered(self) -> None:
        """The converse of `_policy_answering`'s check: nothing `mcp_server/` asks the policy may
        be missing from `_ENTRY_POINTS`, or a rule would have no permissive test and a duplicate
        of it could hide."""
        asked = _policy_calls(_source(SERVICE_SOURCE)) | _policy_calls(_source(TOOLS_SOURCE))
        # No subtraction. The first version excused `authorize_put_artifact`/`authorize_read`,
        # neither of which either module asks — a vestigial escape hatch through which a
        # collaboration decision routed via `authorize_read` would have left the permissive-policy
        # coverage silently (round-3 spec-audit MINOR-11).
        assert asked <= set(_ENTRY_POINTS)

    def test_a_denying_policy_stops_every_write_and_read_path(self, store: SovereignStore) -> None:
        seeded = CollaborationService(store, SovereignPolicy())
        task = _task(seeded)
        debate = _debate(seeded, task, max_rounds=1)
        service = CollaborationService(store, _policy_answering(False, DENIED))
        calls = [
            lambda: service.create_task(COND, objective="o", owner_node_ids=[W1.node_id]),
            lambda: service.get_task(COND, task["task_id"]),
            lambda: service.update_task(W1, task_id=task["task_id"], status="IN_PROGRESS"),
            lambda: service.send_message(
                COND, task_id=task["task_id"], thread_id=None, recipient_node_ids=[W1.node_id],
                message_kind="question", body="?"),
            lambda: service.open_debate(
                COND, task_id=task["task_id"], proposition="p",
                participant_node_ids=[W1.node_id, W2.node_id]),
            lambda: service.post_debate_turn(W1, debate_id=debate["debate_id"], body="turn"),
            lambda: service.close_debate(COND, debate_id=debate["debate_id"], decision="d"),
            lambda: service.get_debate(W1, debate["debate_id"]),
            lambda: service.record_candidate(
                W1, task_id=task["task_id"], candidate=_candidate(W1.node_id)),
            lambda: service.record_synthesis(COND, task_id=task["task_id"], synthesis={}),
        ]
        for call in calls:
            with pytest.raises(CollaborationError, match=DENIED):
                call()

    def test_a_denying_read_policy_empties_the_list_views(self, store: SovereignStore) -> None:
        seeded = CollaborationService(store, SovereignPolicy())
        task = _task(seeded)
        _debate(seeded, task)
        service = CollaborationService(store, _policy_answering(False, DENIED))
        assert service.list_tasks(COND) == []
        assert service.list_debates(COND) == []


class TestAPermissivePolicyReachesPastEveryRule:
    """The direction a duplicated rule cannot survive. Each test performs an operation the
    SHIPPED policy refuses and requires it to SUCCEED (or to fail for a reason that is not the
    authority reason, where a later non-authority rule intervenes). A `raise` left behind in
    `mcp_server/` — U326's exact shape — fails here, and no source grep is consulted."""

    @pytest.fixture()
    def open_service(self, store: SovereignStore) -> CollaborationService:
        return CollaborationService(store, _policy_answering(True, ALLOWED))

    @pytest.fixture()
    def seeded(self, store: SovereignStore) -> dict[str, Any]:
        return _task(CollaborationService(store, SovereignPolicy()))

    def test_task_create(self, open_service: CollaborationService) -> None:
        task = open_service.create_task(W1, objective="self-assigned", owner_node_ids=[W1.node_id])
        assert task["created_by_node_id"] == W1.node_id and task["status"] == "ASSIGNED"

    def test_task_read(self, open_service: CollaborationService, seeded: dict) -> None:
        assert open_service.get_task(STRANGER, seeded["task_id"])["task_id"] == seeded["task_id"]
        assert [t["task_id"] for t in open_service.list_tasks(STRANGER)] == [seeded["task_id"]]

    def test_task_update(self, open_service: CollaborationService, seeded: dict) -> None:
        assert open_service.update_task(
            STRANGER, task_id=seeded["task_id"], status="CANCELLED")["status"] == "CANCELLED"

    def test_send_message_outside_the_task(self, open_service: CollaborationService, seeded: dict) -> None:
        msg = open_service.send_message(
            STRANGER, task_id=seeded["task_id"], thread_id=None,
            recipient_node_ids=["node-nowhere"], message_kind="question", body="reachable?")
        assert msg["recipient_node_ids"] == ["node-nowhere"]

    def test_message_read_and_full_transcript(self, store: SovereignStore, seeded: dict) -> None:
        shipped = CollaborationService(store, SovereignPolicy())
        private = shipped.send_message(
            W1, task_id=seeded["task_id"], thread_id=None, recipient_node_ids=[COND.node_id],
            message_kind="progress", body="halfway")
        open_service = CollaborationService(store, _policy_answering(True, ALLOWED))
        assert private["message_id"] in [
            m["message_id"] for m in open_service.read_messages(W2, task_id=seeded["task_id"])]
        assert len(open_service.read_messages(W2, task_id=seeded["task_id"], include_all=True)) == 2

    def test_open_debate_as_voice_over_outside_nodes(self, open_service: CollaborationService,
                                                    seeded: dict) -> None:
        debate = open_service.open_debate(
            VOICE, task_id=seeded["task_id"], proposition="p",
            participant_node_ids=[W1.node_id, "node-nowhere"])
        assert debate["opened_by_node_id"] == VOICE.node_id

    def test_debate_turn_by_a_non_participant(self, store: SovereignStore, seeded: dict) -> None:
        shipped = CollaborationService(store, SovereignPolicy())
        debate = _debate(shipped, seeded)
        open_service = CollaborationService(store, _policy_answering(True, ALLOWED))
        assert open_service.post_debate_turn(
            COND, debate_id=debate["debate_id"], body="mine now")["node_id"] == COND.node_id

    def test_debate_close_by_a_worker(self, store: SovereignStore, seeded: dict) -> None:
        shipped = CollaborationService(store, SovereignPolicy())
        debate = _debate(shipped, seeded, max_rounds=1)
        shipped.post_debate_turn(W1, debate_id=debate["debate_id"], body="a")
        shipped.post_debate_turn(W2, debate_id=debate["debate_id"], body="b")
        open_service = CollaborationService(store, _policy_answering(True, ALLOWED))
        closed = open_service.close_debate(W1, debate_id=debate["debate_id"], decision="mine")
        assert closed["state"] == "CLOSED" and closed["closed_by_node_id"] == W1.node_id

    def test_debate_read_by_a_stranger(self, store: SovereignStore, seeded: dict) -> None:
        debate = _debate(CollaborationService(store, SovereignPolicy()), seeded)
        open_service = CollaborationService(store, _policy_answering(True, ALLOWED))
        assert open_service.get_debate(STRANGER, debate["debate_id"])["debate_id"] == debate["debate_id"]
        assert [d["debate_id"] for d in open_service.list_debates(STRANGER)] == [debate["debate_id"]]

    def test_publish_candidate_by_the_conductor(self, open_service: CollaborationService,
                                                seeded: dict) -> None:
        updated = open_service.record_candidate(
            COND, task_id=seeded["task_id"], candidate=_candidate(COND.node_id))
        assert COND.node_id in updated["candidates"]

    def test_publish_synthesis_by_a_worker_passes_the_gate(self, open_service: CollaborationService,
                                                           seeded: dict) -> None:
        """The synthesis completeness rule (a service rule, not an authority rule — see U344)
        stops this one step later. What matters is WHICH refusal arrives: the authority reason
        would mean a duplicated role check is still in `mcp_server/`."""
        with pytest.raises(CollaborationError, match="synthesis requires candidates from every worker"):
            open_service.record_synthesis(W1, task_id=seeded["task_id"], synthesis={"s": 1})


# ---------------------------------------------------------------------------
# 3. the rules themselves, exercised through the collaboration path
#    (mutation targets for tools/mutation/_op19_policy_delegation_mutations.py)
# ---------------------------------------------------------------------------

class TestTheRulesStillHoldThroughTheCollaborationPath:
    def test_a_worker_may_not_create_an_assignment(self, service: CollaborationService) -> None:
        with pytest.raises(CollaborationError, match="only the conductor/operator may create"):
            service.create_task(W1, objective="self-assigned", owner_node_ids=[W1.node_id])

    def test_a_stranger_may_not_read_a_task_it_does_not_own(self, service: CollaborationService) -> None:
        task = _task(service)
        with pytest.raises(CollaborationError, match="cross-task access denied"):
            service.get_task(STRANGER, task["task_id"])

    def test_a_stranger_may_not_update_a_task_it_does_not_own(self, service: CollaborationService) -> None:
        task = _task(service)
        with pytest.raises(CollaborationError, match="cross-task access denied"):
            service.update_task(STRANGER, task_id=task["task_id"], status="IN_PROGRESS")

    def test_list_tasks_shows_a_worker_only_its_own(self, service: CollaborationService) -> None:
        task = _task(service)
        assert [t["task_id"] for t in service.list_tasks(W1)] == [task["task_id"]]
        assert service.list_tasks(STRANGER) == []
        assert [t["task_id"] for t in service.list_tasks(COND)] == [task["task_id"]]

    def test_a_voice_identity_is_scoped_like_a_worker_on_reads_and_writes(
            self, service: CollaborationService) -> None:
        """`_SCOPED_ROLES` pairs `voice` with `worker`, as the rest of the policy already did.
        Before this unit the collaboration copy scoped `worker` alone, so a voice identity could
        read AND cancel any task in the project."""
        task = _task(service)
        for call in (
            lambda: service.get_task(VOICE, task["task_id"]),
            lambda: service.update_task(VOICE, task_id=task["task_id"], status="CANCELLED"),
            lambda: service.send_message(
                VOICE, task_id=task["task_id"], thread_id=None, recipient_node_ids=[W1.node_id],
                message_kind="question", body="?"),
        ):
            with pytest.raises(CollaborationError, match="cross-task access denied"):
                call()
        assert service.list_tasks(VOICE) == []
        debate = _debate(service, task)
        with pytest.raises(CollaborationError, match="not a debate participant"):
            service.get_debate(VOICE, debate["debate_id"])
        assert service.list_debates(VOICE) == []

    def test_a_malformed_role_is_refused_everywhere_it_is_asked(
            self, service: CollaborationService) -> None:
        """Deny-by-default on the role itself, uniformly: the first draft gated the task rules
        and not the debate ones, so a malformed role read zero tasks and every project debate."""
        task = _task(service)
        debate = _debate(service, task)
        with pytest.raises(CollaborationError, match="unknown role 'hacker'"):
            service.create_task(MALFORMED, objective="o", owner_node_ids=[W1.node_id])
        with pytest.raises(CollaborationError, match="unknown role 'hacker'"):
            service.get_task(MALFORMED, task["task_id"])
        with pytest.raises(CollaborationError, match="unknown role 'hacker'"):
            service.get_debate(MALFORMED, debate["debate_id"])
        assert service.list_tasks(MALFORMED) == []
        assert service.list_debates(MALFORMED) == []

    def test_a_gate_node_is_not_one_of_the_directing_roles(self, service: CollaborationService) -> None:
        """`_DIRECTING_ROLES` is the membership set behind four rules — the thing an operator
        would actually edit. The deny statements are mutated by P1/P6/P10/P13; this pins the set
        itself in the WIDENING direction, which is the half round 2 found unguarded.

        It was called `test_a_gate_node_directs_nothing` until round 3, and that name was an
        absolute the shipped code falsifies: a gate is deliberately NOT in `_SCOPED_ROLES`, so it
        reads every task in the project, and through that read it may `update_task` (including
        `CANCELLED`), `send_message` into a task thread, and — new in this unit, by the directed
        move to `authorize_debate` — open a debate that costs budget and arms its participants'
        turn timers (U349). What it may not do is the four things below."""
        task = _task(service)
        debate = _debate(service, task, max_rounds=1)
        service.post_debate_turn(W1, debate_id=debate["debate_id"], body="a")
        service.post_debate_turn(W2, debate_id=debate["debate_id"], body="b")
        with pytest.raises(CollaborationError, match="only the conductor/operator may create"):
            service.create_task(GATE, objective="o", owner_node_ids=[W1.node_id])
        with pytest.raises(CollaborationError, match="only conductor/operator may close a debate"):
            service.close_debate(GATE, debate_id=debate["debate_id"], decision="mine")
        with pytest.raises(CollaborationError, match="only conductor/operator may publish synthesis"):
            service.record_synthesis(GATE, task_id=task["task_id"], synthesis={"s": 1})
        service.send_message(W1, task_id=task["task_id"], thread_id=None,
                             recipient_node_ids=[COND.node_id], message_kind="progress", body="x")
        # a gate reads the project but not another node's private traffic
        assert len(service.read_messages(GATE, task_id=task["task_id"], include_all=True)) == 0
        # and what it CAN do, asserted rather than left to a name (U349 owns whether it should):
        assert service.update_task(
            GATE, task_id=task["task_id"], status="BLOCKED")["status"] == "BLOCKED"
        assert service.send_message(
            GATE, task_id=task["task_id"], thread_id=None, recipient_node_ids=[W1.node_id],
            message_kind="challenge", body="justify risk A")["sender_node_id"] == GATE.node_id
        assert service.open_debate(
            GATE, task_id=task["task_id"], proposition="risk A outranks risk B",
            participant_node_ids=[W1.node_id, W2.node_id])["opened_by_node_id"] == GATE.node_id

    def test_every_role_the_policy_admits_has_a_pinned_collaboration_reach(
            self, service: CollaborationService) -> None:
        """`ROLES` became a collaboration READ rule at this unit — `_unknown` is what makes a
        malformed role read nothing — and its MEMBERSHIP was pinned by nothing: adding a member
        handed that role project-wide task and debate reads, and the whole suite stayed green
        (round-3 gate-validator, mutation A5). A role admitted here must declare its reach, and
        the reach is then exercised through the collaboration path rather than asserted."""
        reach = {"conductor": "project", "operator": "project", "gate": "project",
                 "worker": "assigned", "voice": "assigned"}
        task = _task(service)
        # Iterate ROLES, not `reach`: a member added to the constant is then PROBED THROUGH THE
        # SERVICE and must read nothing, because a role this table does not declare has no
        # declared reach. Round 4 was right that the earlier order — assert the constant, then
        # loop over the declaration — made this a structural tripwire wearing a behavioural coat.
        for role in sorted(ROLES):
            probe = Identity(f"{role}-probe", role, "proj")   # deliberately owns nothing
            visible = [t["task_id"] for t in service.list_tasks(probe)]
            assert visible == ([task["task_id"]] if reach.get(role) == "project" else []), role
        assert set(ROLES) == set(reach), "a role added to ROLES must declare its reach here"

    def test_the_default_read_gives_the_conductor_only_its_own_traffic(
            self, service: CollaborationService) -> None:
        """`authorize_message_read` is per-message visibility and applies to EVERY role; the
        conductor's whole-transcript view is the `include_all` path, which asks a different rule.
        A directing-role short-circuit inside the per-message rule would hand the conductor every
        message on the ORDINARY path and leave `authorize_read_task_transcript` decorative —
        invariant 8. Round 3 proved that widening survived the entire suite (mutation A1)."""
        task = _task(service)
        between_workers = service.send_message(
            W1, task_id=task["task_id"], thread_id=task["thread_id"],
            recipient_node_ids=[W2.node_id], message_kind="question", body="which risk first?")
        default_view = [m["message_id"] for m in service.read_messages(COND, task_id=task["task_id"])]
        assert between_workers["message_id"] not in default_view
        assert between_workers["message_id"] in [
            m["message_id"] for m in service.read_messages(
                COND, task_id=task["task_id"], include_all=True)]

    def test_opening_a_debate_does_not_make_the_opener_a_reader_of_it(
            self, service: CollaborationService) -> None:
        """A worker may open a debate it is not a participant of — `authorize_open_debate` scopes
        the PARTICIPANTS to the task, not the caller to the participants — so "the opener may
        always read it" is a reachable widening of `authorize_debate_read`, not an equivalent
        mutant. Nothing caught it before round 3 (mutation A2)."""
        task = _task(service)
        debate = service.open_debate(
            W1, task_id=task["task_id"], proposition="risk A outranks risk B",
            participant_node_ids=[W2.node_id, COND.node_id])
        assert debate["opened_by_node_id"] == W1.node_id
        with pytest.raises(CollaborationError, match="not a debate participant"):
            service.get_debate(W1, debate["debate_id"])
        assert service.list_debates(W1) == []

    def test_a_conductor_named_as_an_owner_still_may_not_publish_a_candidate(
            self, service: CollaborationService) -> None:
        """The candidate rule's role half in the WIDENING direction — round-2 MAJOR-2 recurring on
        a third membership set (round-3 mutation A3). `test_only_the_worker_role_publishes_a_
        candidate_even_when_assigned` pins a VOICE owner, so admitting `conductor` stayed green,
        and a conductor may genuinely be named an owner. I-M6: the node that synthesizes does not
        also publish the candidates it will judge (invariant 18)."""
        task = service.create_task(COND, objective="o",
                                   owner_node_ids=[W1.node_id, COND.node_id])
        with pytest.raises(CollaborationError, match="only an assigned worker"):
            service.record_candidate(COND, task_id=task["task_id"],
                                     candidate=_candidate(COND.node_id))

    def test_synthesis_asks_task_read_before_it_publishes(
            self, service: CollaborationService) -> None:
        """The round-2 remediation put `_require_task` in front of `record_synthesis` — the one
        write path that skipped read authority — and deleting it again was green (round-3 mutation
        A6). Shadowed for AUTHORITY (only directing roles get this far, and neither is scoped),
        live for existence, which is an observable verdict either way."""
        with pytest.raises(CollaborationError, match="no such task in this project"):
            service.record_synthesis(COND, task_id="task-does-not-exist", synthesis={"s": 1})

    def test_a_debate_needs_two_participants_not_one(self, service: CollaborationService) -> None:
        """The floor, separately from the subset rule: dropping `len(participants) < 2` left the
        suite green, because every other debate-scope test also violates the subset clause."""
        task = _task(service)
        with pytest.raises(CollaborationError, match="at least two task participants"):
            service.open_debate(COND, task_id=task["task_id"], proposition="p",
                                participant_node_ids=[W1.node_id])

    def test_a_peer_node_that_is_not_an_owner_is_outside_the_authority_set(
            self, service: CollaborationService) -> None:
        """`_task_participants` is owners + creator, faithfully preserved. Whether `peer_nodes`
        SHOULD be in it is U347's open question; until that is decided, this pins what the code
        actually does, so a widening cannot happen by accident."""
        task = service.create_task(COND, objective="o", owner_node_ids=[W1.node_id],
                                   peer_nodes=[W1.node_id, "peer-not-owner"])
        assert "peer-not-owner" in task["peer_nodes"]
        with pytest.raises(CollaborationError, match="cross-task recipient denied"):
            service.send_message(W1, task_id=task["task_id"], thread_id=None,
                                 recipient_node_ids=["peer-not-owner"],
                                 message_kind="question", body="?")

    def test_only_the_worker_role_publishes_a_candidate_even_when_assigned(
            self, service: CollaborationService) -> None:
        """The rule is `role == "worker" AND assigned`, not `assigned`. A voice identity named as
        an owner is still refused — invariant 25: voice cannot expand authority."""
        task = service.create_task(COND, objective="o",
                                   owner_node_ids=[W1.node_id, VOICE.node_id])
        with pytest.raises(CollaborationError, match="only an assigned worker"):
            service.record_candidate(VOICE, task_id=task["task_id"],
                                     candidate=_candidate(VOICE.node_id))

    def test_a_message_may_not_be_addressed_outside_the_task(self, service: CollaborationService) -> None:
        task = _task(service)
        with pytest.raises(CollaborationError, match="cross-task recipient denied"):
            service.send_message(
                W1, task_id=task["task_id"], thread_id=task["thread_id"],
                recipient_node_ids=[STRANGER.node_id], message_kind="question", body="leak?")

    def test_a_worker_reads_only_the_messages_it_is_party_to(self, service: CollaborationService) -> None:
        task = _task(service)
        private = service.send_message(
            W1, task_id=task["task_id"], thread_id=task["thread_id"],
            recipient_node_ids=[COND.node_id], message_kind="progress", body="halfway")
        visible = [m["message_id"] for m in service.read_messages(W2, task_id=task["task_id"])]
        assert private["message_id"] not in visible
        assert private["message_id"] in [
            m["message_id"] for m in service.read_messages(W1, task_id=task["task_id"])]

    def test_only_the_conductor_reads_the_full_transcript(self, service: CollaborationService) -> None:
        task = _task(service)
        service.send_message(
            W1, task_id=task["task_id"], thread_id=task["thread_id"],
            recipient_node_ids=[COND.node_id], message_kind="progress", body="halfway")
        assert len(service.read_messages(COND, task_id=task["task_id"], include_all=True)) == 2
        # a worker asking for everything is scoped, not obeyed (invariant 8)
        assert len(service.read_messages(W2, task_id=task["task_id"], include_all=True)) == 1

    def test_any_authorized_node_may_open_a_debate_but_voice_may_not(self, service: CollaborationService) -> None:
        """I-DS1 via `control_plane/policy.py:authorize_debate` — the entry point unit 19.2 was
        told to use. A worker may request; voice is a transducer, not a reasoning caller."""
        task = _task(service)
        opened = service.open_debate(
            W1, task_id=task["task_id"], proposition="risk A outranks risk B",
            participant_node_ids=[W1.node_id, W2.node_id])
        assert opened["opened_by_node_id"] == W1.node_id
        with pytest.raises(CollaborationError, match="may not request debate"):
            service.open_debate(
                VOICE, task_id=task["task_id"], proposition="p",
                participant_node_ids=[W1.node_id, W2.node_id])

    def test_a_debate_may_not_be_opened_over_nodes_outside_the_task(self, service: CollaborationService) -> None:
        task = _task(service)
        with pytest.raises(CollaborationError, match="at least two task participants"):
            service.open_debate(
                COND, task_id=task["task_id"], proposition="p",
                participant_node_ids=[W1.node_id, STRANGER.node_id])

    def test_a_non_participant_may_not_post_a_turn(self, service: CollaborationService) -> None:
        debate = _debate(service, _task(service))
        with pytest.raises(CollaborationError, match="not a debate participant"):
            service.post_debate_turn(COND, debate_id=debate["debate_id"], body="mine now")

    def test_a_worker_may_not_close_a_debate(self, service: CollaborationService) -> None:
        debate = _debate(service, _task(service), max_rounds=1)
        service.post_debate_turn(W1, debate_id=debate["debate_id"], body="a")
        service.post_debate_turn(W2, debate_id=debate["debate_id"], body="b")
        with pytest.raises(CollaborationError, match="only conductor/operator may close"):
            service.close_debate(W1, debate_id=debate["debate_id"], decision="mine")

    def test_a_non_participant_worker_may_not_read_a_debate(self, service: CollaborationService) -> None:
        debate = _debate(service, _task(service))
        with pytest.raises(CollaborationError, match="not a debate participant"):
            service.get_debate(STRANGER, debate["debate_id"])
        assert service.list_debates(STRANGER) == []
        assert [d["debate_id"] for d in service.list_debates(W1)] == [debate["debate_id"]]

    def test_only_an_assigned_worker_publishes_a_candidate(self, service: CollaborationService) -> None:
        task = _task(service)
        with pytest.raises(CollaborationError, match="only an assigned worker"):
            service.record_candidate(COND, task_id=task["task_id"],
                                     candidate=_candidate(COND.node_id))

    def test_a_worker_may_not_publish_the_synthesis(self, service: CollaborationService) -> None:
        task = _task(service)
        with pytest.raises(CollaborationError, match="only conductor/operator may publish synthesis"):
            service.record_synthesis(W1, task_id=task["task_id"], synthesis={"status": "SYNTHESIS"})


# ---------------------------------------------------------------------------
# 4. what the relocation exposed (U343)
# ---------------------------------------------------------------------------

class TestTheUpdateRuleIsTheReadRule:
    """`authorize_task_update` deliberately has no clause of its own. The inline check it
    replaced was unconditionally dead — its condition was byte-identical to the read rule that
    ran first — so it is not carried forward with an invented justification. If update authority
    ever diverges from read authority, it diverges HERE, and this test is where that shows."""

    def test_update_authority_is_exactly_read_authority_today(self, service: CollaborationService) -> None:
        policy = SovereignPolicy()
        task = _task(service)
        for who in (COND, W1, STRANGER, VOICE, GATE, MALFORMED):
            read = policy.authorize_task_read(who, task)
            update = policy.authorize_task_update(who, task)
            assert (update.allow, update.reason) == (read.allow, read.reason), who


class TestTheSenderRuleIsShadowedOnTheServicePath:
    """`send_message`'s sender clause is unreachable through the service — `_require_task`
    refuses a scoped non-owner first, with the same condition — but unlike the update rule it is
    LIVE for a direct caller, so deleting it changes an observable verdict. Assertion of current
    behaviour in the style U304 established: a unit that makes it reachable turns this red."""

    def test_the_sender_rule_is_live_for_a_direct_caller(self, service: CollaborationService) -> None:
        task = _task(service)
        assert SovereignPolicy().authorize_send_message(STRANGER, task, [W1.node_id]).reason == (
            "sender is not a participant in this task")

    def test_but_the_task_read_answers_first_on_the_service_path(self, service: CollaborationService) -> None:
        task = _task(service)
        with pytest.raises(CollaborationError, match="cross-task access denied"):
            service.send_message(STRANGER, task_id=task["task_id"], thread_id=None,
                                 recipient_node_ids=[W1.node_id], message_kind="question", body="?")


# ---------------------------------------------------------------------------
# 5. defence in depth: clauses the collaboration path cannot reach
# ---------------------------------------------------------------------------

class TestTheCrossProjectClausesAreDefenceInDepth:
    """`SovereignStore` scopes every operational read by `identity.project_id` before the policy
    is asked, so no cross-project record can ever be handed to these clauses from the service.
    They are asserted directly and labelled as such — a mutation row graded by these tests has
    NOT been proven through the collaboration path, and the harness says so at the row."""

    def _foreign(self) -> tuple[dict, dict, dict]:
        return ({"project_id": "other", "owner_node_ids": ["worker-1"], "created_by_node_id": "c"},
                {"project_id": "other", "sender_node_id": "worker-1", "recipient_node_ids": []},
                {"project_id": "other", "participant_node_ids": ["worker-1"]})

    def test_a_foreign_project_record_is_refused_by_each_read_rule(self) -> None:
        """Asserted for a DIRECTING identity as well as a worker: round 4 showed that a
        directing-role short-circuit inserted ahead of the cross-project clause survived the
        suite, because every assertion here used `W1`. Project scope is not a worker rule."""
        policy, (task, message, debate) = SovereignPolicy(), self._foreign()
        for who in (W1, COND, GATE):
            assert policy.authorize_task_read(who, task).reason == "cross-project task read denied (scope)"
            assert policy.authorize_message_read(who, message).reason == "cross-project message read denied (scope)"
            assert policy.authorize_debate_read(who, debate).reason == "cross-project debate read denied (scope)"

    def test_the_store_is_why_the_service_never_reaches_them(self, service: CollaborationService) -> None:
        task = _task(service)
        other_project = Identity(W1.node_id, "worker", "other-project")
        with pytest.raises(CollaborationError, match="no such task in this project"):
            service.get_task(other_project, task["task_id"])


# ---------------------------------------------------------------------------
# 6. the tool layer the live nodes actually call
# ---------------------------------------------------------------------------

class _FakeApp:
    """Stands in for the Electron application-control channel. Every method that reaches it is
    past the authority gate, so a call here on a refused path is itself the failure."""

    def __init__(self, identity: Identity, *, allow_calls: bool = False) -> None:
        self._details = {"node_id": identity.node_id, "role": identity.role,
                         "project_id": identity.project_id, "provider_id": "p", "model_id": "m"}
        self._allow_calls = allow_calls

    def identity_details(self) -> dict[str, Any]:
        return dict(self._details)

    def call(self, operation: str, arguments: dict[str, Any] | None = None) -> Any:
        if self._allow_calls:
            return {"delivered": operation}
        raise AssertionError(f"application call {operation!r} made on a path the policy refused")


class TestTheToolLayerAsksThePolicyToo:
    """`SovereignToolRuntime` takes its policy as a REQUIRED keyword, so the tool layer's
    delegation is falsifiable by behaviour and not only by reading its source."""

    def _runtime(self, tmp_path: pathlib.Path, identity: Identity,
                 policy: SovereignPolicy | None = None, *,
                 allow_calls: bool = False) -> SovereignToolRuntime:
        return SovereignToolRuntime(_FakeApp(identity, allow_calls=allow_calls), tmp_path,
                                    policy=policy or SovereignPolicy())

    def test_a_conductor_may_not_publish_a_candidate(self, tmp_path: pathlib.Path) -> None:
        runtime = self._runtime(tmp_path, COND)
        try:
            task = _task(runtime.collaboration)
            with pytest.raises(ToolError, match="only an assigned worker may publish a candidate"):
                runtime.call("publish_candidate", {"task_id": task["task_id"], "summary": "s",
                                                   "claims": ["c"], "evidence_refs": ["e"],
                                                   "peer_messages_considered": [],
                                                   "debates_considered": [], "limitations": []})
        finally:
            runtime.close()

    def test_a_worker_may_not_publish_the_synthesis(self, tmp_path: pathlib.Path) -> None:
        """The task is real and the arguments are COMPLETE, so deleting this gate does not fail
        incidentally on shape validation: the call would run to the service, which refuses it as
        `CollaborationError` — defence in depth, and a different exception type, so the row that
        deletes the gate goes red for the refusal that vanished rather than for a typo."""
        seeder = self._runtime(tmp_path, COND)
        try:
            task = _task(seeder.collaboration)
        finally:
            seeder.close()
        runtime = self._runtime(tmp_path, W1)
        try:
            with pytest.raises(ToolError, match="only conductor/operator may publish synthesis"):
                runtime.call("publish_synthesis", _synthesis_args(task["task_id"]))
        finally:
            runtime.close()

    def test_an_unassigned_worker_is_refused_before_anything_reaches_cas(
            self, tmp_path: pathlib.Path) -> None:
        """The improvement this unit claims on this path, asserted rather than described: the
        gate is upstream of `memory.put_artifact`, so a refused candidate leaves NO blob behind.
        Round 2 showed a re-inlined `getattr` role check could revert this invisibly, because the
        only guard was a source grep."""
        seeder = self._runtime(tmp_path, COND)
        try:
            task = _task(seeder.collaboration)
        finally:
            seeder.close()
        outsider = Identity("worker-out", "worker", "proj")
        runtime = self._runtime(tmp_path, outsider)
        try:
            # NOTE the exception TYPE: the tool layer fetches the task through the collaboration
            # service, so an unassigned worker's refusal surfaces as `CollaborationError`, not
            # `ToolError`. The JSON-RPC boundary prints the type name, so the wire text changed
            # when this gate moved upstream of the CAS write. Recorded, not hidden.
            with pytest.raises(CollaborationError, match="cross-task access denied"):
                runtime.call("publish_candidate", {"task_id": task["task_id"], "summary": "s",
                                                   "claims": ["c"], "evidence_refs": ["e"],
                                                   "peer_messages_considered": [],
                                                   "debates_considered": [], "limitations": []})
        finally:
            runtime.close()
        assert [p for p in (tmp_path / "cas").rglob("*") if p.is_file()] == []

    def test_an_injected_permissive_policy_reaches_past_the_candidate_gate(
            self, tmp_path: pathlib.Path) -> None:
        """The permissive direction on the CANDIDATE path — the gate round 2 found guarded only
        by a grep. With an authority that allows it, a conductor's candidate call must get past
        the gate; a re-inlined role check in `sovereign_tools.py` fails this however it is
        spelled."""
        runtime = self._runtime(tmp_path, COND, policy=_policy_answering(True, ALLOWED),
                                allow_calls=True)
        try:
            task = _task(runtime.collaboration)
            result = runtime.call("publish_candidate", {
                "task_id": task["task_id"], "summary": "s", "claims": ["c"],
                "evidence_refs": ["e"], "peer_messages_considered": [],
                "debates_considered": [], "limitations": []})
            assert result["candidate"]["status"] == "CANDIDATE"
        finally:
            runtime.close()

    def test_an_injected_permissive_policy_reaches_past_the_tool_layer_gate(
            self, tmp_path: pathlib.Path) -> None:
        """The permissive direction, on the tool layer: with an authority that allows it, a
        worker's synthesis call must get PAST the gate and fail on a later, non-authority rule.
        A re-inlined role check in `sovereign_tools.py` fails this."""
        seeder = self._runtime(tmp_path, COND)
        try:
            task = _task(seeder.collaboration)
        finally:
            seeder.close()
        runtime = self._runtime(tmp_path, W1, policy=_policy_answering(True, ALLOWED))
        try:
            # A SCHEMA-COMPLETE payload since W-33. It used to pass `{"task_id": ...}` alone and
            # rely on the tool layer to raise something — anything — that was not the role refusal.
            # With the declared inputSchema now enforced before dispatch, that payload is refused by
            # SHAPE and never reaches the layer this test is about, so P23's mutation (the tool
            # layer re-inlining its own role check) became undetectable and the harness reported
            # `GREEN (guard does not hold)`. The arguments are complete so the call gets PAST
            # validation and fails on a later, non-authority rule, which is what the docstring
            # always claimed it was testing.
            with pytest.raises(ToolError) as exc:
                runtime.call("publish_synthesis", {
                    "task_id": task["task_id"],
                    "contributions": [{"node_id": W1.node_id, "contribution": "w1 said"}],
                    "points_of_agreement": ["a"], "points_of_disagreement": [],
                    "debate_outcome": "o", "evidence_used": ["e"], "limitations": [],
                    "conductor_judgment": "j", "recommended_next_action": "n", "debate_ids": []})
            assert "only conductor/operator may publish synthesis" not in str(exc.value)
        finally:
            runtime.close()

    def test_the_service_still_refuses_what_the_tool_layer_lets_through(
            self, tmp_path: pathlib.Path) -> None:
        """Defence in depth, stated as a property: the tool-layer gate is not the only one. With
        a permissive tool-layer authority but the SHIPPED service policy, a worker's synthesis
        still dies at `record_synthesis` — which is why round 2's re-inline finding was an
        invariant-7 and CAS-write regression, not a live authorization bypass."""
        seeder = self._runtime(tmp_path, COND)
        try:
            task = _task(seeder.collaboration)
            # Candidates for both owners, so the permissive tool-layer authority under test carries
            # this call PAST the U333 contributions cross-check and into the service, which is the
            # refusal the test is about. Without them it would die on shape and prove nothing.
            for worker in (W1, W2):
                seeder.collaboration.record_candidate(
                    worker, task_id=task["task_id"], candidate=_candidate(worker.node_id))
        finally:
            seeder.close()
        runtime = self._runtime(tmp_path, W1, policy=_policy_answering(True, ALLOWED))
        runtime.collaboration = CollaborationService(runtime.store, SovereignPolicy())
        try:
            with pytest.raises(CollaborationError, match="only conductor/operator may publish synthesis"):
                runtime.call("publish_synthesis", _synthesis_args(task["task_id"]))
        finally:
            runtime.close()

    def test_the_runtime_will_not_manufacture_its_own_authority(self, tmp_path: pathlib.Path) -> None:
        """A defaulted policy is the U292(a) shape: the product path would construct the very
        object a test then injects, and nobody would notice if the caller stopped supplying it."""
        with pytest.raises(TypeError):
            SovereignToolRuntime(_FakeApp(COND), tmp_path)


# ---------------------------------------------------------------------------
# 7. the whole verdict surface, pinned as one table (U352)
# ---------------------------------------------------------------------------

VOICE_OWNER = Identity("voice-own", "voice", "proj")
OPERATOR = Identity("op-1", "operator", "proj")

MATRIX_IDENTITIES = {
    "conductor(creator)": COND, "operator": OPERATOR, "gate": GATE,
    "worker(owner)": W1, "worker(outside)": STRANGER,
    "voice(owner)": VOICE_OWNER, "voice(outside)": VOICE, "malformed": MALFORMED,
}


def _outcome(call: Any) -> str:
    """The observation, not an assertion about it: what a caller actually gets back."""
    try:
        value = call()
    except Exception as exc:                      # noqa: BLE001 — the exception IS the outcome
        return f"{type(exc).__name__}: {exc}"
    return f"ok:len={len(value)}" if isinstance(value, list) else "ok"


def _matrix_world(service: CollaborationService) -> tuple[dict[str, Any], dict[str, Any]]:
    """One deterministic world, built by the conductor through the SHIPPED policy: a task with
    three owners (one of them a voice identity, so the voice-as-owner cells are reachable), a
    debate between the two workers with a turn from each, and one message a third party never
    saw."""
    task = service.create_task(
        COND, objective="rank the integration risks",
        owner_node_ids=[W1.node_id, W2.node_id, VOICE_OWNER.node_id],
        acceptance_criteria=["one candidate per worker"])
    debate = service.open_debate(
        COND, task_id=task["task_id"], proposition="risk A outranks risk B",
        participant_node_ids=[W1.node_id, W2.node_id], max_rounds=2)
    service.post_debate_turn(W1, debate_id=debate["debate_id"], body="a")
    service.post_debate_turn(W2, debate_id=debate["debate_id"], body="b")
    service.send_message(W1, task_id=task["task_id"], thread_id=task["thread_id"],
                         recipient_node_ids=[W2.node_id], message_kind="question", body="first?")
    return task, debate


def _open_then_close(service: CollaborationService, who: Identity, task_id: str) -> dict[str, Any]:
    """The cell round 4 needed: whoever OPENS a debate must not thereby be able to close it.
    `authorize_debate_close` asks only for a directing role, and a worker may open a debate — so
    "the opener may close it" is a reachable widening, and closing a debate you argued in is the
    invariant-18 question recorded as U350."""
    opened = service.open_debate(who, task_id=task_id, proposition="closable?",
                                 participant_node_ids=[W1.node_id, W2.node_id], max_rounds=2)
    service.post_debate_turn(W1, debate_id=opened["debate_id"], body="a")
    service.post_debate_turn(W2, debate_id=opened["debate_id"], body="b")
    return service.close_debate(who, debate_id=opened["debate_id"], decision="mine")


def _open_then_abort(service: CollaborationService, who: Identity, task_id: str) -> dict[str, Any]:
    """U416's cell. The debate is opened by the CONDUCTOR so the outcome measures abort authority
    alone rather than whoever happens to be able to open one, and it is a FRESH debate so this
    row's earlier cells are unaffected by it (the ops share one world)."""
    opened = service.open_debate(COND, task_id=task_id, proposition="abortable?",
                                 participant_node_ids=[W1.node_id, W2.node_id], max_rounds=2)
    return service.abort_debate(who, debate_id=opened["debate_id"], reason="peer pane exited")


def _abort_own_debate(service: CollaborationService, who: Identity, task_id: str) -> dict[str, Any]:
    """The cell the 19.5 spec-auditor's MAJOR-1 needed: `who` is a PARTICIPANT in the debate it
    aborts. `authorize_debate_abort` restricts by role and not by participation, so a directing
    node that is arguing in a debate may end it — U350's question for `close_debate`, inherited
    here. The row above cannot see it, because there the aborter is never a participant."""
    opened = service.open_debate(COND, task_id=task_id, proposition="abortable by a party?",
                                 participant_node_ids=[who.node_id, W1.node_id], max_rounds=2)
    return service.abort_debate(who, debate_id=opened["debate_id"], reason="I am in this one")


def _verdict_row(service: CollaborationService, task: dict[str, Any], debate: dict[str, Any],
                 who: Identity) -> dict[str, str]:
    """Reads first, then writes, so the ordering is deterministic and every cell is comparable
    across identities and across mutations."""
    tid, did = task["task_id"], debate["debate_id"]
    ops: list[tuple[str, Any]] = [
        ("get_task", lambda: service.get_task(who, tid)),
        ("list_tasks", lambda: service.list_tasks(who)),
        ("read_messages", lambda: service.read_messages(who, task_id=tid)),
        ("read_messages(all)", lambda: service.read_messages(who, task_id=tid, include_all=True)),
        ("get_debate", lambda: service.get_debate(who, did)),
        ("list_debates", lambda: service.list_debates(who)),
        ("update_task", lambda: service.update_task(who, task_id=tid, status="BLOCKED")),
        ("send_message(owner)", lambda: service.send_message(
            who, task_id=tid, thread_id=None, recipient_node_ids=[W1.node_id],
            message_kind="question", body="?")),
        ("send_message(outsider)", lambda: service.send_message(
            who, task_id=tid, thread_id=None, recipient_node_ids=[STRANGER.node_id],
            message_kind="question", body="?")),
        ("post_turn", lambda: service.post_debate_turn(who, debate_id=did, body="mine")),
        ("close_debate", lambda: service.close_debate(who, debate_id=did, decision="d")),
        ("open_debate(two owners)", lambda: service.open_debate(
            who, task_id=tid, proposition="p", participant_node_ids=[W1.node_id, W2.node_id])),
        ("open_debate(self+owner)", lambda: service.open_debate(
            who, task_id=tid, proposition="p2", participant_node_ids=[who.node_id, W1.node_id])),
        ("open_then_close_own", lambda: _open_then_close(service, who, tid)),
        ("record_candidate", lambda: service.record_candidate(
            who, task_id=tid, candidate={**_candidate(who.node_id), "task_id": tid})),
        ("record_synthesis", lambda: service.record_synthesis(who, task_id=tid, synthesis={"s": 1})),
        ("create_task", lambda: service.create_task(who, objective="o", owner_node_ids=[W1.node_id])),
        ("abort_fresh_debate", lambda: _open_then_abort(service, who, tid)),
        ("abort_own_debate", lambda: _abort_own_debate(service, who, tid)),
    ]
    return {name: _outcome(call) for name, call in ops}


def observed_matrix(root: pathlib.Path) -> dict[str, str]:
    """Every admitted role driven through every collaboration operation, each on its own fresh
    world so no identity's writes colour another's reads."""
    out: dict[str, str] = {}
    for label, who in MATRIX_IDENTITIES.items():
        store = SovereignStore(root / f"{label.replace('(', '_').replace(')', '')}.db")
        try:
            service = CollaborationService(store, SovereignPolicy())
            task, debate = _matrix_world(service)
            for op, outcome in _verdict_row(service, task, debate, who).items():
                out[f"{label} | {op}"] = outcome
        finally:
            store.close()
    return out


#: The pinned table. Regenerate ONLY deliberately:
#:     py -3.12 tests/unit/test_collaboration_policy_delegation.py
#: and justify every changed cell in the unit's evidence, the way §2's before/after table does.
GOLDEN_MATRIX: dict[str, str] = {
    'conductor(creator) | get_task': 'ok',
    'conductor(creator) | list_tasks': 'ok:len=1',
    'conductor(creator) | read_messages': 'ok:len=1',
    'conductor(creator) | read_messages(all)': 'ok:len=4',
    'conductor(creator) | get_debate': 'ok',
    'conductor(creator) | list_debates': 'ok:len=1',
    'conductor(creator) | update_task': 'ok',
    'conductor(creator) | send_message(owner)': 'ok',
    'conductor(creator) | send_message(outsider)': 'CollaborationError: cross-task recipient denied',
    'conductor(creator) | post_turn': 'CollaborationError: node is not a debate participant',
    'conductor(creator) | close_debate': 'ok',
    'conductor(creator) | open_debate(two owners)': 'ok',
    'conductor(creator) | open_debate(self+owner)': 'ok',
    'conductor(creator) | open_then_close_own': 'ok',
    'conductor(creator) | record_candidate': 'CollaborationError: only an assigned worker may publish a candidate',
    'conductor(creator) | record_synthesis': 'CollaborationError: synthesis requires candidates from every worker: worker-1, worker-2, voice-own',
    'conductor(creator) | create_task': 'ok',
    'conductor(creator) | abort_fresh_debate': 'ok',
    'conductor(creator) | abort_own_debate': 'ok',
    'operator | get_task': 'ok',
    'operator | list_tasks': 'ok:len=1',
    'operator | read_messages': 'ok:len=0',
    'operator | read_messages(all)': 'ok:len=4',
    'operator | get_debate': 'ok',
    'operator | list_debates': 'ok:len=1',
    'operator | update_task': 'ok',
    'operator | send_message(owner)': 'ok',
    'operator | send_message(outsider)': 'CollaborationError: cross-task recipient denied',
    'operator | post_turn': 'CollaborationError: node is not a debate participant',
    'operator | close_debate': 'ok',
    'operator | open_debate(two owners)': 'ok',
    'operator | open_debate(self+owner)': 'CollaborationError: debate needs at least two task participants',
    'operator | open_then_close_own': 'ok',
    'operator | record_candidate': 'CollaborationError: only an assigned worker may publish a candidate',
    'operator | record_synthesis': 'CollaborationError: synthesis requires candidates from every worker: worker-1, worker-2, voice-own',
    'operator | create_task': 'ok',
    'operator | abort_fresh_debate': 'ok',
    'operator | abort_own_debate': 'CollaborationError: debate needs at least two task participants',
    'gate | get_task': 'ok',
    'gate | list_tasks': 'ok:len=1',
    'gate | read_messages': 'ok:len=0',
    'gate | read_messages(all)': 'ok:len=0',
    'gate | get_debate': 'ok',
    'gate | list_debates': 'ok:len=1',
    'gate | update_task': 'ok',
    'gate | send_message(owner)': 'ok',
    'gate | send_message(outsider)': 'CollaborationError: cross-task recipient denied',
    'gate | post_turn': 'CollaborationError: node is not a debate participant',
    'gate | close_debate': 'CollaborationError: only conductor/operator may close a debate',
    'gate | open_debate(two owners)': 'ok',
    'gate | open_debate(self+owner)': 'CollaborationError: debate needs at least two task participants',
    'gate | open_then_close_own': 'CollaborationError: only conductor/operator may close a debate',
    'gate | record_candidate': 'CollaborationError: only an assigned worker may publish a candidate',
    'gate | record_synthesis': 'CollaborationError: only conductor/operator may publish synthesis',
    'gate | create_task': 'CollaborationError: only the conductor/operator may create assignments',
    'gate | abort_fresh_debate': 'CollaborationError: only conductor/operator may abort a debate',
    'gate | abort_own_debate': 'CollaborationError: debate needs at least two task participants',
    'worker(owner) | get_task': 'ok',
    'worker(owner) | list_tasks': 'ok:len=1',
    'worker(owner) | read_messages': 'ok:len=4',
    'worker(owner) | read_messages(all)': 'ok:len=4',
    'worker(owner) | get_debate': 'ok',
    'worker(owner) | list_debates': 'ok:len=1',
    'worker(owner) | update_task': 'ok',
    'worker(owner) | send_message(owner)': 'ok',
    'worker(owner) | send_message(outsider)': 'CollaborationError: cross-task recipient denied',
    'worker(owner) | post_turn': 'ok',
    'worker(owner) | close_debate': 'CollaborationError: only conductor/operator may close a debate',
    'worker(owner) | open_debate(two owners)': 'ok',
    'worker(owner) | open_debate(self+owner)': 'CollaborationError: debate needs at least two task participants',
    'worker(owner) | open_then_close_own': 'CollaborationError: only conductor/operator may close a debate',
    'worker(owner) | record_candidate': 'ok',
    'worker(owner) | record_synthesis': 'CollaborationError: only conductor/operator may publish synthesis',
    'worker(owner) | create_task': 'CollaborationError: only the conductor/operator may create assignments',
    'worker(owner) | abort_fresh_debate': 'CollaborationError: only conductor/operator may abort a debate',
    'worker(owner) | abort_own_debate': 'CollaborationError: debate needs at least two task participants',
    'worker(outside) | get_task': 'CollaborationError: cross-task access denied',
    'worker(outside) | list_tasks': 'ok:len=0',
    'worker(outside) | read_messages': 'CollaborationError: cross-task access denied',
    'worker(outside) | read_messages(all)': 'CollaborationError: cross-task access denied',
    'worker(outside) | get_debate': 'CollaborationError: node is not a debate participant',
    'worker(outside) | list_debates': 'ok:len=0',
    'worker(outside) | update_task': 'CollaborationError: cross-task access denied',
    'worker(outside) | send_message(owner)': 'CollaborationError: cross-task access denied',
    'worker(outside) | send_message(outsider)': 'CollaborationError: cross-task access denied',
    'worker(outside) | post_turn': 'CollaborationError: node is not a debate participant',
    'worker(outside) | close_debate': 'CollaborationError: node is not a debate participant',
    'worker(outside) | open_debate(two owners)': 'CollaborationError: cross-task access denied',
    'worker(outside) | open_debate(self+owner)': 'CollaborationError: cross-task access denied',
    'worker(outside) | open_then_close_own': 'CollaborationError: cross-task access denied',
    'worker(outside) | record_candidate': 'CollaborationError: cross-task access denied',
    'worker(outside) | record_synthesis': 'CollaborationError: cross-task access denied',
    'worker(outside) | create_task': 'CollaborationError: only the conductor/operator may create assignments',
    'worker(outside) | abort_fresh_debate': 'CollaborationError: node is not a debate participant',
    'worker(outside) | abort_own_debate': 'CollaborationError: debate needs at least two task participants',
    'voice(owner) | get_task': 'ok',
    'voice(owner) | list_tasks': 'ok:len=1',
    'voice(owner) | read_messages': 'ok:len=1',
    'voice(owner) | read_messages(all)': 'ok:len=1',
    'voice(owner) | get_debate': 'CollaborationError: node is not a debate participant',
    'voice(owner) | list_debates': 'ok:len=0',
    'voice(owner) | update_task': 'ok',
    'voice(owner) | send_message(owner)': 'ok',
    'voice(owner) | send_message(outsider)': 'CollaborationError: cross-task recipient denied',
    'voice(owner) | post_turn': 'CollaborationError: node is not a debate participant',
    'voice(owner) | close_debate': 'CollaborationError: node is not a debate participant',
    'voice(owner) | open_debate(two owners)': "CollaborationError: role 'voice' may not request debate",
    'voice(owner) | open_debate(self+owner)': "CollaborationError: role 'voice' may not request debate",
    'voice(owner) | open_then_close_own': "CollaborationError: role 'voice' may not request debate",
    'voice(owner) | record_candidate': 'CollaborationError: only an assigned worker may publish a candidate',
    'voice(owner) | record_synthesis': 'CollaborationError: only conductor/operator may publish synthesis',
    'voice(owner) | create_task': 'CollaborationError: only the conductor/operator may create assignments',
    'voice(owner) | abort_fresh_debate': 'CollaborationError: node is not a debate participant',
    'voice(owner) | abort_own_debate': 'CollaborationError: only conductor/operator may abort a debate',
    'voice(outside) | get_task': 'CollaborationError: cross-task access denied',
    'voice(outside) | list_tasks': 'ok:len=0',
    'voice(outside) | read_messages': 'CollaborationError: cross-task access denied',
    'voice(outside) | read_messages(all)': 'CollaborationError: cross-task access denied',
    'voice(outside) | get_debate': 'CollaborationError: node is not a debate participant',
    'voice(outside) | list_debates': 'ok:len=0',
    'voice(outside) | update_task': 'CollaborationError: cross-task access denied',
    'voice(outside) | send_message(owner)': 'CollaborationError: cross-task access denied',
    'voice(outside) | send_message(outsider)': 'CollaborationError: cross-task access denied',
    'voice(outside) | post_turn': 'CollaborationError: node is not a debate participant',
    'voice(outside) | close_debate': 'CollaborationError: node is not a debate participant',
    'voice(outside) | open_debate(two owners)': "CollaborationError: role 'voice' may not request debate",
    'voice(outside) | open_debate(self+owner)': "CollaborationError: role 'voice' may not request debate",
    'voice(outside) | open_then_close_own': "CollaborationError: role 'voice' may not request debate",
    'voice(outside) | record_candidate': 'CollaborationError: cross-task access denied',
    'voice(outside) | record_synthesis': 'CollaborationError: cross-task access denied',
    'voice(outside) | create_task': 'CollaborationError: only the conductor/operator may create assignments',
    'voice(outside) | abort_fresh_debate': 'CollaborationError: node is not a debate participant',
    'voice(outside) | abort_own_debate': 'CollaborationError: debate needs at least two task participants',
    'malformed | get_task': "CollaborationError: unknown role 'hacker'",
    'malformed | list_tasks': 'ok:len=0',
    'malformed | read_messages': "CollaborationError: unknown role 'hacker'",
    'malformed | read_messages(all)': "CollaborationError: unknown role 'hacker'",
    'malformed | get_debate': "CollaborationError: unknown role 'hacker'",
    'malformed | list_debates': 'ok:len=0',
    'malformed | update_task': "CollaborationError: unknown role 'hacker'",
    'malformed | send_message(owner)': "CollaborationError: unknown role 'hacker'",
    'malformed | send_message(outsider)': "CollaborationError: unknown role 'hacker'",
    'malformed | post_turn': "CollaborationError: unknown role 'hacker'",
    'malformed | close_debate': "CollaborationError: unknown role 'hacker'",
    'malformed | open_debate(two owners)': "CollaborationError: role 'hacker' may not request debate",
    'malformed | open_debate(self+owner)': "CollaborationError: role 'hacker' may not request debate",
    'malformed | open_then_close_own': "CollaborationError: role 'hacker' may not request debate",
    'malformed | record_candidate': "CollaborationError: unknown role 'hacker'",
    'malformed | record_synthesis': "CollaborationError: unknown role 'hacker'",
    'malformed | create_task': "CollaborationError: unknown role 'hacker'",
    'malformed | abort_fresh_debate': "CollaborationError: unknown role 'hacker'",
    'malformed | abort_own_debate': 'CollaborationError: debate needs at least two task participants',
}


class TestTheWholeVerdictSurfaceIsPinned:
    """Four consecutive review rounds found the SAME defect: a deny statement was pinned by a
    test while the membership set or scope clause behind it was not, so widening it left the whole
    suite green — `_SCOPED_ROLES` (round 1), `_DIRECTING_ROLES` toward `gate` (round 2), four more
    constants (round 3), and then `_DIRECTING_ROLES` toward `voice`, the debate closer's identity
    and `authorize_open_debate`'s subset (round 4). One-off tests cannot end that: each round pins
    the widening the round before it found, and the next reviewer finds the next one.

    This table is the structural answer. Every role the policy admits, driven through every
    collaboration operation on a deterministic world, with the exact outcome recorded. No change to
    `_SCOPED_ROLES` or `_DIRECTING_ROLES` can pass it: such a change moves a cell, and a moved cell
    is a failure until someone regenerates this table on purpose and says why. (`ROLES` is pinned
    instead by `test_the_table_covers_every_role_the_policy_admits` and by
    `test_every_role_the_policy_admits_has_a_pinned_collaboration_reach` — adding a member moves no
    cell here unless the added name is one an identity already carries, and only `hacker` is.) It
    goes through
    `CollaborationService`; no policy method is called by the grader. Recorded as U352.

    What it does NOT catch, demonstrated at round 5 rather than assumed (U353) — the table pins ONE
    deterministic world, so a rule is invisible to it when the world never puts that rule's input in
    front of a policy call: a clause keyed on a task status (`COMPLETED`) this world never reaches,
    on a debate state (`CLOSED`) no policy call here is ever asked about, or on a message kind
    (`decision`) never written; an extra name admitted by `_unknown`; a role dimension this world
    holds at one value — `authorize_debate_turn` has no role clause at all and its participants here
    are workers only, so adding one would be unobserved (U355); and a clause an earlier gate answers
    first, so it is never asked — `authorize_send_message`'s sender clause (U343).
    Four such widenings were shown green against the whole suite at round 5 (2,331 passed, 1 skipped).
    Widen the world before trusting the table with a new rule shape."""

    def test_the_verdict_matrix_matches_the_pinned_table(self, tmp_path: pathlib.Path) -> None:
        observed = observed_matrix(tmp_path)
        assert set(observed) == set(GOLDEN_MATRIX), "an operation or identity was added or removed"
        drift = {k: (GOLDEN_MATRIX[k], observed[k]) for k in observed if observed[k] != GOLDEN_MATRIX[k]}
        assert drift == {}, "a policy verdict moved: " + "; ".join(
            f"{k}: {was!r} -> {now!r}" for k, (was, now) in sorted(drift.items()))

    def test_the_table_covers_every_role_the_policy_admits(self) -> None:
        """A role added to `ROLES` with no row here would be unpinned by construction — the
        round-3 hole, in the one place that would otherwise silently tolerate it."""
        assert {who.role for who in MATRIX_IDENTITIES.values()} >= set(ROLES)


if __name__ == "__main__":                                   # pragma: no cover - regeneration aid
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        for key, value in observed_matrix(pathlib.Path(tmp)).items():
            print(f"    {key!r}: {value!r},")
