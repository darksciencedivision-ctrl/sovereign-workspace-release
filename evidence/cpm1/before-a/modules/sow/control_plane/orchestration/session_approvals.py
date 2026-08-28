"""The operator's approval drawer, rebuilt from REAL SESSION EVENTS — Phase 17D `.events` (OP-11 §16).

**The defect this replaces (operator finding F2, 2026-07-25).** The operator opened the shipped shell
and found three pending approvals waiting for them: a plan, a protected action, a clarification. No
session had produced any of them. They were Phase 16D's DETERMINISTIC DEMONSTRATION trio — a canned
objective run through the real flow, two canned commands run through the real broker — rebuilt
identically on every fetch. The authority path was real; the content was canned. A queue that shows
work nobody asked for is worse than an empty one: it teaches the operator to dismiss their own
drawer.

This module is the replacement producer. The drawer is a FOLD over the append-only log of events the
running session actually produced (`apps/desktop/approvals/session-events.js` writes it). **An empty
session shows an empty drawer.** There is no path here that invents a row.

WHICH PRODUCERS ARE WIRED TODAY, exactly (invariant 3 — the directive names three; the shell has
one). The `voice:capture` path records: a protected/destructive verb the CommandBroker queued, and a
clarification the bridge would not route. NOT wired: a protected verb TYPED at the conductor pane
(those keystrokes go straight to the ConPTY and never reach the broker — U149), and a gate promotion
from a governed dispatch (`recordDispatchPlan` exists and is covered, but its only caller would be an
operator-driven dispatch, which lands with the conductor conversation, 17E/OP-8 §13; the launch-time
demonstration dispatch is deliberately not recorded — it would be finding F2 one layer down). The
`plan` event kind below is therefore built and tested ahead of its producer.

WHY THE LOG IS NOT TRUSTED, AND WHAT THAT BUYS. The log is written by the shell — the least-trusted
surface (invariant 29). So a recorded event is treated as a CLAIM about what happened, and everything
that decides how it appears to the operator is re-derived here, by the same authorities that decided
it the first time:

  * an `utterance` event is re-routed through the REAL `ConductorVoiceBridge` router over the REAL
    `CommandBroker` (invariant 30 — this module owns no classifier). The recorded classification must
    match what the classifier says now, or the whole feed fails closed. So the shell cannot promote an
    ordinary sentence into a protected-action row, cannot demote a protected verb into a dismissible
    question, and cannot mint a row with no utterance behind it. The chat sink handed to that router
    REFUSES delivery: re-deriving a recorded event must never speak to the conductor;
  * a `plan` event's approvability is DERIVED from its recorded `gate@1.0` verdict through the same
    `propose_plan_for_approval`/`build_plan_proposal` the 15E surface uses, and the record must
    validate against the frozen `gate@1.0` schema and carry `decided_by: "gate_engine"` — so a
    hand-rolled `{"verdict": "PASS"}` is refused, and an approvable plan at least has the shape of a
    rendered verdict (invariant 16 then governs what may be done with it: no override);
  * a `decision` event is replayed through `ApprovalQueue.resolve`, so operator-only authority
    (invariant 1) and the no-approve-of-a-failed-gate rule (invariant 16) are re-enforced on EVERY
    rebuild. That is also what makes the operator's decisions PERSIST across fetches — the gap 16D
    recorded as owed — without any component keeping a mutable queue alive.

PRODUCER AUTHENTICITY (W-43, closes the DISPOSE half of the residual below). A `decision` event is
authoritative only if it carries a stamp minted by THIS module's decision producer. The stamp is an
HMAC over the whole `decision` object minus the stamp field itself, under a per-session key the
producer and the drawer builder share and a log writer does not hold. So a `decision` event that was
assembled by hand — however well-formed, however plainly it names an approvable row and claims the
operator role — is not authoritative and cannot dispose of anything. See `decision_is_authentic`.

HONEST RESIDUAL (invariant 3), stated at its full width because two reviews measured it. Re-derivation
binds the drawer to the real classifiers; it is NOT proof that a recorded event was emitted by a
governed producer. Concretely, a shell process (or anything that can write the log file) can still:
  * INJECT a row, by writing a *plausible* utterance ("spawn a worker") that the real classifier does
    accept, or a FULLY-FORMED `gate@1.0` record carrying `decided_by: "gate_engine"` — the checks
    above refuse malformed forgeries, not well-made ones (`U205`). STILL OPEN: W-43 authenticates the
    DECISION producer, not the utterance or plan producers, and does not claim to;
  * DISPOSE of a row, by writing a `decision` event (`U206`). CLOSED at this boundary by the producer
    authenticity stamp above — and closed exactly as far as the key's confidentiality reaches: an
    attacker who can read the shell process's memory or its children's environment holds the key and
    is inside the supervisor's containment boundary already, which is a different problem than a
    file anyone can append to.
This is a narrower surface than the trio it replaces (every row now corresponds to something a real
classifier accepts, and every decision is re-governed), and it is bounded by the integrity of the
shell process and its per-run file, which the supervisor already owns.

PURE + FAIL-CLOSED: no I/O beyond reading the log the caller names, no model call, no credential, no
network, no MCP server. Any malformed event, any classification mismatch, any refused replay ⇒ the
UNAVAILABLE feed (`sourced:false`, the reason named, an EMPTY drawer) — never a partial drawer and
never a fabricated row.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import jsonschema

from control_plane.ipc.envelope import canonical_payload
from control_plane.orchestration.operator_surface import (
    ApprovalError,
    ApprovalQueue,
    mirror_broker_outcome,
    propose_plan_for_approval,
)
from control_plane.policy import Identity
from voice_bridge.command_broker import CommandBroker
from voice_bridge.conductor_voice import (
    ConductorInputKind,
    ConductorVoiceBridge,
)

#: Pinned on every recorded event so a drifted writer is refused rather than half-understood.
SESSION_APPROVAL_EVENT_SCHEMA = "session_approval_event@1.0"

#: The shell contract. Bumped from `@1.0` deliberately: `@1.0` was the demo-trio feed, and a shell
#: pinned to the new version can never be fed by an emitter that still produces the old one.
SESSION_DRAWER_FEED_SCHEMA = "approval_drawer_feed@1.1"
SESSION_DECISION_FEED_SCHEMA = "approval_decision_feed@1.1"

#: The frozen gate contract a recorded plan verdict is re-validated against (schemas/ is the single
#: source of truth, @1.0 frozen) — read once, at import.
_GATE_SCHEMA = json.loads(
    (Path(__file__).resolve().parents[2] / "schemas" / "gate.schema.json").read_text(encoding="utf-8"))

#: The one identity the shell is allowed to record for a decision: the operator at this keyboard.
#: HONEST ASSUMPTION, carried over from 16D and unchanged here: the local shell PRESUMES the operator
#: is the one clicking. The authority re-checks the role on every replay regardless, so a recorded
#: non-operator role is refused (invariant 1, defense-in-depth) — the presumption never widens
#: authority, it only names the caller.
_OPERATOR_ROLE = "operator"

#: What is still owed, carried on every feed so the reader is never told more than was proven.
SIDE_EFFECTS_OWED: dict[str, Any] = {
    "owed": True,
    "issue": "17E",
    "note": ("a resolved item is recorded and stops being pending (it persists across fetches now); "
             "the downstream side effect of an APPROVE — the broker executing the queued command, "
             "ObjectiveIntake assigning an approved plan — is not fired from this read/decide path. "
             "A row's `ref` is therefore the pending id of the classification that rebuilt it, not a "
             "handle into a live broker: it is re-minted on every fetch and routes nowhere yet."),
}


class SideEffectRefused(RuntimeError):
    """A side effect was attempted behind a decision whose deciding identity is not authenticated."""


def authorize_side_effect(decision: Mapping[str, Any], *, operator: Identity | None = None,
                          operator_authenticated: bool = False) -> dict[str, Any]:
    """THE fence (W-42). Every executable effect behind an approval must pass exactly this.

    ONE function at the narrowest boundary that can turn a decision into an effect, rather than an
    `if operator_identity_presumed` scattered through approval types — that shape guarantees the
    next approval type added forgets it.

    WHAT THIS IS NOT: operator authentication. [[U207]] stays OPEN. This constrains the blast radius
    of the presumption; it does not remove it. `operator_authenticated` is supplied by the CALLER —
    the surface that actually bound the identity — and there is no such surface yet, which is
    precisely why every decision recorded today refuses here.

    PROVENANCE IS AN ARGUMENT, NEVER READ FROM THE RECORD. The record is the thing under suspicion:
    a caller that could clear `operator_identity_presumed` in a dict it authored would otherwise
    grant itself eligibility, and a `role: "operator"` string in that dict proves nothing. So the
    record's own flag is used only to REFUSE, never to permit.
    """
    if not isinstance(decision, Mapping):
        return {"eligible": False, "reason": "no decision record to authorize (fail closed)"}
    # (i) the record's own admission is sufficient to refuse, never to permit.
    if bool(decision.get("operator_identity_presumed")):
        return {"eligible": False, "reason": (
            "the deciding operator identity was PRESUMED, not authenticated (U207) — this decision "
            "is recordable and displayable, and may not produce an executable side effect")}
    # (ii) the caller must positively assert an authenticated binding. Absence is refusal, so a
    #      future executor that forgets the argument is refused rather than admitted.
    if not operator_authenticated or not isinstance(operator, Identity):
        return {"eligible": False, "reason": (
            "no authenticated operator identity was bound to this decision (U207) — being recorded "
            "with an Identity is not the same fact as that identity being authenticated")}
    # (iii) authentication answers WHO, not WHETHER. Invariant 1 still applies on top of it.
    if operator.role != _OPERATOR_ROLE:
        return {"eligible": False, "reason": (
            f"role {operator.role!r} is not the operator — authentication does not widen authority")}
    return {"eligible": True, "reason": "authenticated operator identity bound to this decision"}


def mark_side_effect_executed(decision: Mapping[str, Any], *, effect: str,
                              operator: Identity | None = None,
                              operator_authenticated: bool = False) -> dict[str, Any]:
    """Record that `effect` actually fired. Passes the SAME fence, because discharging the owed
    debt is itself a side effect — and the one most likely to be done "just for bookkeeping".

    Raises rather than returning a verdict: a caller reaching this point has already decided to act,
    so a value it might ignore is the wrong shape. `SIDE_EFFECTS_OWED` is never mutated here; an
    attempt leaves it exactly as it was.
    """
    verdict = authorize_side_effect(decision, operator=operator,
                                    operator_authenticated=operator_authenticated)
    if not verdict["eligible"]:
        raise SideEffectRefused(f"side effect {effect!r} refused: {verdict['reason']}")
    return {"effect": effect, "executed": True, "authorized_by": operator.node_id}


class SessionEventError(ValueError):
    """A recorded event could not be re-derived: a drifted schema, a malformed shape, a classification
    that no longer matches, or a decision the authority refuses on replay. Fail closed — the drawer is
    reported UNAVAILABLE rather than shown partially."""


# --------------------------------------------------------------------------------------
# W-43 — producer authenticity for `decision` events (U206)
# --------------------------------------------------------------------------------------

#: DOMAIN SEPARATION. The stamp is an HMAC, and W-41 made the IPC envelope one too. Without a domain
#: tag an authenticated IPC envelope whose canonical bytes happened to coincide could be transplanted
#: into this position and read as a valid approval stamp. The tag is a fixed literal PREFIXED to the
#: canonical bytes, so the signed input here begins with `SOW_APPROVAL_DECISION_V1\x00` and an
#: envelope's begins with `{` — the two byte strings cannot collide whatever the key.
#: Network-envelope authentication and approval-event provenance answer different questions; sharing
#: a hash construction must not become sharing an answer.
APPROVAL_DECISION_STAMP_DOMAIN = b"SOW_APPROVAL_DECISION_V1"

#: WHICH producer issued it. Signed like every other field, so it cannot be edited after minting; the
#: verifier also pins the accepted value, which is what makes a version bump a refusal rather than a
#: silently-accepted second producer.
APPROVAL_DECISION_PRODUCER = "session_approvals.route_session_decision@1.0"

#: The per-session key, delivered through the environment of the emitter processes the shell spawns
#: (`apps/desktop/approvals/drawer-source.js` mints it once per shell process and hands it to BOTH
#: the decision producer and the drawer builder). It is deliberately NOT a file beside the log: a key
#: readable by whoever can write the log would authenticate the forger too. Its lifetime matches the
#: log's — `SessionApprovalLog.begin()` truncates the log once per shell process — so a stamp minted
#: in one session cannot be replayed into another, and no session identifier has to be invented to
#: say so. The name matches `isCredentialEnvName` (substring `KEY`), so it is scrubbed out of every
#: pane, worker and conductor child environment by the W-29/W-32 machinery already in place.
APPROVAL_DECISION_KEY_ENV = "SOW_APPROVAL_DECISION_KEY"

#: Below this a "key" is not one. 32 bytes is the HMAC-SHA256 block-relevant floor the IPC path mints.
_APPROVAL_DECISION_KEY_MIN_BYTES = 32


def approval_decision_key() -> bytes | None:
    """The session's approval-decision key, or None when there is none to be had.

    Read at CALL time, never cached at import: the emitters are one-shot processes, and a cached
    absence would outlive the fix for it. None is not an error here — it is the fail-closed input
    that makes `decision_is_authentic` refuse everything and the decide path report unavailable.
    """
    raw = os.environ.get(APPROVAL_DECISION_KEY_ENV, "")
    try:
        key = bytes.fromhex(raw.strip())
    except ValueError:
        return None
    return key if len(key) >= _APPROVAL_DECISION_KEY_MIN_BYTES else None


def canonical_decision_bytes(decision: Mapping[str, Any]) -> bytes:
    """The byte form the stamp is taken over: the domain tag, then the WHOLE decision object except
    the stamp field itself.

    Everything-except-one is deliberate, and it is the opposite of an allowlist: a field added to the
    decision record later is signed by default, and a forger who ADDS a field changes these bytes and
    fails. An allowlist would have to be remembered, which is the shape this programme keeps finding
    unremembered. `canonical_payload` is W-41's serializer (sorted keys, compact, UTF-8), borrowed so
    there is exactly one canonicalization in the tree — two that can disagree is a signature bypass.

    NOT signed, because they do not participate in how a decision is interpreted: the event's
    `event_id`, `at` and `provenance`. `_apply_decision` reads none of them, and the shell RE-STAMPS
    `event_id`/`at` when it appends (`SessionApprovalLog.append`), so signing them would break every
    genuine decision in transit while protecting nothing.
    """
    body = {k: v for k, v in decision.items() if k != "authenticity"}
    return APPROVAL_DECISION_STAMP_DOMAIN + b"\x00" + canonical_payload(body)


def mint_decision_authenticity(decision: Mapping[str, Any], *, key: bytes) -> str:
    """Stamp a decision record. Called ONLY by the trusted producer, below."""
    return hmac.new(key, canonical_decision_bytes(decision), hashlib.sha256).hexdigest()


def decision_is_authentic(decision: Mapping[str, Any], *, key: bytes | None) -> bool:
    """Was this decision record minted by the trusted producer? Fail closed on every doubt.

    The stamp is NOT another caller-supplied assertion: `producer_authenticated: true` in a forged
    record would prove nothing, so nothing here reads a boolean the record asserts about itself. The
    only question asked is whether the recomputed HMAC matches, and only a holder of the session key
    can make it match for a given (item, decision, role, producer) tuple.
    """
    if key is None or not isinstance(decision, Mapping):
        return False
    stamp = decision.get("authenticity")
    if not isinstance(stamp, str) or not stamp:
        return False
    try:
        expected = mint_decision_authenticity(decision, key=key)
    except (TypeError, ValueError):
        return False                      # an unserializable record cannot be authentic
    # Compared as BYTES, not as str. `hmac.compare_digest` raises TypeError on a non-ASCII str, and
    # the stamp arrives from a file a forger may have written — so the str form would turn a forged
    # value into an exception of the wrong type escaping `build_session_queue`. Encoding first makes
    # every forgery a plain False. Unequal lengths are handled by compare_digest itself.
    if not hmac.compare_digest(expected.encode("ascii"), stamp.encode("utf-8")):
        return False
    # The producer name is inside the signed bytes, so this cannot be edited after minting; pinning
    # the accepted value is what stops a future second producer being honored by accident.
    return decision.get("producer") == APPROVAL_DECISION_PRODUCER


class _ChatRouted(RuntimeError):
    """Raised by the refusing sink when a recorded approval event re-routes as ORDINARY CHAT."""


class _RefusingChatSink:
    """The sink the re-derivation hands the router. Re-deriving a recorded event must never deliver
    anything to the conductor — the utterance was already routed once, when it happened. A CHAT
    outcome here means the recorded event claimed to be an approval row and is not one."""

    def deliver(self, message: Any) -> Any:
        raise _ChatRouted("the recorded utterance routes as ordinary chat — it is not a drawer item")


class _NoTranscriptionAdapter:
    """The bridge takes an adapter for transcription; re-derivation starts from a transcript that was
    already produced, so this one refuses to transcribe (and holds no engine, no audio, no retention).
    Injecting it is also what keeps this module free of any `adapters.voice_parakeet` import."""

    def transcribe(self, audio_ref: str) -> Any:
        raise SessionEventError("re-derivation never transcribes — it re-routes a recorded transcript")

    def start_capture(self) -> None:  # pragma: no cover - the bridge's capture API, unused here
        raise SessionEventError("re-derivation never captures audio")

    def stop_capture(self) -> None:  # pragma: no cover - same
        raise SessionEventError("re-derivation never captures audio")

    def get_usage(self) -> dict[str, Any]:  # pragma: no cover - not read on this path
        return {"tts": False, "retained_now": 0}

    def close(self) -> None:
        return None


@dataclass(frozen=True)
class _RecordedTask:
    """One task of a recorded decomposition, in the shape `build_plan_proposal` reads."""

    task_id: str
    capability: str
    description: str
    deps: tuple[str, ...] = ()


@dataclass(frozen=True)
class _RecordedDecomposition:
    """A recorded decomposition, in the shape `build_plan_proposal` reads. It carries no authority —
    the plan's approvability comes from the gate verdict, never from these rows."""

    tasks: tuple[_RecordedTask, ...] = ()
    refused: tuple[dict[str, Any], ...] = field(default_factory=tuple)


# --------------------------------------------------------------------------------------
# reading the log the shell writes
# --------------------------------------------------------------------------------------

def read_session_events(path: str | Path) -> list[dict[str, Any]]:
    """Read the append-only JSONL session-approval log. A MISSING log is an empty session (the
    ordinary state at first launch), NOT an error. A corrupt line IS an error — a log that cannot be
    read in full must not be rendered in part, because the part that failed to parse could be the
    decision that resolved the row we would otherwise show as pending."""
    p = Path(path)
    if not p.exists():
        return []
    try:
        text = p.read_text(encoding="utf-8")
    except OSError as exc:
        raise SessionEventError(f"could not read the session-approval log: {exc}") from exc
    events: list[dict[str, Any]] = []
    for n, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError as exc:
            raise SessionEventError(f"session-approval log line {n} is not JSON: {exc}") from exc
        if not isinstance(row, dict):
            raise SessionEventError(f"session-approval log line {n} is not an object")
        events.append(row)
    return events


# --------------------------------------------------------------------------------------
# rebuilding the queue from the events
# --------------------------------------------------------------------------------------

def _require_mapping(value: Any, what: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SessionEventError(f"{what} must be an object")
    return value


def _provenance_detail(event: Mapping[str, Any]) -> dict[str, Any]:
    """The provenance every row carries onto the operator's screen (invariant 11): which recorded
    event it came from and which channel recorded it."""
    prov = event.get("provenance") if isinstance(event.get("provenance"), Mapping) else {}
    return {
        "event_id": str(event.get("event_id") or ""),
        "at": str(event.get("at") or ""),
        "channel": str(prov.get("channel") or "unknown"),
        "feed_schema": prov.get("feed_schema"),
    }


class _ProvenanceMirror:
    """The mirror the router is given: `mirror_broker_outcome` with the CURRENT event's provenance
    folded into the row's detail. One instance is built per rebuild and re-aimed at each event, so the
    bridge is constructed once and no private attribute of it is ever touched."""

    def __init__(self, queue: ApprovalQueue) -> None:
        self._queue = queue
        self.provenance: dict[str, Any] = {}

    def __call__(self, outcome: Any, command: Any) -> str | None:
        return mirror_broker_outcome(self._queue, outcome, command, extra_detail=self.provenance)


def _apply_utterance(bridge: ConductorVoiceBridge, mirror: _ProvenanceMirror,
                     event: Mapping[str, Any]) -> None:
    """Re-route a recorded utterance through the REAL router and mirror whatever the REAL broker makes
    of it. The recorded classification is checked against the re-derived one; a mismatch fails closed."""
    utt = _require_mapping(event.get("utterance"), "an utterance event's `utterance`")
    text = utt.get("text")
    if not isinstance(text, str) or not text.strip():
        raise SessionEventError("an utterance event carries no transcript")
    source = utt.get("source")
    if source not in ("voice", "typed"):
        raise SessionEventError(f"an utterance event's source must be voice|typed, got {source!r}")
    confidence = utt.get("confidence")
    if confidence is not None and not isinstance(confidence, (int, float)):
        raise SessionEventError("an utterance event's confidence must be a number or null")
    claimed = utt.get("classified_as")
    if claimed not in (ConductorInputKind.PROPOSED_ACTION.value, ConductorInputKind.CLARIFY.value):
        raise SessionEventError(
            f"an utterance event must be recorded as proposed_action|clarify, got {claimed!r}")

    # Aim the mirror at THIS event so the row it enqueues carries this event's provenance. The
    # governed detail is merged last: the recorded event can add provenance, never overwrite what the
    # broker said about the command.
    mirror.provenance = _provenance_detail(event)
    try:
        outcome = bridge.route_transcript(text, source, confidence)
    except _ChatRouted as exc:
        raise SessionEventError(
            f"recorded {claimed!r} event {event.get('event_id')!r}: {exc}") from exc
    if outcome.kind.value != claimed:
        raise SessionEventError(
            f"recorded event {event.get('event_id')!r} claims {claimed!r} but the real classifier now "
            f"routes that utterance as {outcome.kind.value!r} — refusing to show the operator a row "
            f"its own classifier does not stand behind")
    if not outcome.queue_item_id:
        raise SessionEventError(
            f"recorded event {event.get('event_id')!r} produced no drawer item (nothing to approve)")


def _apply_plan(queue: ApprovalQueue, event: Mapping[str, Any]) -> None:
    """Surface a recorded plan. Its approvability is DERIVED from the recorded gate verdict, and the
    record must have the SHAPE of a rendered plan verdict: valid against the frozen `gate@1.0` schema,
    `kind == "plan"`, and claiming `decided_by == "gate_engine"`. That is a shape check, not proof of
    provenance - a well-made forgery passes it (see this module's HONEST RESIDUAL, U205)."""
    plan = _require_mapping(event.get("plan"), "a plan event's `plan`")
    objective = plan.get("objective")
    if not isinstance(objective, str) or not objective.strip():
        raise SessionEventError("a plan event carries no objective")
    gate = plan.get("plan_gate")
    if not isinstance(gate, Mapping):
        raise SessionEventError("a plan event carries no gate record")
    try:
        jsonschema.validate(dict(gate), _GATE_SCHEMA)
    except jsonschema.ValidationError as exc:
        raise SessionEventError(
            f"a plan event's gate record is not a valid gate@1.0 record: {exc.message}") from exc
    if gate.get("kind") != "plan":
        raise SessionEventError(f"a plan event's gate record must be a plan gate, got {gate.get('kind')!r}")
    if gate.get("decided_by") != "gate_engine":
        raise SessionEventError(
            f"a plan event's gate record must claim the gate engine decided it, got "
            f"{gate.get('decided_by')!r} — a plan is not approvable on a verdict that does not "
            f"even say a gate rendered it")
    blocked = plan.get("plan_blocked")
    if not isinstance(blocked, bool):
        raise SessionEventError("a plan event must record whether the flow blocked the plan")
    raw_tasks = plan.get("tasks")
    if not isinstance(raw_tasks, Sequence) or isinstance(raw_tasks, (str, bytes)):
        raise SessionEventError("a plan event's tasks must be a list")
    tasks = []
    for t in raw_tasks:
        row = _require_mapping(t, "a plan task")
        tasks.append(_RecordedTask(
            task_id=str(row.get("task_id") or ""), capability=str(row.get("capability") or ""),
            description=str(row.get("description") or ""),
            deps=tuple(str(d) for d in (row.get("deps") or []))))
    refused = tuple(dict(_require_mapping(r, "a refused task")) for r in (plan.get("refused") or []))
    decomposition = _RecordedDecomposition(tasks=tuple(tasks), refused=refused)
    # `approvable` is derived inside build_plan_proposal from (plan_blocked, verdict) — the recorded
    # event's own `approvable`, if it carries one, is never read.
    propose_plan_for_approval(queue, objective=objective, decomposition=decomposition,
                              plan_gate=gate, plan_blocked=blocked,
                              extra_detail=_provenance_detail(event))


def _apply_decision(queue: ApprovalQueue, event: Mapping[str, Any]) -> None:
    """Replay the operator's recorded decision THROUGH the authority, so invariant 1 and invariant 16
    are re-enforced on every rebuild — and a decided item stops appearing in the drawer."""
    dec = _require_mapping(event.get("decision"), "a decision event's `decision`")
    item_id = dec.get("item_id")
    decision = dec.get("decision")
    if not isinstance(item_id, str) or not item_id.strip():
        raise SessionEventError("a decision event names no item")
    role = dec.get("operator_role")
    if not isinstance(role, str) or not role.strip():
        raise SessionEventError("a decision event records no deciding role")
    # W-43. The authenticity check sits AFTER the shape checks and BEFORE the authority, on purpose.
    # After the shape checks, so a malformed event still fails on being malformed and the tests that
    # exercise those guards still reach them. Before `queue.resolve`, because this is the state-
    # consumption boundary: whether a recorded decision may affect approval state is decided HERE,
    # once, rather than per approval kind. An unauthenticated decision is not a decision at all, so
    # invariant 1 and invariant 16 are never even asked about it.
    if not decision_is_authentic(dec, key=approval_decision_key()):
        raise SessionEventError(
            f"recorded decision on {item_id!r} carries no valid producer authenticity stamp — only a "
            f"decision minted by the trusted producer may dispose of an approval (U206); a "
            f"hand-built decision event is not authoritative however well-formed it is")
    identity = Identity(node_id="operator", role=role, project_id="proj")
    try:
        queue.resolve(item_id, identity, decision=str(decision),
                      reason=str(dec.get("reason") or ""))
    except ApprovalError as exc:
        # The shell's decide path only appends AFTER the authority resolved, so on an untampered log a
        # refusal here means a bug. On a tampered one it means the file disagrees with the authority —
        # which is exactly why the replay goes through `resolve` instead of being believed. Either way,
        # fail closed: a log that cannot be replayed is reported unavailable, never rendered in part.
        raise SessionEventError(
            f"recorded decision on {item_id!r} is refused by the authority on replay: {exc}") from exc


def build_session_queue(events: Iterable[Mapping[str, Any]]) -> ApprovalQueue:
    """Rebuild the operator's approval queue from the recorded session events. Deterministic: the same
    log rebuilds the same queue with the same item ids (they are positional, and the log is
    append-only, so an appended event never renumbers a row the operator is looking at).

    Raises `SessionEventError` on ANY event it cannot re-derive — the caller renders UNAVAILABLE."""
    queue = ApprovalQueue()
    mirror = _ProvenanceMirror(queue)
    bridge = ConductorVoiceBridge(chat_sink=_RefusingChatSink(), broker=CommandBroker(),
                                  adapter=_NoTranscriptionAdapter(), mirror=mirror)
    try:
        for event in events:
            if not isinstance(event, Mapping):
                raise SessionEventError("a session-approval event must be an object")
            if event.get("schema") != SESSION_APPROVAL_EVENT_SCHEMA:
                raise SessionEventError(
                    f"session-approval event schema must be {SESSION_APPROVAL_EVENT_SCHEMA}, got "
                    f"{event.get('schema')!r}")
            kind = event.get("kind")
            if kind == "utterance":
                _apply_utterance(bridge, mirror, event)
            elif kind == "plan":
                _apply_plan(queue, event)
            elif kind == "decision":
                _apply_decision(queue, event)
            else:
                raise SessionEventError(f"unknown session-approval event kind {kind!r} (fail closed)")
    finally:
        bridge.close()
    return queue


# --------------------------------------------------------------------------------------
# the shell contract
# --------------------------------------------------------------------------------------

def _empty_drawer() -> dict[str, Any]:
    """The fail-closed drawer payload — an EMPTY queue's own `drawer_model()`, never a literal."""
    return ApprovalQueue().drawer_model()


def fold_session_drawer_feed(drawer_model: Mapping[str, Any], *, event_count: int,
                             decision_count: int) -> dict[str, Any]:
    """Fold a rebuilt drawer into the `approval_drawer_feed@1.1` contract the shell renders. PURE."""
    pending = list(drawer_model.get("pending") or [])
    return {
        "schema": SESSION_DRAWER_FEED_SCHEMA,
        "sourced": True,
        "source": "session_events",
        "event_count": int(event_count),
        "decision_count": int(decision_count),
        # The F2 receipt, carried on the wire: nothing in this feed was demonstration content.
        "demo_items": False,
        "drawer": dict(drawer_model),
        "badge_count": int(drawer_model.get("badge_count") or 0),
        "kinds_present": sorted({str(r.get("kind")) for r in pending if isinstance(r, Mapping)}),
        "side_effects_owed": dict(SIDE_EFFECTS_OWED),
        "torn_down": True,   # nothing is started here: no MCP server, no flow, no engine
    }


def unavailable_session_feed(reason: str, *, event_count: int = 0) -> dict[str, Any]:
    """The fail-closed feed: the drawer could NOT be rebuilt. An empty drawer + the honest reason —
    never a partial drawer (a log we cannot fully re-derive may be hiding a decision)."""
    return {
        "schema": SESSION_DRAWER_FEED_SCHEMA,
        "sourced": False,
        "source": "session_events",
        "reason": reason,
        "event_count": int(event_count),
        "decision_count": 0,
        "demo_items": False,
        "drawer": _empty_drawer(),
        "badge_count": 0,
        "kinds_present": [],
        "side_effects_owed": dict(SIDE_EFFECTS_OWED),
        "torn_down": True,
    }


def build_session_drawer_feed(events: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Top-level READ path: rebuild the drawer from the recorded events, or fail closed. Never raises."""
    rows = list(events or [])
    try:
        queue = build_session_queue(rows)
    except Exception as exc:  # noqa: BLE001 — any fault is reported as unavailable, never faked
        return unavailable_session_feed(f"{type(exc).__name__}: {exc}", event_count=len(rows))
    decisions = sum(1 for e in rows if isinstance(e, Mapping) and e.get("kind") == "decision")
    return fold_session_drawer_feed(queue.drawer_model(), event_count=len(rows),
                                    decision_count=decisions)


def _decision_base(item_id: str, decision: str, *, identity_presumed: bool) -> dict[str, Any]:
    return {
        "schema": SESSION_DECISION_FEED_SCHEMA,
        "item_id": item_id,
        "decision": decision,
        "authority": "operator-only (ApprovalQueue.resolve enforces invariant 1 / invariant 16)",
        # The two halves of that sentence are not equally proven, and the wire should say so
        # (invariant 3). The invariant-16 half is enforced against a real item: a non-approvable item
        # is refused here and on every replay. The invariant-1 half is enforced against an identity the
        # local shell PRESUMES — the role is re-checked, but nothing on this path authenticates who is
        # at the keyboard (U207). A caller supplying a non-operator identity is still refused.
        "operator_identity_presumed": bool(identity_presumed),
        # load-bearing: the shell forwarded an intent; this Python authority decided.
        "self_authorized": False,
        "side_effects_owed": dict(SIDE_EFFECTS_OWED),
        "torn_down": True,
    }


def route_session_decision(*, events: Sequence[Mapping[str, Any]], item_id: str, decision: str,
                           reason: str = "", operator: Identity | None = None) -> dict[str, Any]:
    """Route the operator's approve/reject to the GOVERNED authority over the event-sourced queue.

    On a resolve this ALSO mints the `decision` event the shell must append so the decision persists —
    minted here, by the authority that made it, so the shell never authors a decision record of its
    own. A governed refusal (invariant 1/16) mints nothing: there is nothing to persist."""
    op = operator if isinstance(operator, Identity) else Identity(
        node_id="operator", role=_OPERATOR_ROLE, project_id="proj")
    out = _decision_base(item_id, decision, identity_presumed=not isinstance(operator, Identity))
    # W-43: without the session key this authority cannot mint a decision the drawer builder will
    # honor. Reporting UNAVAILABLE is the honest answer — resolving in memory and handing back an
    # unstampable event would tell the operator their decision was recorded when nothing durable
    # happened. Checked FIRST so it cannot be reached only on the paths that happen to resolve.
    key = approval_decision_key()
    if key is None:
        return {**out, "resolved": False, "refused": False, "unavailable": True,
                "reason": (f"no approval-decision key in {APPROVAL_DECISION_KEY_ENV} — this authority "
                           f"cannot mint a decision the drawer will honor, so it does not claim to "
                           f"have made one")}
    try:
        queue = build_session_queue(list(events or []))
    except Exception as exc:  # noqa: BLE001 — a log we cannot re-derive is unavailable, not a resolve
        return {**out, "resolved": False, "refused": False, "unavailable": True,
                "reason": f"{type(exc).__name__}: {exc}"}
    try:
        resolved = queue.resolve(item_id, op, decision=decision, reason=reason)
    except ApprovalError as exc:
        return {**out, "resolved": False, "refused": True, "reason": f"{type(exc).__name__}: {exc}"}
    # W-43: THE trusted decision producer. The record is assembled first and stamped last, over
    # itself — so every field that says which approval was decided, what was decided, by which role
    # and by which producer is inside the signature. A field added here later is signed by default.
    minted = {"item_id": item_id, "decision": decision, "reason": str(reason or ""),
              "operator_role": op.role, "producer": APPROVAL_DECISION_PRODUCER}
    minted["authenticity"] = mint_decision_authenticity(minted, key=key)
    return {
        **out,
        "resolved": True,
        "refused": False,
        "item": resolved.as_row(),
        "decision_event": {
            "schema": SESSION_APPROVAL_EVENT_SCHEMA,
            "event_id": f"dec-{item_id}",
            "kind": "decision",
            "decision": minted,
            "provenance": {"channel": "approvals:decide", "feed_schema": SESSION_DECISION_FEED_SCHEMA},
        },
    }
