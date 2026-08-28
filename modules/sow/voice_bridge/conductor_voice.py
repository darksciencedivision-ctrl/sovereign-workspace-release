"""Voice-IN to the live CONDUCTOR (Phase 15E `.voice`; OP-8 §13.5, invariants 24/25, I-V1..V3).

OP-8 §13.5: *"the operator can speak to the conductor; transcribed text enters the conductor's input
on the same command path as typing (propose->approve for destructive/protected actions per I-V3;
ordinary chat flows directly)."* This is DISTINCT from the Phase-12 voice surface (voice as a
shell-control command bus, `voice_bridge.command_broker` + `adapters.voice_parakeet`): here voice is
a second INPUT surface over the CONDUCTOR CONVERSATION.

The bridge is a router, not a new authority. It COMPOSES pieces already built and re-implements no
classifier, no lifecycle and no authority:
  * transcription + transcribe-then-discard + bounded diagnostic retention: the Phase-12
    `VoiceAdapter` (STT-only; audio never egresses under the offline profile).
  * the gated-verb normalization: `voice_bridge.spoken_verbs.split_spoken_command` — the SAME
    table the Phase-12 adapter uses, scanning the full utterance so polite prefixes cannot evade it.
  * protected/destructive gating: the Phase-12 `CommandBroker` (propose-never-execute, invariant 25).
  * the ONE operator approval drawer: an injected `mirror` (in production
    `operator_surface.mirror_broker_outcome`) — so a spoken protected action surfaces beside plan and
    typed approvals in the same drawer, routing back to the same broker `pending_id`.

Routing (deterministic — never model output; fail-closed):
  1. A VOICE transcript with low/absent STT confidence -> CLARIFY. A garbled transcript never enters
     the conductor's conversation and never proposes an action (fail closed, I-V3). Blank text (from
     either surface) clarifies too.
  2. A recognized PROTECTED or DESTRUCTIVE verb anywhere -> PROPOSED ACTION: submitted to the
     `CommandBroker`, which QUEUES it for operator approval (never auto-executes, invariant 25) and is
     mirrored into the drawer. It is NOT delivered into the conversation as text.
  3. Anything else -> ORDINARY CHAT: delivered verbatim to the conductor's input, exactly as if the
     operator had typed it (the "same command path as typing").

**CORRECTED at Phase 17C `.close` (spec-audit MAJOR-3).** Rule 3 used to end: "The conductor is itself a
governed node — it cannot execute a protected action without the broker either." That was true while the
sink was this module's `_RecordingSink` or a `powershell.exe` stand-in pane, and it is FALSE of the sink
17C installs. The conductor is a live first-party `claude` CLI: it is *spawned* through the governed
ticket path (supervised admission, governed identity, workspace binding, credential scrub, I-X3 lease),
but this router alone cannot govern that vendor process's tool use. The production launch now binds a
supervisor-owned per-turn profile: direct voice CHAT is marked, UserPromptSubmit arms the turn before
model processing, and PreToolUse/PermissionRequest deny every tool/escalation until Stop. Vendor mode
chrome remains interaction state only; invariant 29 forbids treating it as authority. Deterministic
lexicon coverage remains bounded (U144, narrowed from the former leading-word-only defect by scanning
the whole utterance plus common inflections), and STT confidence is uncalibrated (U140). Nothing in
this module may cite vendor chrome as why CHAT is safe.

Only protected/destructive verbs gate here; a *safe* Phase-12 nav verb (focus/status/...) is NOT
special-cased — spoken to the conductor it is CONVERSATION (shell nav has its own typed/button
surface). This is the narrowest gate that satisfies invariant 25, and it honors "ordinary chat flows
directly". Trade-off, disclosed and fail-closed: a conversational sentence containing a
destructive/protected verb (e.g. "delete that stray comment") is over-gated into the approval drawer
rather than delivered as chat; the operator simply dismisses it. Over-gating is the safe direction —
voice must never expand authority, and a queued item is inert until the operator acts.

typed/voice equivalence: `speak()` (voice) and `type_message()` (typed) share ONE `_route`, so the
same text routes identically and a delivered chat message carries the same `semantic_key` regardless
of surface (only the `source` tag differs).

NO speech-OUT (I-V2/D-VOICE-02): this bridge has no synthesize/speak/tts method by construction.
Spoken answers remain OWED-BY-OPERATOR-DECISION (OP-8 §13.6) — recorded, never faked.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Protocol, runtime_checkable

from voice_bridge.command_broker import (
    DEFAULT_CONFIDENCE_THRESHOLD,
    DESTRUCTIVE_VERBS,
    PROTECTED_VERBS,
    BrokerOutcome,
    CommandBroker,
    Disposition,
    ProposedCommand,
)
from voice_bridge.spoken_verbs import split_spoken_command

VOICE = "voice"
TYPED = "typed"
#: the verbs a spoken utterance must PROPOSE (never deliver as chat, never execute) — invariant 25.
GATED_VERBS = PROTECTED_VERBS | DESTRUCTIVE_VERBS


class ConductorVoiceError(RuntimeError):
    """A fail-closed refusal inside the router — raised only where continuing would mean delivering
    or executing something a branch had already decided must not be delivered or executed."""


class ConductorInputKind(str, Enum):
    """What the router did with one operator utterance/keystroke to the conductor."""

    CHAT = "chat"                        # delivered verbatim to the conductor conversation
    PROPOSED_ACTION = "proposed_action"  # queued for operator approval (never executed here)
    CLARIFY = "clarify"                  # low/absent confidence or blank — nothing delivered/queued


@dataclass(frozen=True)
class ConductorChatMessage:
    """One conversational message delivered into the conductor's input. Immutable; the `source` tag
    records voice vs typed but does NOT change the semantics (equivalence)."""

    text: str
    source: str

    def semantic_key(self) -> str:
        """The part that must be identical for typed/voice equivalence — the delivered text, not the
        surface it arrived on."""
        return self.text.strip()


@runtime_checkable
class ConductorChatSink(Protocol):
    """Submit-only delivery into the conductor's conversation input — what the bridge is handed so a
    transducer cannot reach execution/approval (least privilege, invariant 25). The real sink writes
    to the interactive conductor ConPTY (an operator-run surface, directive §6); the mock sink records
    deliveries for the headless proof."""

    def deliver(self, message: ConductorChatMessage) -> Any: ...


@dataclass(frozen=True)
class ConductorInputOutcome:
    """The result of routing ONE utterance/keystroke. Fully observable (Buildout §4): the kind, the
    surface, the text, and — depending on the branch — the delivered chat message, the broker outcome
    and the drawer item id."""

    kind: ConductorInputKind
    source: str
    text: str
    confidence: float | None = None
    chat_message: ConductorChatMessage | None = None
    delivery: Any = None
    broker_outcome: BrokerOutcome | None = None
    queue_item_id: str | None = None
    reason: str = ""


#: a mirror maps (broker outcome, the proposed command) -> a drawer item id (or None). In production
#: this is `functools.partial(operator_surface.mirror_broker_outcome, queue)`; injected so the bridge
#: needs no import of the operator surface (and stays a pure router).
Mirror = Callable[[BrokerOutcome, ProposedCommand], "str | None"]


class ConductorVoiceBridge:
    """Routes operator speech (and, for equivalence, typed input) into the conductor conversation."""

    def __init__(self, *, chat_sink: ConductorChatSink, broker: CommandBroker,
                 engine: Any = None, adapter: Any = None, mirror: Mirror | None = None,
                 confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
                 diagnostic_retention: bool = False, retention_ttl_s: int = 7 * 24 * 3600,
                 network: str = "none") -> None:
        # Lazily import the Phase-12 adapter here (not at module top) so importing this module can
        # never form a cycle with adapters.voice_parakeet. The adapter provides transcribe-then-discard
        # + retention + usage; the bridge uses ONLY its transcription (its own proposer, handed a
        # submit-only broker handle, is never invoked by the bridge).
        if adapter is None:
            from adapters.voice_parakeet.adapter import VoiceAdapter

            adapter = VoiceAdapter(
                broker.as_proposer(), engine, diagnostic_retention=diagnostic_retention,
                retention_ttl_s=retention_ttl_s, network=network)
        self._adapter = adapter
        self._broker = broker
        self._sink = chat_sink
        self._mirror = mirror
        # FAIL CLOSED AT CONSTRUCTION (Phase 17D `.events`, spec-audit): the router's clarify branch
        # routes through the broker, and it can only rely on the broker's rule 1 to refuse execution if
        # the broker's bar is at least as high as this router's. A bridge that clarified at a HIGHER
        # confidence than its broker would hand over utterances it had itself judged too uncertain, and
        # the broker — finding them confident enough — would execute a safe verb. Refuse the pairing
        # here rather than discover it one utterance at a time.
        broker_threshold = getattr(broker, "confidence_threshold", None)
        if isinstance(broker_threshold, (int, float)) and confidence_threshold > broker_threshold:
            raise ConductorVoiceError(
                f"this router clarifies below {confidence_threshold} but its broker only clarifies "
                f"below {broker_threshold}: an utterance between the two would be routed as uncertain "
                f"and executed as confident (fail closed — the broker's bar may not be the lower one)")
        self._threshold = confidence_threshold
        self._log: list[dict[str, Any]] = []

    # -- capture lifecycle (push-to-talk) -------------------------------------
    def start_capture(self) -> None:
        self._adapter.start_capture()

    def stop_capture(self) -> None:
        self._adapter.stop_capture()

    # -- the two input surfaces, one router -----------------------------------
    def speak(self, audio_ref: str) -> ConductorInputOutcome:
        """Push-to-talk: transcribe (audio discarded per the adapter's policy), then route. The
        conductor voice-IN path (OP-8 §13.5)."""
        t = self._adapter.transcribe(audio_ref)  # transcribe-then-discard by default
        return self.route_transcript(t.text, VOICE, t.confidence)

    def type_message(self, text: str) -> ConductorInputOutcome:
        """The typed conductor-input path — the SAME router, so typed and voice are equivalent (the
        "same command path as typing"). Typed input carries no STT confidence and is not clarified on
        confidence (it is deliberate), but a destructive/protected verb still proposes, never runs."""
        return self.route_transcript(text, TYPED, None)

    def route_transcript(self, text: str, source: str, confidence: float | None) -> ConductorInputOutcome:
        """Route an ALREADY-TRANSCRIBED utterance — the same router `speak()` and `type_message()` use,
        exposed so a caller holding a recorded transcript can re-derive its classification instead of
        re-implementing one (invariant 30: no second classifier).

        Phase 17D `.events` uses this to REBUILD the approval drawer from recorded session events: the
        shell records what the operator actually said/typed and the classification the governed feed
        reported, and the drawer builder re-runs THIS router over the recorded transcript. A recorded
        event whose transcript no longer classifies the way it claims is refused, so the least-trusted
        surface cannot promote its own row into the operator's drawer.

        It routes; it decides nothing extra. A CHAT still reaches the injected sink — a re-derivation
        caller therefore injects a sink that REFUSES delivery (a recorded approval event that
        re-derives as ordinary chat is a mismatch, not a message to send)."""
        return self._route(text, source, confidence)

    def _route(self, text: str, source: str, confidence: float | None) -> ConductorInputOutcome:
        raw = text if isinstance(text, str) else ""
        verb, target = split_spoken_command(raw, GATED_VERBS)
        # (0) blank/empty -> clarify (nothing to deliver; fail closed on either surface).
        if not raw.strip():
            return self._record(self._clarify(raw, source, confidence, "empty transcript"))
        # (1) low/absent-confidence VOICE -> clarify: never converse, never propose (I-V3, fail closed).
        if source == VOICE and (confidence is None or confidence < self._threshold):
            return self._record(self._clarify(
                raw, source, confidence,
                f"low/absent STT confidence {confidence} < {self._threshold}"))
        # (2) a recognized protected/destructive verb -> PROPOSE via the broker (never execute; never
        #     delivered as chat). The broker classifies and queues; the mirror surfaces it in the drawer.
        if verb in GATED_VERBS:
            cmd = ProposedCommand(source=source, verb=verb, target=target, raw_text=raw,
                                  confidence=confidence)
            outcome = self._broker.submit(cmd)  # submit-only path: the bridge never approves/executes
            item_id = self._mirror(outcome, cmd) if self._mirror is not None else None
            return self._record(ConductorInputOutcome(
                kind=ConductorInputKind.PROPOSED_ACTION, source=source, text=raw, confidence=confidence,
                broker_outcome=outcome, queue_item_id=item_id, reason=outcome.reason))
        # (3) ordinary conversation -> deliver verbatim to the conductor input (same as typing).
        msg = ConductorChatMessage(text=raw, source=source)
        delivery = self._sink.deliver(msg)
        return self._record(ConductorInputOutcome(
            kind=ConductorInputKind.CHAT, source=source, text=raw, confidence=confidence,
            chat_message=msg, delivery=delivery))

    def _clarify(self, raw: str, source: str, confidence: float | None,
                 reason: str) -> ConductorInputOutcome:
        """A clarification the operator can SEE (Phase 17D `.events`).

        Before 17D these two branches returned a bare CLARIFY outcome: the utterance was correctly
        refused, but it never reached the one approval drawer, so an operator whose speech was not
        confidently heard got nothing to look at — the drawer was where OP-7 §12.5 said clarifications
        surface. The refusal is unchanged; it now goes through the same broker + mirror the proposed
        action does, so it lands beside the other things awaiting the operator.

        This can never widen authority: the broker's own rule 1 (a low/absent-confidence VOICE command
        is never executed) and rule 2 (an unrecognized verb clarifies) are exactly the conditions that
        bring us here, so the disposition must come back CLARIFY. If it ever does not, we fail closed
        rather than let a clarify branch fall into delivery or execution.

        "Exactly the conditions" holds because the constructor refuses a bridge whose threshold sits
        ABOVE its broker's. Without that check the reasoning had a hole the audit found: a bridge
        clarifying at 0.9 over a broker clarifying at 0.5 would hand a 0.6-confidence *safe* verb to a
        broker that considers it confident enough — rule 4, EXECUTED, a control event minted before the
        guard below could refuse it. The guard stays as defence in depth, but it is no longer the only
        thing standing between a clarify branch and an execution."""
        verb, target = split_spoken_command(raw, GATED_VERBS)
        cmd = ProposedCommand(source=source, verb=verb, target=target, raw_text=raw,
                              confidence=confidence)
        outcome = self._broker.submit(cmd)   # submit-only path: the bridge never approves/executes
        if outcome.disposition is not Disposition.CLARIFY:
            raise ConductorVoiceError(
                f"a clarify branch must clarify: the broker returned {outcome.disposition} for "
                f"{verb!r} (fail closed — nothing is delivered and nothing is executed)")
        item_id = self._mirror(outcome, cmd) if self._mirror is not None else None
        return ConductorInputOutcome(
            kind=ConductorInputKind.CLARIFY, source=source, text=raw, confidence=confidence,
            broker_outcome=outcome, queue_item_id=item_id, reason=reason)

    def _record(self, outcome: ConductorInputOutcome) -> ConductorInputOutcome:
        self._log.append({"kind": outcome.kind.value, "source": outcome.source,
                          "reason": outcome.reason})
        return outcome

    # -- observability --------------------------------------------------------
    def log(self) -> list[dict[str, Any]]:
        return list(self._log)

    def get_usage(self) -> dict[str, Any]:
        """The voice usage view — transcribe-then-discard counters, retention state, network posture,
        and `tts: False` (STT-only; carried through from the adapter)."""
        return dict(self._adapter.get_usage())

    def close(self) -> None:
        self._adapter.close()
