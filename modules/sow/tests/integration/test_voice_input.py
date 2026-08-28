"""Phase 12 §2.8 voice acceptance matrix (STT-only): PTT transcription; low-confidence ->
clarification; destructive -> approval queue; typed/voice control-event equivalence; voice
cannot instantiate nodes or expand permissions; offline network=none; no TTS."""
from __future__ import annotations

import pytest

from adapters.voice_parakeet import VoiceAdapter, detect_voice_stack, real_parakeet_available
from adapters.voice_parakeet.engine import MockSTT
from control_plane.policy import Identity
from voice_bridge.command_broker import CommandBroker, Disposition, ProposedCommand

OPERATOR = Identity("op", "operator", "proj")
WORKER = Identity("w", "worker", "proj")


def _wired(**kw):
    broker = CommandBroker()
    # the adapter gets a SUBMIT-ONLY handle: it structurally cannot approve/execute
    return broker, VoiceAdapter(broker.as_proposer(), MockSTT(), **kw)


def test_ptt_transcribes_and_executes_a_safe_command() -> None:
    broker, voice = _wired()
    voice.start_capture()
    out = voice.propose_command("audio:focus-pane-3")
    voice.stop_capture()
    assert out.disposition is Disposition.EXECUTED
    assert out.control_event.verb == "focus" and out.control_event.target == "pane 3"


def test_low_confidence_requires_clarification_not_execution() -> None:
    broker, voice = _wired()
    out = voice.propose_command("audio:mumble")  # confidence 0.35 < 0.6
    assert out.disposition is Disposition.CLARIFY and out.control_event is None


def test_destructive_command_routes_to_approval_queue() -> None:
    broker, voice = _wired()
    out = voice.propose_command("audio:terminate-node-b")
    assert out.disposition is Disposition.APPROVAL_QUEUED and out.control_event is None
    assert out.pending_id in broker.pending()
    # nothing executed until the operator approves
    assert not any(e["kind"] == "control_event" for e in broker.log())
    ev = broker.approve(out.pending_id, OPERATOR)
    assert ev.verb == "terminate" and ev.target == "node-b"


def test_voice_cannot_instantiate_a_node() -> None:
    broker, voice = _wired()
    out = voice.propose_command("audio:spawn-worker")  # spawn is PROTECTED
    assert out.disposition is Disposition.APPROVAL_QUEUED  # never auto-executed from voice
    assert not any(e["kind"] == "control_event" for e in broker.log())


def test_voice_cannot_expand_permissions() -> None:
    broker, voice = _wired()
    out = voice.propose_command("audio:grant-admin")  # grant is PROTECTED
    assert out.disposition is Disposition.APPROVAL_QUEUED
    assert not any(e["kind"] == "control_event" for e in broker.log())


def test_typed_and_voice_produce_equivalent_control_events() -> None:
    broker, voice = _wired()
    voice_out = voice.propose_command("audio:focus-pane-3")           # voice path
    typed_out = broker.submit(ProposedCommand(source="typed", verb="focus", target="pane 3"))  # typed path
    assert voice_out.disposition is typed_out.disposition is Disposition.EXECUTED
    # identical semantics (verb/target/args); only id/ts/source differ
    assert voice_out.control_event.semantic_key() == typed_out.control_event.semantic_key()
    assert voice_out.control_event.source == "voice" and typed_out.control_event.source == "typed"


def test_transcribe_then_discard_by_default() -> None:
    broker, voice = _wired()  # diagnostic_retention defaults OFF
    voice.propose_command("audio:show-status")
    assert voice.retained_count() == 0
    u = voice.get_usage()
    assert u["discarded"] == 1 and u["retained"] == 0 and u["diagnostic_retention"] is False


def test_diagnostic_retention_is_bounded_and_purges_at_ttl() -> None:
    broker, voice = _wired(diagnostic_retention=True, retention_ttl_s=100)
    voice.transcribe("audio:show-status")
    assert voice.retained_count() == 1
    assert voice.purge_expired(now=_far_future()) == 1  # TTL purge
    assert voice.retained_count() == 0


def test_offline_profile_network_none_and_no_tts() -> None:
    broker, voice = _wired(network="none")
    u = voice.get_usage()
    assert u["network"] == "none"   # offline profile: audio never egresses
    assert u["tts"] is False        # STT-only, no speech synthesis
    # the adapter has no synthesis/speak method by construction (no TTS drift)
    assert not any(hasattr(voice, m) for m in ("synthesize", "speak", "say", "tts"))


def test_approve_requires_operator_identity() -> None:
    """F1: executing a queued destructive/protected command requires the OPERATOR — a
    non-operator identity is refused (invariant 1, no self-authorization)."""
    broker, voice = _wired()
    out = voice.propose_command("audio:terminate-node-b")
    with pytest.raises(PermissionError, match="only the operator"):
        broker.approve(out.pending_id, WORKER)
    assert out.pending_id in broker.pending()  # still queued, not executed
    ev = broker.approve(out.pending_id, OPERATOR)  # operator can
    assert ev.verb == "terminate"


def test_operator_can_reject_a_queued_command() -> None:
    """F6: the operator can decline a queued command (not stuck-or-execute); worker cannot."""
    broker, voice = _wired()
    out = voice.propose_command("audio:spawn-worker")
    with pytest.raises(PermissionError):
        broker.reject(out.pending_id, WORKER)
    broker.reject(out.pending_id, OPERATOR, reason="not now")
    assert out.pending_id not in broker.pending()
    assert not any(e["kind"] == "control_event" for e in broker.log())


def test_voice_adapter_has_no_execute_or_approve_capability() -> None:
    """F2: the transducer holds a submit-only handle — it structurally cannot approve/execute."""
    broker, voice = _wired()
    assert not hasattr(voice._proposer, "approve")
    assert not hasattr(voice._proposer, "_execute")


def test_synonym_maps_to_destructive_and_queues() -> None:
    """A spoken synonym ('stop' -> terminate) escalates to the destructive queue, never a safe
    execute (the escalation table only maps toward more-restrictive verbs)."""
    broker, voice = _wired()
    out = voice.propose_command("audio:stop-node")
    assert out.disposition is Disposition.APPROVAL_QUEUED
    assert not any(e["kind"] == "control_event" for e in broker.log())


def test_voice_command_with_no_confidence_fails_closed_to_clarify() -> None:
    """F3: a voice proposal with absent confidence is treated as ambiguous, not executed."""
    broker = CommandBroker()
    out = broker.submit(ProposedCommand(source="voice", verb="focus", target="pane 3", confidence=None))
    assert out.disposition is Disposition.CLARIFY


def test_double_approve_is_refused() -> None:
    broker, voice = _wired()
    out = voice.propose_command("audio:terminate-node-b")
    broker.approve(out.pending_id, OPERATOR)
    with pytest.raises(KeyError):
        broker.approve(out.pending_id, OPERATOR)  # no double execution


def test_typed_case_and_punctuation_variants_are_equivalent() -> None:
    """F5: broker-side canonicalization makes 'Focus  Pane 3' (typed, mixed case/spacing)
    equivalent to the voice form 'focus pane 3' — equivalence doesn't depend on each caller
    normalizing. (Hyphen vs space stays a real distinction: node-B != node B.)"""
    broker, voice = _wired()
    v = voice.propose_command("audio:focus-pane-3")
    t = broker.submit(ProposedCommand(source="typed", verb="Focus", target="Pane  3"))
    assert v.control_event.semantic_key() == t.control_event.semantic_key()


def test_voice_stack_detection_recorded() -> None:
    d = detect_voice_stack()
    # Phase 17C `.probe` (U74) adds `nemo_state` + `probe`: `nemo` alone could not express "not asked
    # yet", so an unanswered probe had to be reported as False — which the chrome drew as "mock engine"
    # on a host with Parakeet installed (finding F1).
    assert set(d) == {"nvidia_gpu", "wsl", "nemo", "nemo_state", "probe"}
    assert d["nemo"] is (d["nemo_state"] == "available")   # fail-closed: only a positive probe is "yes"
    # Phase 16E `.real`: `nemo` is probed INSIDE WSL (not a host `import nemo`, which is always false).
    # Whatever the host reports, real-availability is exactly the conjunction — never claimed otherwise.
    assert real_parakeet_available(d) == (d["nvidia_gpu"] and d["wsl"] and d["nemo"])
    assert real_parakeet_available() == real_parakeet_available(d)  # self-detects the same dict


def _far_future() -> float:
    import time
    return time.time() + 10_000
