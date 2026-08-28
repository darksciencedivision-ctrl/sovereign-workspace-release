"""Phase 15E `.voice` acceptance matrix — voice-IN to the live CONDUCTOR (OP-8 §13.5; I-V1..V3,
invariants 24/25).

Distinct from the Phase-12 shell-control voice bus (`test_voice_input.py`): here voice is a second
input surface over the CONDUCTOR CONVERSATION. Ordinary chat flows DIRECTLY into the conductor's
input (the "same command path as typing"); a spoken protected/destructive ACTION proposes→approves
through the real CommandBroker and never executes (invariant 25); a low-confidence transcript
clarifies and never enters the conversation; typed and voice forms of the same text route
identically; there is NO speech-out (I-V2/D-VOICE-02).
"""
from __future__ import annotations

import pytest

from adapters.voice_parakeet.engine import Transcript
from control_plane.orchestration.operator_surface import (
    ApprovalKind,
    ApprovalQueue,
    apply_protected_decision,
    mirror_broker_outcome,
)
from control_plane.policy import Identity
from voice_bridge.command_broker import CommandBroker, Disposition
from voice_bridge.conductor_voice import (
    ConductorChatMessage,
    ConductorInputKind,
    ConductorVoiceBridge,
    ConductorVoiceError,
)

OPERATOR = Identity("op", "operator", "proj")
WORKER = Identity("w", "worker", "proj")


class _ScriptedSTT:
    """A deterministic conductor-conversation STT: maps audio refs to (text, confidence). Includes
    conversational phrases (the Phase-12 MockSTT only scripts shell commands)."""

    name = "scripted-stt"
    _SCRIPT = {
        "audio:chat-question": ("what is the status of the auth refactor", 0.96),
        "audio:chat-greet": ("hello conductor let us plan the parser work", 0.95),
        "audio:chat-direction": ("focus the next task on the failing login test", 0.94),
        "audio:terminate-node": ("terminate node-B", 0.93),
        "audio:spawn-worker": ("spawn a coding worker", 0.92),
        "audio:grant-admin": ("grant admin to worker-A", 0.9),
        "audio:stop-node": ("stop node-B", 0.9),           # 'stop' synonym -> terminate (destructive)
        "audio:mumble": ("uh something something", 0.35),  # low confidence
    }

    def transcribe(self, audio_ref: str) -> Transcript:
        text, conf = self._SCRIPT.get(audio_ref, ("unintelligible", 0.3))
        return Transcript(text=text, confidence=conf)


class _RecordingSink:
    """A submit-only conductor chat sink that records deliveries (the mock for the operator-run
    interactive ConPTY write)."""

    def __init__(self) -> None:
        self.delivered: list[ConductorChatMessage] = []

    def deliver(self, message: ConductorChatMessage):
        self.delivered.append(message)
        return {"ok": True, "seq": len(self.delivered)}


def _wired(**kw):
    broker = CommandBroker()
    queue = ApprovalQueue()
    sink = _RecordingSink()
    bridge = ConductorVoiceBridge(
        chat_sink=sink, broker=broker, engine=_ScriptedSTT(),
        mirror=lambda outcome, cmd: mirror_broker_outcome(queue, outcome, cmd), **kw)
    return broker, queue, sink, bridge


# -- ordinary chat flows directly into the conductor conversation -------------------------------

def test_ordinary_speech_flows_directly_to_the_conductor() -> None:
    _, _, sink, bridge = _wired()
    out = bridge.speak("audio:chat-question")
    assert out.kind is ConductorInputKind.CHAT
    assert out.chat_message is not None
    assert out.chat_message.text == "what is the status of the auth refactor"
    assert out.chat_message.source == "voice"
    # delivered verbatim to the conductor input — nothing queued, nothing executed
    assert len(sink.delivered) == 1 and sink.delivered[0].text == out.chat_message.text


def test_conversational_command_word_is_not_a_shell_control_command() -> None:
    """'focus the next task ...' is CONVERSATION to the conductor, not a Phase-12 `focus` control
    command: a safe verb no longer hijacks conductor speech — only protected/destructive gate."""
    _, _, sink, bridge = _wired()
    out = bridge.speak("audio:chat-direction")
    assert out.kind is ConductorInputKind.CHAT
    assert sink.delivered[0].text.startswith("focus the next task")


# -- protected/destructive: propose→approve, never execute (invariant 25) -----------------------

def test_destructive_speech_proposes_and_queues_never_executes() -> None:
    broker, queue, sink, bridge = _wired()
    out = bridge.speak("audio:terminate-node")
    assert out.kind is ConductorInputKind.PROPOSED_ACTION
    assert out.broker_outcome.disposition is Disposition.APPROVAL_QUEUED
    # NOT delivered into the conversation, and nothing executed
    assert sink.delivered == []
    assert not any(e["kind"] == "control_event" for e in broker.log())
    # it surfaced in the ONE operator drawer as a protected/destructive action
    item = queue.get(out.queue_item_id)
    assert item.kind is ApprovalKind.PROTECTED_ACTION
    assert item.ref == out.broker_outcome.pending_id  # routes back to the same broker


def test_voice_cannot_instantiate_a_node_via_the_conductor() -> None:
    broker, queue, sink, bridge = _wired()
    out = bridge.speak("audio:spawn-worker")  # spawn is PROTECTED
    assert out.kind is ConductorInputKind.PROPOSED_ACTION
    assert out.broker_outcome.disposition is Disposition.APPROVAL_QUEUED
    assert sink.delivered == []
    assert not any(e["kind"] == "control_event" for e in broker.log())


def test_voice_cannot_expand_permissions_via_the_conductor() -> None:
    broker, _, sink, bridge = _wired()
    out = bridge.speak("audio:grant-admin")  # grant is PROTECTED
    assert out.kind is ConductorInputKind.PROPOSED_ACTION
    assert out.broker_outcome.disposition is Disposition.APPROVAL_QUEUED
    assert sink.delivered == []


def test_spoken_synonym_escalates_to_the_destructive_queue() -> None:
    """'stop node-B' -> terminate (destructive): a synonym escalates to approval, never chat."""
    broker, _, sink, bridge = _wired()
    out = bridge.speak("audio:stop-node")
    assert out.kind is ConductorInputKind.PROPOSED_ACTION
    assert out.broker_outcome.disposition is Disposition.APPROVAL_QUEUED
    assert sink.delivered == []


@pytest.mark.parametrize("utterance, expected_verb", [
    ("please delete the ledger", "delete"),
    ("please erase the ledger", "delete"),
    ("please begin removing the old branch", "remove"),
    ("could you stop node-B now", "terminate"),
    ("I need you to grant admin access", "grant"),
    ("begin authorizing the new worker", "authorize"),
])
def test_indirect_destructive_or_protected_language_is_queued_not_chat(
        utterance: str, expected_verb: str) -> None:
    """Voice cannot evade the broker by placing a polite word before the dangerous verb."""
    broker, _, sink, bridge = _wired()
    out = bridge._route(utterance, "voice", 0.95)
    assert out.kind is ConductorInputKind.PROPOSED_ACTION
    assert out.broker_outcome.disposition is Disposition.APPROVAL_QUEUED
    assert sink.delivered == []
    assert broker.pending()
    assert next(iter(broker.pending().values())).verb == expected_verb


def test_operator_approval_of_a_spoken_action_executes_through_the_broker() -> None:
    """The whole governed path: spoken destructive action -> drawer -> operator approve -> the REAL
    broker executes the control event. The operator disposes (invariant 1)."""
    broker, queue, _, bridge = _wired()
    out = bridge.speak("audio:terminate-node")
    item = queue.resolve(out.queue_item_id, OPERATOR, decision="approve")
    ev = apply_protected_decision(broker, item, OPERATOR)
    assert ev is not None and ev.verb == "terminate" and ev.target == "node-b"


def test_non_operator_cannot_approve_a_spoken_action() -> None:
    broker, queue, _, bridge = _wired()
    out = bridge.speak("audio:spawn-worker")
    from control_plane.orchestration.operator_surface import ApprovalError
    with pytest.raises(ApprovalError, match="only the operator"):
        queue.resolve(out.queue_item_id, WORKER, decision="approve")
    # still queued, nothing executed
    assert out.broker_outcome.pending_id in broker.pending()
    assert not any(e["kind"] == "control_event" for e in broker.log())


# -- low/absent confidence fails closed to clarify ----------------------------------------------

def test_low_confidence_clarifies_and_does_not_enter_the_conversation() -> None:
    broker, _, sink, bridge = _wired()
    out = bridge.speak("audio:mumble")  # confidence 0.35 < 0.6
    assert out.kind is ConductorInputKind.CLARIFY
    assert out.chat_message is None
    assert sink.delivered == []                                   # never delivered as chat
    assert not any(e["kind"] == "control_event" for e in broker.log())  # never executed


def test_absent_confidence_fails_closed_to_clarify() -> None:
    _, _, sink, bridge = _wired()
    out = bridge._route("terminate node-B", "voice", None)  # a voice event with no STT confidence
    assert out.kind is ConductorInputKind.CLARIFY
    assert sink.delivered == []


# -- typed/voice equivalence --------------------------------------------------------------------

def test_typed_and_voice_chat_are_equivalent() -> None:
    _, _, sink, bridge = _wired()
    v = bridge.speak("audio:chat-question")
    t = bridge.type_message("what is the status of the auth refactor")
    assert v.kind is t.kind is ConductorInputKind.CHAT
    # identical delivered text (only the source tag differs) — the "same command path as typing"
    assert v.chat_message.semantic_key() == t.chat_message.semantic_key()
    assert v.chat_message.source == "voice" and t.chat_message.source == "typed"


def test_typed_and_voice_destructive_route_identically() -> None:
    broker, queue, sink, bridge = _wired()
    v = bridge.speak("audio:terminate-node")
    t = bridge.type_message("terminate node-B")
    assert v.kind is t.kind is ConductorInputKind.PROPOSED_ACTION
    assert v.broker_outcome.disposition is t.broker_outcome.disposition is Disposition.APPROVAL_QUEUED
    assert sink.delivered == []  # neither surface delivered a destructive action as chat


def test_typed_chat_delivers_verbatim() -> None:
    _, _, sink, bridge = _wired()
    out = bridge.type_message("please summarize the parser diff")
    assert out.kind is ConductorInputKind.CHAT
    assert sink.delivered[0].text == "please summarize the parser diff"
    assert sink.delivered[0].source == "typed"


# -- transcribe-then-discard + no TTS -----------------------------------------------------------

def test_transcribe_then_discard_by_default() -> None:
    _, _, _, bridge = _wired()
    bridge.speak("audio:chat-question")
    u = bridge.get_usage()
    assert u["retained_now"] == 0 and u["diagnostic_retention"] is False and u["tts"] is False


def test_bridge_has_no_speech_out_capability() -> None:
    """I-V2/D-VOICE-02: voice input only — the bridge has no synthesis/speak/tts method (no TTS
    drift). Spoken answers remain OWED-BY-OPERATOR-DECISION (OP-8 §13.6), never faked."""
    _, _, _, bridge = _wired()
    assert not any(hasattr(bridge, m) for m in ("synthesize", "speak_out", "say", "tts", "answer_voice"))


def test_empty_transcript_fails_closed_to_clarify() -> None:
    _, _, sink, bridge = _wired()
    out = bridge.type_message("   ")
    assert out.kind is ConductorInputKind.CLARIFY
    assert sink.delivered == []


# -- least privilege: the sink cannot approve/execute -------------------------------------------

def test_chat_sink_is_submit_only() -> None:
    _, _, sink, _ = _wired()
    assert not hasattr(sink, "approve")
    assert not hasattr(sink, "execute")


# -- Phase 17D `.events`: a clarification the operator can SEE, and the pairing that makes it safe --

def test_a_clarified_utterance_reaches_the_operators_drawer() -> None:
    """Before 17D these branches refused the utterance correctly and then dropped it: the operator
    whose speech was not confidently heard had nothing to look at, though OP-7 s12.5 put
    clarifications in the one drawer. The refusal is unchanged; it is now visible."""
    broker, queue, sink, bridge = _wired()
    out = bridge.speak("audio:mumble")                       # confidence 0.35 < 0.6
    assert out.kind is ConductorInputKind.CLARIFY
    assert out.queue_item_id is not None                     # it is IN the drawer
    (row,) = queue.drawer_model()["pending"]
    assert row["kind"] == "clarification"
    assert row["approvable"] is False                        # a question, never approvable
    assert sink.delivered == []                              # still not delivered as chat
    assert not any(e["kind"] == "control_event" for e in broker.log())   # still never executed


def test_an_empty_transcript_clarifies_into_the_drawer_without_executing() -> None:
    broker, queue, sink, bridge = _wired()
    out = bridge.route_transcript("   ", "typed", None)
    assert out.kind is ConductorInputKind.CLARIFY
    assert queue.drawer_model()["badge_count"] == 1
    assert sink.delivered == []
    assert not any(e["kind"] == "control_event" for e in broker.log())


def test_a_router_may_not_clarify_above_its_brokers_bar() -> None:
    """The hole the spec-audit found in the branch above: a router clarifying at 0.9 over a broker
    clarifying at 0.5 would hand a 0.6-confidence SAFE verb to a broker that finds it confident
    enough - rule 4, executed. The pairing is refused at construction instead."""
    with pytest.raises(ConductorVoiceError):
        ConductorVoiceBridge(chat_sink=_RecordingSink(), broker=CommandBroker(confidence_threshold=0.5),
                             engine=_ScriptedSTT(), confidence_threshold=0.9)
    # the safe direction (a broker at least as strict as the router) is allowed
    ConductorVoiceBridge(chat_sink=_RecordingSink(), broker=CommandBroker(confidence_threshold=0.9),
                         engine=_ScriptedSTT(), confidence_threshold=0.6)


def test_a_clarify_branch_never_mints_a_control_event_for_a_safe_verb() -> None:
    """The property the constructor guard exists to hold, asserted end-to-end: a low-confidence SAFE
    verb (`status`) clarifies and mints nothing."""
    broker, queue, sink, bridge = _wired()
    out = bridge.route_transcript("status of the build", "voice", 0.2)
    assert out.kind is ConductorInputKind.CLARIFY
    assert not any(e["kind"] == "control_event" for e in broker.log())
    assert queue.drawer_model()["badge_count"] == 1
    assert sink.delivered == []
