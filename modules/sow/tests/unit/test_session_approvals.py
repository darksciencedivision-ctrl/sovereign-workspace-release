"""Phase 17D `.events` — the approval drawer is sourced from REAL SESSION EVENTS ONLY (finding F2).

The operator opened the shipped shell and saw three pending items — `ap-1` plan, `ap-2` protected
action, `ap-3` clarification — that no session had produced. They were the 16D `.approvals` emitter's
DETERMINISTIC DEMONSTRATION trio: a canned objective run through the real flow and two canned commands
run through the real broker, rebuilt identically on every fetch. Real authority path, canned content
(F2). This module replaces that producer: the drawer is rebuilt from the append-only log of events the
running session actually produced, and an empty session shows an EMPTY drawer.

What the tests below pin, in order of how badly each would hurt if it regressed:

  * **No events ⇒ an empty, honest drawer** (`badge_count:0`, `demo_items:false`) — never the trio.
  * **The shell does not get to say what an event MEANS.** A recorded utterance is re-routed through
    the REAL `ConductorVoiceBridge` router + the REAL `CommandBroker`; the recorded classification must
    match what the classifier says now, or the whole feed fails closed. So the least-trusted surface
    (the renderer/main process) cannot promote an ordinary sentence into a protected-action row, nor
    demote a protected verb into a clarification, nor invent a row with no utterance behind it.
  * **A recorded plan cannot assert its own approvability** — it is DERIVED from the recorded
    `gate@1.0` verdict through the same `build_plan_proposal` the 15E surface uses, and the record is
    re-validated against the frozen `gate@1.0` schema (invariant 16: a failed gate is not approvable,
    and there is no override path).
  * **The operator's decisions PERSIST** — a resolve is itself a recorded event, replayed through
    `ApprovalQueue.resolve`, so authority (invariant 1) and the no-override rule (invariant 16) are
    re-enforced on every rebuild and a decided item stops appearing in the drawer.
  * **Fail closed on anything malformed** — unknown kinds, bad shapes, a decision the authority would
    refuse: the feed is `sourced:false` with a reason, never a partial or fabricated drawer.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path

import pytest

from control_plane.ipc.envelope import canonical_payload
from control_plane.orchestration.session_approvals import (
    APPROVAL_DECISION_KEY_ENV,
    APPROVAL_DECISION_PRODUCER,
    SESSION_APPROVAL_EVENT_SCHEMA,
    SESSION_DECISION_FEED_SCHEMA,
    SESSION_DRAWER_FEED_SCHEMA,
    SessionEventError,
    approval_decision_key,
    build_session_drawer_feed,
    build_session_queue,
    canonical_decision_bytes,
    mint_decision_authenticity,
    read_session_events,
    route_session_decision,
    unavailable_session_feed,
)
from control_plane.policy import Identity
from tools.live.emit_approval_decision import main as decide_main
from tools.live.emit_approval_drawer import main as drawer_main

ROOT = Path(__file__).resolve().parents[2]

#: The session key every test runs with. In a real session the shell mints a random one per process
#: and hands it to both emitter processes; a fixed one here makes the stamps reproducible.
SESSION_KEY_HEX = "5a" * 32
OTHER_KEY = bytes.fromhex("a5" * 32)


@pytest.fixture(autouse=True)
def _session_approval_key(monkeypatch) -> None:
    """W-43. Every test runs WITH a session key, because every real session has one. A suite that ran
    without it would prove only the fail-closed path — and would silently stop exercising invariant 1
    and invariant 16 on replay, because an unauthenticated decision never reaches them. The no-key
    case is worth pinning too, so it has its own test that removes the key deliberately."""
    monkeypatch.setenv(APPROVAL_DECISION_KEY_ENV, SESSION_KEY_HEX)


# --------------------------------------------------------------------------------------
# event builders — the exact shapes the shell records (apps/desktop/approvals/session-events.js)
# --------------------------------------------------------------------------------------

def utterance_event(text, *, source="voice", confidence=0.95, classified_as="proposed_action",
                    event_id="ev-1"):
    return {
        "schema": SESSION_APPROVAL_EVENT_SCHEMA,
        "event_id": event_id,
        "at": "2026-07-31T00:00:00+00:00",
        "kind": "utterance",
        "utterance": {"text": text, "source": source, "confidence": confidence,
                      "classified_as": classified_as},
        "provenance": {"channel": "voice:capture", "feed_schema": "conductor_voice_feed@1.0"},
    }


def gate_record(verdict="PASS", *, kind="plan"):
    """A `gate@1.0` record shaped exactly as `GateEngine.evaluate` emits one."""
    return {
        "gate_id": "g-plan-1", "kind": kind, "criteria": ["plan_has_tasks"], "verdict": verdict,
        "evidence": ["mem://decision/1"], "debate_ref": None, "decided_by": "gate_engine",
        "reasons": ["plan_has_tasks: 2 task(s)"], "task_id": None, "schema": "gate@1.0",
    }


def plan_event(*, verdict="PASS", plan_blocked=False, event_id="ev-2", extra=None):
    ev = {
        "schema": SESSION_APPROVAL_EVENT_SCHEMA,
        "event_id": event_id,
        "at": "2026-07-31T00:00:10+00:00",
        "kind": "plan",
        "plan": {
            "objective": "Summarize the roster",
            "tasks": [{"task_id": "t1", "capability": "reasoning", "description": "read", "deps": []},
                      {"task_id": "t2", "capability": "coding", "description": "write", "deps": ["t1"]}],
            "refused": [],
            "plan_gate": gate_record(verdict),
            "plan_blocked": plan_blocked,
        },
        "provenance": {"channel": "conductor:dispatch", "feed_schema": "conductor_dispatch_feed@1.0"},
    }
    if extra:
        ev["plan"].update(extra)
    return ev


def hand_built_decision_event(item_id, decision, *, event_id="ev-9", reason="",
                              operator_role="operator"):
    """A decision event assembled BY HAND — exactly what this file's `decision_event` helper produced
    before W-43, kept verbatim so the forgery the old U206 test used is still the forgery under test.
    Well-formed, names a real row, claims the operator role, carries NO producer authenticity."""
    return {
        "schema": SESSION_APPROVAL_EVENT_SCHEMA,
        "event_id": event_id,
        "at": "2026-07-31T00:01:00+00:00",
        "kind": "decision",
        "decision": {"item_id": item_id, "decision": decision, "reason": reason,
                     "operator_role": operator_role},
        "provenance": {"channel": "approvals:decide"},
    }


def decision_event(item_id, decision, *, event_id="ev-9", reason="", operator_role="operator",
                   key=None):
    """A decision event carrying a GENUINE producer authenticity stamp (W-43).

    Assembled here rather than driven through `route_session_decision` on purpose: several tests need
    a decision the real producer would REFUSE to mint at all — an unknown item, a worker role — and
    those are exactly the cases that must still reach the authority. Stamping them proves the
    defence-in-depth claim rather than shadowing it: even a holder of the session key does not get to
    resolve as a non-operator or decide a row that does not exist. `route_session_decision`'s own
    minting is exercised end-to-end by the acceptance tests in section 5b."""
    ev = hand_built_decision_event(item_id, decision, event_id=event_id, reason=reason,
                                   operator_role=operator_role)
    ev["decision"]["producer"] = APPROVAL_DECISION_PRODUCER
    ev["decision"]["authenticity"] = mint_decision_authenticity(
        ev["decision"], key=key if key is not None else approval_decision_key())
    return ev


PROTECTED_TEXT = "spawn a gpt-5.5 worker node"      # `spawn` is a PROTECTED verb → broker queues it
CHAT_TEXT = "what is the current build status"      # ordinary conversation → no drawer row at all


# --------------------------------------------------------------------------------------
# 1. an empty session shows an EMPTY drawer — the demo trio is gone from the product path
# --------------------------------------------------------------------------------------

def test_no_events_yields_an_empty_honest_drawer() -> None:
    feed = build_session_drawer_feed([])
    assert feed["schema"] == SESSION_DRAWER_FEED_SCHEMA
    assert feed["sourced"] is True            # sourcing SUCCEEDED; there was simply nothing to show
    assert feed["source"] == "session_events"
    assert feed["badge_count"] == 0
    assert feed["drawer"]["pending"] == []
    assert feed["event_count"] == 0
    assert feed["demo_items"] is False        # the F2 receipt: no canned rows can be here


def test_the_demo_trio_is_not_reachable_from_the_product_source() -> None:
    """F2 in one assertion: the shipped source has no path that invents ap-1/ap-2/ap-3. The canned
    objective + canned commands now live under tests/ (test-only), so a product import cannot reach
    them and an empty session cannot produce three rows."""
    src = (ROOT / "control_plane" / "orchestration" / "session_approvals.py").read_text(encoding="utf-8")
    assert "LiveGovernedFlow" not in src          # no canned objective run behind the operator's back
    assert "ProposedCommand(" not in src          # no canned commands minted here
    assert not (ROOT / "control_plane" / "orchestration" / "approval_feed.py").exists()


# --------------------------------------------------------------------------------------
# 2. a REAL utterance becomes exactly the row the REAL classifier says it is
# --------------------------------------------------------------------------------------

def test_a_protected_utterance_becomes_a_protected_action_row_with_the_brokers_ref() -> None:
    feed = build_session_drawer_feed([utterance_event(PROTECTED_TEXT)])
    assert feed["sourced"] is True and feed["badge_count"] == 1
    (row,) = feed["drawer"]["pending"]
    assert row["kind"] == "protected_action"
    assert row["item_id"] == "ap-1"
    assert row["origin"] == "voice"
    assert row["approvable"] is True
    assert row["detail"]["verb"] == "spawn"
    assert row["detail"]["category"] == "protected"
    # the broker's own pending_id — the decision routes back to the SAME broker classification
    assert isinstance(row["ref"], str) and row["ref"]
    # provenance survives onto the row the operator sees (invariant 11)
    assert row["detail"]["event_id"] == "ev-1"
    assert row["detail"]["channel"] == "voice:capture"


def test_a_low_confidence_utterance_becomes_a_non_approvable_clarification() -> None:
    feed = build_session_drawer_feed([
        utterance_event("uh do the roster thing", confidence=0.2, classified_as="clarify")])
    (row,) = feed["drawer"]["pending"]
    assert row["kind"] == "clarification"
    assert row["approvable"] is False          # a question is never approvable into execution
    assert row["ref"] is None


def test_events_keep_their_order_and_ids_are_stable_as_the_log_grows() -> None:
    """Item ids are positional, and the decide path resolves by id — so an appended event must never
    renumber an item the operator is looking at."""
    first = build_session_drawer_feed([utterance_event(PROTECTED_TEXT)])
    second = build_session_drawer_feed([
        utterance_event(PROTECTED_TEXT),
        utterance_event("uh do the roster thing", confidence=0.2, classified_as="clarify",
                        event_id="ev-2")])
    assert first["drawer"]["pending"][0]["item_id"] == "ap-1"
    assert [r["item_id"] for r in second["drawer"]["pending"]] == ["ap-1", "ap-2"]
    assert second["drawer"]["pending"][0]["detail"]["event_id"] == "ev-1"


# --------------------------------------------------------------------------------------
# 3. the shell cannot say what an event MEANS — the real classifier re-decides it
# --------------------------------------------------------------------------------------

def test_an_ordinary_sentence_cannot_be_recorded_as_a_protected_action() -> None:
    """The forgery that matters: main.js (the least-trusted surface) claiming a chat sentence was a
    protected action. The re-route says CHAT, no drawer item exists, and the feed fails closed."""
    with pytest.raises(SessionEventError) as exc:
        build_session_queue([utterance_event(CHAT_TEXT, classified_as="proposed_action")])
    assert "chat" in str(exc.value).lower()
    feed = build_session_drawer_feed([utterance_event(CHAT_TEXT, classified_as="proposed_action")])
    assert feed["sourced"] is False and feed["badge_count"] == 0 and feed["drawer"]["pending"] == []


def test_a_protected_utterance_cannot_be_downgraded_to_a_clarification() -> None:
    """The other direction: a protected verb recorded as a mere question would show the operator a
    dismissible row for something the broker actually queued for approval."""
    with pytest.raises(SessionEventError):
        build_session_queue([utterance_event(PROTECTED_TEXT, classified_as="clarify")])


def test_a_typed_protected_utterance_is_gated_exactly_like_a_spoken_one() -> None:
    feed = build_session_drawer_feed([utterance_event(PROTECTED_TEXT, source="typed",
                                                     confidence=None)])
    (row,) = feed["drawer"]["pending"]
    assert row["kind"] == "protected_action" and row["origin"] == "typed"


def test_an_utterance_with_no_text_is_refused() -> None:
    with pytest.raises(SessionEventError):
        build_session_queue([utterance_event("   ", classified_as="proposed_action")])


def test_an_unknown_event_kind_fails_closed() -> None:
    bad = {"schema": SESSION_APPROVAL_EVENT_SCHEMA, "event_id": "ev-x", "kind": "gate_promotion_lol"}
    with pytest.raises(SessionEventError):
        build_session_queue([bad])
    assert build_session_drawer_feed([bad])["sourced"] is False


def test_an_event_carrying_a_drifted_schema_is_refused() -> None:
    ev = utterance_event(PROTECTED_TEXT)
    ev["schema"] = "session_approval_event@2.0"
    with pytest.raises(SessionEventError):
        build_session_queue([ev])


# --------------------------------------------------------------------------------------
# 4. a plan row's approvability is DERIVED from its real gate verdict (invariant 16)
# --------------------------------------------------------------------------------------

def test_a_passing_plan_is_approvable_and_carries_its_verdict() -> None:
    feed = build_session_drawer_feed([plan_event(verdict="PASS")])
    (row,) = feed["drawer"]["pending"]
    assert row["kind"] == "plan" and row["approvable"] is True
    assert row["detail"]["plan_gate_verdict"] == "PASS"
    assert row["detail"]["task_count"] == 2


def test_a_gate_failed_plan_is_surfaced_but_not_approvable() -> None:
    feed = build_session_drawer_feed([plan_event(verdict="FAIL", plan_blocked=True)])
    (row,) = feed["drawer"]["pending"]
    assert row["kind"] == "plan"
    assert row["approvable"] is False          # invariant 16 — no override path
    assert "BLOCKED" in row["summary"]


def test_a_plan_event_cannot_assert_its_own_approvability() -> None:
    """A recorded `approvable:true` beside a FAIL verdict must lose to the verdict."""
    feed = build_session_drawer_feed([plan_event(verdict="FAIL", plan_blocked=True,
                                                 extra={"approvable": True})])
    assert feed["drawer"]["pending"][0]["approvable"] is False


def test_a_plan_whose_gate_record_is_not_a_real_gate_record_is_refused() -> None:
    """The recorded verdict is re-validated against the frozen `gate@1.0` schema, so a hand-rolled
    `{"verdict": "PASS"}` never reaches the operator's drawer as an approvable plan."""
    with pytest.raises(SessionEventError):
        build_session_queue([plan_event(extra={"plan_gate": {"verdict": "PASS"}})])
    with pytest.raises(SessionEventError):
        build_session_queue([plan_event(extra={"plan_gate": gate_record("PASS", kind="local")})])


def test_a_plan_gate_record_not_decided_by_the_gate_engine_is_refused() -> None:
    rec = gate_record("PASS")
    rec["decided_by"] = "conductor"
    with pytest.raises(SessionEventError):
        build_session_queue([plan_event(extra={"plan_gate": rec})])


# --------------------------------------------------------------------------------------
# 5. the operator's decision persists — and is re-governed on every replay
# --------------------------------------------------------------------------------------

def test_a_recorded_decision_removes_the_item_from_the_next_drawer() -> None:
    events = [utterance_event(PROTECTED_TEXT), decision_event("ap-1", "reject", reason="not now")]
    feed = build_session_drawer_feed(events)
    assert feed["sourced"] is True
    assert feed["badge_count"] == 0            # decided ⇒ no longer pending
    assert feed["decision_count"] == 1


def test_a_forged_approve_of_a_NON_APPROVABLE_item_fails_closed_on_replay() -> None:
    """Invariant 16 is enforced on REPLAY too: an `approve` of a clarification recorded into the log
    (i.e. someone editing the file) is refused by the authority, and the feed fails closed rather than
    quietly dropping the row or honoring it. NOTE what this does NOT prove — see the test below."""
    events = [utterance_event("uh do the roster thing", confidence=0.2, classified_as="clarify"),
              decision_event("ap-1", "approve")]
    # Authentically stamped since W-43, and the match is what proves it: an authenticity refusal
    # would satisfy `raises(SessionEventError)` without invariant 16 ever being consulted.
    with pytest.raises(SessionEventError, match="invariant 16"):
        build_session_queue(events)
    assert build_session_drawer_feed(events)["sourced"] is False


def test_a_forged_decision_CANNOT_dispose_of_an_approvable_row() -> None:
    """W-43, the INVERSION of the test this file used to carry (U206).

    Until W-43 this assertion read `CAN_dispose_..._and_that_is_recorded_as_owed`: a hand-built
    `decision` event over an APPROVABLE row was honored, so anything able to write the log could make
    a pending approval disappear from the operator's drawer. The repo memorialized that as expected
    behaviour, which is why inverting THIS test is the unit's acceptance criterion and not a
    by-product of it.

    The forgery below is byte-for-byte what the old helper produced. It is well-formed, it names a
    real approvable row, and it claims the operator role — everything the pre-W-43 checks asked for.
    It carries no producer authenticity stamp, so it is not authoritative, and the feed fails closed
    rather than honoring it."""
    forged = hand_built_decision_event("ap-1", "approve", operator_role="operator")
    feed = build_session_drawer_feed([utterance_event(PROTECTED_TEXT), forged])
    assert feed["sourced"] is False
    assert "authenticity" in feed["reason"]
    # and the row the forgery aimed at is untouched: still pending, still counted (acceptance 7)
    honest = build_session_drawer_feed([utterance_event(PROTECTED_TEXT)])
    assert honest["badge_count"] == 1
    assert feed["badge_count"] == 0 and feed["drawer"]["pending"] == []   # fail-closed, never partial


def test_a_non_operator_decision_in_the_log_is_refused() -> None:
    """Invariant 1 on replay. The event is AUTHENTICALLY STAMPED, so this test still reaches the
    guard it names: W-43's authenticity check sits in front of the authority, and an unstamped event
    would be refused before `ApprovalQueue.resolve` ever saw the role. Holding the session key does
    not widen authority — the refusal below is the authority's, and the message proves it."""
    events = [utterance_event(PROTECTED_TEXT), decision_event("ap-1", "approve", operator_role="worker")]
    with pytest.raises(SessionEventError, match="invariant 1"):
        build_session_queue(events)


def test_a_decision_for_an_unknown_item_is_refused() -> None:
    """Also authentically stamped, for the same reason: the guard under test is the queue's unknown-
    item refusal, and the assertion names it so an authenticity refusal cannot pass for it."""
    with pytest.raises(SessionEventError, match="no approval item"):
        build_session_queue([utterance_event(PROTECTED_TEXT), decision_event("ap-77", "reject")])


# --------------------------------------------------------------------------------------
# 5b. W-43 — PRODUCER AUTHENTICITY: only a decision the trusted producer minted may dispose (U206)
#
# The property: a forged or manually constructed `decision` event must never dispose an approvable
# row. The mechanism: the producer stamps the decision record with an HMAC over its own canonical
# bytes under a per-session key, and the drawer builder — the ONE boundary that decides whether a
# recorded decision affects approval state — verifies it before the authority is consulted.
#
# What is proven here is the BINDING. What is not proven here, and must not be read as proven, is
# the confidentiality of the key: these tests hold it, as the shell's emitter processes do.
# --------------------------------------------------------------------------------------

def test_a_producer_minted_decision_disposes_the_row_it_names() -> None:
    """Acceptance 1, driven END TO END through the real producer rather than through this file's
    stamping helper — the mint and the verify must agree across the actual seam."""
    events = [utterance_event(PROTECTED_TEXT)]
    out = route_session_decision(events=events, item_id="ap-1", decision="reject", reason="not now")
    assert out["resolved"] is True
    feed = build_session_drawer_feed([*events, out["decision_event"]])
    assert feed["sourced"] is True
    assert feed["badge_count"] == 0 and feed["decision_count"] == 1


def test_a_decision_event_with_its_authenticity_removed_is_not_authoritative() -> None:
    """Acceptance 3. Missing is refused, not treated as 'nothing to check'."""
    events = [utterance_event(PROTECTED_TEXT)]
    ev = route_session_decision(events=events, item_id="ap-1", decision="reject")["decision_event"]
    del ev["decision"]["authenticity"]
    assert build_session_drawer_feed([*events, ev])["sourced"] is False


def test_a_self_asserted_authentication_flag_proves_nothing() -> None:
    """The stamp must not be another caller-supplied field. A forger writing the most confident
    possible claim about itself gets exactly as far as one writing nothing."""
    forged = hand_built_decision_event("ap-1", "approve")
    forged["decision"]["producer"] = APPROVAL_DECISION_PRODUCER
    forged["decision"]["producer_authenticated"] = True
    forged["decision"]["authenticity"] = "authentic"
    assert build_session_drawer_feed([utterance_event(PROTECTED_TEXT), forged])["sourced"] is False


def test_changing_the_decision_after_minting_breaks_the_stamp() -> None:
    """Acceptance 4 — WHAT was decided is inside the signature."""
    events = [utterance_event(PROTECTED_TEXT)]
    ev = route_session_decision(events=events, item_id="ap-1", decision="reject")["decision_event"]
    assert build_session_drawer_feed([*events, ev])["sourced"] is True     # genuine, before tampering
    ev["decision"]["decision"] = "approve"
    assert build_session_drawer_feed([*events, ev])["sourced"] is False


def test_changing_the_target_approval_after_minting_breaks_the_stamp() -> None:
    """Acceptance 5 — WHICH approval was decided is inside the signature. Two pending rows, so the
    rewrite names a row that really exists: a refusal caused by an unknown item would prove nothing."""
    events = [utterance_event(PROTECTED_TEXT), utterance_event(PROTECTED_TEXT, event_id="ev-1b")]
    assert build_session_drawer_feed(events)["badge_count"] == 2
    ev = route_session_decision(events=events, item_id="ap-1", decision="reject")["decision_event"]
    ev["decision"]["item_id"] = "ap-2"
    assert build_session_drawer_feed([*events, ev])["sourced"] is False


def test_a_stamp_transplanted_from_one_decision_to_another_is_refused() -> None:
    """Acceptance 6, and the property mutation P40 exists to catch: authenticating the decision VALUE
    without its target identity would let a stamp minted for `ap-1` dispose of `ap-2`. Both records
    below are genuinely minted, and only the stamp is moved — so nothing about them is malformed."""
    events = [utterance_event(PROTECTED_TEXT), utterance_event(PROTECTED_TEXT, event_id="ev-1b")]
    a = route_session_decision(events=events, item_id="ap-1", decision="reject")["decision_event"]
    b = route_session_decision(events=events, item_id="ap-2", decision="reject")["decision_event"]
    assert a["decision"]["authenticity"] != b["decision"]["authenticity"]
    b["decision"]["authenticity"] = a["decision"]["authenticity"]
    assert build_session_drawer_feed([*events, b])["sourced"] is False


def test_rewriting_the_producer_after_minting_breaks_the_stamp() -> None:
    """WHICH producer issued it is inside the signature too, so the pinned producer name is not a
    string a log writer can supply to satisfy the verifier."""
    events = [utterance_event(PROTECTED_TEXT)]
    ev = route_session_decision(events=events, item_id="ap-1", decision="reject")["decision_event"]
    ev["decision"]["producer"] = "some.other.producer@9.9"
    assert build_session_drawer_feed([*events, ev])["sourced"] is False


def test_a_stamp_minted_under_a_different_key_is_refused() -> None:
    """The key is what is load-bearing, not the shape of the field. A forger who reproduces the
    canonicalization exactly but does not hold the session key still fails."""
    forged = decision_event("ap-1", "approve", key=OTHER_KEY)
    assert build_session_drawer_feed([utterance_event(PROTECTED_TEXT), forged])["sourced"] is False


def test_the_stamp_is_domain_separated_from_the_ipc_envelope_hmac() -> None:
    """W-41 signs canonical envelope bytes with the same primitive. Without the domain tag, an HMAC
    computed over the same canonical object would be a valid approval stamp — so an authenticated IPC
    envelope could be transplanted into this position. The tag is what makes that impossible, and
    this test fails if it is ever dropped."""
    forged = hand_built_decision_event("ap-1", "approve")
    forged["decision"]["producer"] = APPROVAL_DECISION_PRODUCER
    body = dict(forged["decision"])
    undomained = hmac.new(approval_decision_key(), canonical_payload(body), hashlib.sha256).hexdigest()
    forged["decision"]["authenticity"] = undomained
    assert build_session_drawer_feed([utterance_event(PROTECTED_TEXT), forged])["sourced"] is False
    # and the domained bytes really are the other thing — the prefix, then the same canonical object
    assert canonical_decision_bytes(body) == b"SOW_APPROVAL_DECISION_V1\x00" + canonical_payload(body)


def test_non_decision_events_remain_readable_and_unaffected() -> None:
    """Acceptance 8. W-43 gates decisions; it must not have made the rest of the log unreadable —
    a log with no decision in it is authenticated by nothing and must still rebuild exactly."""
    events = [utterance_event(PROTECTED_TEXT), plan_event(), utterance_event(
        "uh do the roster thing", confidence=0.2, classified_as="clarify", event_id="ev-3")]
    feed = build_session_drawer_feed(events)
    assert feed["sourced"] is True
    assert feed["badge_count"] == 3 and feed["decision_count"] == 0
    assert feed["kinds_present"] == ["clarification", "plan", "protected_action"]


def test_with_no_session_key_the_authority_does_not_claim_to_have_decided(monkeypatch) -> None:
    """The fail-closed direction, both halves. With no key the producer cannot mint a decision the
    drawer would honor, so it reports UNAVAILABLE rather than handing back a resolve that will not
    persist — and a previously genuine decision stops being authoritative rather than being trusted
    because it once was."""
    events = [utterance_event(PROTECTED_TEXT)]
    ev = route_session_decision(events=events, item_id="ap-1", decision="reject")["decision_event"]
    monkeypatch.delenv(APPROVAL_DECISION_KEY_ENV)
    out = route_session_decision(events=events, item_id="ap-1", decision="reject")
    assert out["resolved"] is False and out["refused"] is False and out["unavailable"] is True
    assert "decision_event" not in out
    assert build_session_drawer_feed([*events, ev])["sourced"] is False


def test_a_hostile_stamp_value_is_refused_and_not_an_exception_of_the_wrong_type() -> None:
    """The stamp arrives from a file a forger writes, so its VALUE is attacker-chosen. A non-ASCII
    stamp made `hmac.compare_digest` raise TypeError out of `build_session_queue` — fail-closed at
    the feed, but the wrong exception escaping the authority, and one a caller catching
    SessionEventError would not handle. Every hostile value is a plain refusal."""
    for hostile in (" " * 64, "ü" * 64, "\x00" * 64, "not-hex-at-all"):
        forged = hand_built_decision_event("ap-1", "approve")
        forged["decision"]["producer"] = APPROVAL_DECISION_PRODUCER
        forged["decision"]["authenticity"] = hostile
        with pytest.raises(SessionEventError, match="authenticity"):
            build_session_queue([utterance_event(PROTECTED_TEXT), forged])


def test_a_short_or_malformed_key_is_no_key_at_all() -> None:
    """A key is fail-closed on its own shape: a truncated or non-hex value is an absence, never a
    weaker key that still authenticates something."""
    for bad in ("", "  ", "not-hex", "ab", "5a" * 31):
        with pytest.MonkeyPatch.context() as mp:
            mp.setenv(APPROVAL_DECISION_KEY_ENV, bad)
            assert approval_decision_key() is None


# --------------------------------------------------------------------------------------
# 6. the decide path — the shell forwards, the Python authority decides
# --------------------------------------------------------------------------------------

def test_route_session_decision_resolves_a_protected_action() -> None:
    events = [utterance_event(PROTECTED_TEXT)]
    out = route_session_decision(events=events, item_id="ap-1", decision="reject", reason="no")
    assert out["schema"] == SESSION_DECISION_FEED_SCHEMA
    assert out["resolved"] is True and out["refused"] is False
    assert out["self_authorized"] is False
    assert out["item"]["decision"] == "reject" and out["item"]["resolved"] is True
    # the event the shell must append so the decision persists — minted HERE, by the authority
    ev = out["decision_event"]
    assert ev["kind"] == "decision"
    minted = dict(ev["decision"])
    stamp = minted.pop("authenticity")
    assert minted == {"item_id": "ap-1", "decision": "reject", "reason": "no",
                      "operator_role": "operator", "producer": APPROVAL_DECISION_PRODUCER}
    # W-43: the stamp is a real HMAC over those exact bytes, not a flag the record asserts about
    # itself. Recomputed here rather than compared to a literal, so a changed canonicalization is a
    # failure of this test and not a silently re-baselined constant.
    assert stamp == mint_decision_authenticity(minted, key=approval_decision_key())


def test_route_session_decision_refuses_an_approve_of_a_clarification() -> None:
    events = [utterance_event("uh do the roster thing", confidence=0.2, classified_as="clarify")]
    out = route_session_decision(events=events, item_id="ap-1", decision="approve")
    assert out["resolved"] is False and out["refused"] is True
    assert "invariant 16" in out["reason"] or "not approvable" in out["reason"]
    assert "decision_event" not in out          # nothing to persist — the decision did not happen
    assert out["self_authorized"] is False


def test_route_session_decision_refuses_a_non_operator() -> None:
    out = route_session_decision(events=[utterance_event(PROTECTED_TEXT)], item_id="ap-1",
                                 decision="reject",
                                 operator=Identity(node_id="w1", role="worker", project_id="proj"))
    assert out["resolved"] is False and out["refused"] is True


def test_route_session_decision_on_a_broken_log_is_unavailable_not_a_resolve() -> None:
    out = route_session_decision(events=[utterance_event(CHAT_TEXT, classified_as="proposed_action")],
                                 item_id="ap-1", decision="reject")
    assert out["resolved"] is False and out.get("unavailable") is True
    assert out["self_authorized"] is False
    # W-43 added a SECOND unavailable branch (no session key) with the same shape, and it is checked
    # first. Name the reason so this test cannot start passing because of the other one.
    assert "SessionEventError" in out["reason"]


def test_an_already_decided_item_cannot_be_decided_twice() -> None:
    events = [utterance_event(PROTECTED_TEXT), decision_event("ap-1", "reject")]
    out = route_session_decision(events=events, item_id="ap-1", decision="approve")
    assert out["resolved"] is False and out["refused"] is True


# --------------------------------------------------------------------------------------
# 7. reading the log the shell writes (JSONL, append-only, fail-closed)
# --------------------------------------------------------------------------------------

def test_read_session_events_reads_jsonl_and_skips_nothing_silently(tmp_path) -> None:
    p = tmp_path / "session-events.jsonl"
    p.write_text(json.dumps(utterance_event(PROTECTED_TEXT)) + "\n"
                 + json.dumps(plan_event()) + "\n", encoding="utf-8")
    events = read_session_events(p)
    assert [e["kind"] for e in events] == ["utterance", "plan"]


def test_read_session_events_on_a_missing_log_is_an_empty_session(tmp_path) -> None:
    assert read_session_events(tmp_path / "nope.jsonl") == []


def test_read_session_events_refuses_a_corrupt_line(tmp_path) -> None:
    p = tmp_path / "session-events.jsonl"
    p.write_text(json.dumps(utterance_event(PROTECTED_TEXT)) + "\n{not json\n", encoding="utf-8")
    with pytest.raises(SessionEventError):
        read_session_events(p)


# --------------------------------------------------------------------------------------
# 8. the emitters the shell actually runs
# --------------------------------------------------------------------------------------

def _write_log(tmp_path, events) -> Path:
    p = tmp_path / "session-events.jsonl"
    p.write_text("".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")
    return p


def test_drawer_emitter_with_no_log_prints_an_empty_drawer(tmp_path, capsys) -> None:
    """First launch: no session has produced anything, so the operator sees an empty drawer — the
    exact case that used to print three canned rows."""
    assert drawer_main(["--emit-approval-drawer"]) == 0
    feed = json.loads(capsys.readouterr().out)
    assert feed["schema"] == SESSION_DRAWER_FEED_SCHEMA
    assert feed["sourced"] is True and feed["badge_count"] == 0
    assert feed["drawer"]["pending"] == []


def test_drawer_emitter_folds_the_recorded_log(tmp_path, capsys) -> None:
    log = _write_log(tmp_path, [utterance_event(PROTECTED_TEXT), plan_event()])
    assert drawer_main(["--emit-approval-drawer", "--events", str(log)]) == 0
    feed = json.loads(capsys.readouterr().out)
    assert feed["badge_count"] == 2
    assert feed["kinds_present"] == ["plan", "protected_action"]
    assert feed["event_count"] == 2


def test_drawer_emitter_fails_closed_on_a_corrupt_log(tmp_path, capsys) -> None:
    p = tmp_path / "session-events.jsonl"
    p.write_text("{not json\n", encoding="utf-8")
    assert drawer_main(["--emit-approval-drawer", "--events", str(p)]) == 0
    feed = json.loads(capsys.readouterr().out)
    assert feed["sourced"] is False and feed["drawer"]["pending"] == []


def test_decision_emitter_resolves_and_hands_back_the_event_to_append(tmp_path, capsys) -> None:
    log = _write_log(tmp_path, [utterance_event(PROTECTED_TEXT)])
    assert decide_main(["--emit-approval-decision", "--item", "ap-1", "--decision", "reject",
                        "--reason", "later", "--events", str(log)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["resolved"] is True and out["self_authorized"] is False
    assert out["decision_event"]["decision"]["decision"] == "reject"


def test_decision_emitter_refuses_an_approve_of_a_clarification(tmp_path, capsys) -> None:
    log = _write_log(tmp_path, [utterance_event("uh do the roster thing", confidence=0.2,
                                                classified_as="clarify")])
    assert decide_main(["--emit-approval-decision", "--item", "ap-1", "--decision", "approve",
                        "--events", str(log)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["resolved"] is False and out["refused"] is True


def test_emitters_refuse_any_other_invocation(capsys) -> None:
    assert drawer_main([]) == 2
    assert decide_main([]) == 2


def test_unavailable_feed_shape_is_an_empty_drawer_with_a_reason() -> None:
    feed = unavailable_session_feed("boom")
    assert feed["sourced"] is False and feed["reason"] == "boom"
    assert feed["drawer"]["pending"] == [] and feed["badge_count"] == 0
    assert feed["demo_items"] is False
