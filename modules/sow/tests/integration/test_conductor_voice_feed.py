"""Conductor voice-IN feed tests — Phase 16E `.engine` (directive §15 track 16E; OP-8 §13.5).

The engine-selected read half of U67: route ONE captured utterance through the REAL
`ConductorVoiceBridge` over a REAL `CommandBroker` (mock-first, no live call) and fold the outcome into
`conductor_voice_feed@1.0` with a VISIBLE mock-engine indicator. These tests pin the three routing
outcomes (chat delivered / protected queued / low-confidence clarify), the engine honesty (mock, never
a claimed real engine on this host), NO TTS, transcribe-then-discard, and the fail-closed feed.

Mirrors the Phase-15E bridge tests (`tests/integration/test_conductor_voice.py`) but asserts the FEED
the shell renders, not the raw bridge outcome.
"""
from __future__ import annotations

import json

from adapters.voice_parakeet.engine import MockSTT, real_parakeet_available
from control_plane.orchestration.conductor_voice_feed import (
    CONDUCTOR_VOICE_FEED_SCHEMA,
    DEFAULT_AUDIO_REF,
    VOICE_PROBE_FEED_SCHEMA,
    fold_conductor_voice_feed,
    run_conductor_voice,
    run_voice_probe,
    select_engine,
    unavailable_feed,
)
from tools.live import emit_conductor_voice


# Detection dicts stand in for a host. Phase 17C `.probe` (U74) adds `nemo_state`: the probe's OWN
# answer, so "not installed" (answered no) and "not asked yet" are different facts to every reader.
_ALL = {"nvidia_gpu": True, "wsl": True, "nemo": True, "nemo_state": "available"}   # full real stack
_NONE = {"nvidia_gpu": True, "wsl": True, "nemo": False, "nemo_state": "unavailable"}  # NeMo absent


class _FakeReal:
    name = "parakeet-wsl"

    def transcribe(self, audio_ref):  # noqa: ANN001, ANN201
        from adapters.voice_parakeet.engine import Transcript
        return Transcript(text="focus pane 3", confidence=1.0)


# ---- engine selection (the VISIBLE mock/real indicator; never a silent pretend-to-hear) -----------
def test_select_engine_standin_stays_mock_but_reports_real_available() -> None:
    # The headless indicator poll (for_capture=False) carries no PCM, so even on a real-stack host the
    # transcript is the mock's — mock:True — but real_available is reported TRUTHFULLY so the indicator
    # renders "ready" (never a claimed real transcript, never a hidden "voice is still mock").
    eng, info = select_engine(detection=_ALL)
    assert isinstance(eng, MockSTT)
    assert info["mock"] is True and info["real_available"] is True
    assert info["real_engine"] == "parakeet-wsl"
    assert "16F" in info["reason"] and "mock STT" in info["reason"]


def test_select_engine_standin_names_the_standin_as_the_cause_whatever_the_probe_says() -> None:
    """The stand-in's reason must name the OPERATIVE cause, not the probe's state (spec-audit m3).

    Measured in the 17E composition receipt: the protected-verb leg runs in a fresh `py` child, so the
    NeMo probe starts cold and answered `unprobed`. The old branch order reported that as the reason —
    "the real engine may still be available" — inside a receipt whose own capture leg had transcribed
    real PCM on the real engine ninety seconds earlier. The engine state never decided this path: a
    scripted ref carries no PCM, so no real engine could have transcribed it either way.
    """
    unprobed = {**_ALL, "nemo": False, "nemo_state": "unprobed"}
    _, info = select_engine(detection=unprobed)
    assert info["mock"] is True and info["probing"] is True
    assert "carries no PCM" in info["reason"]
    assert info["reason"].index("carries no PCM") < info["reason"].index("probe")
    assert "did not decide this path" in info["reason"]
    # the probe's state is still reported — as context, and without claiming it caused anything
    assert "may still be available" not in info["reason"]


def test_select_engine_uses_real_for_capture_when_available() -> None:
    eng, info = select_engine(for_capture=True, detection=_ALL, real_engine_factory=_FakeReal)
    assert isinstance(eng, _FakeReal)               # real engine selected for a real capture
    assert info["mock"] is False and info["real_available"] is True
    assert info["name"] == "parakeet-wsl" and "real engine" in info["reason"]


def test_select_engine_falls_back_to_mock_when_real_adapter_init_fails() -> None:
    def _boom():
        raise RuntimeError("no venv")
    eng, info = select_engine(for_capture=True, detection=_ALL, real_engine_factory=_boom)
    assert isinstance(eng, MockSTT)                 # fail-closed to the VISIBLE mock
    assert info["mock"] is True and "failed to initialise" in info["reason"]


def test_select_engine_is_mock_when_no_real_stack() -> None:
    eng, info = select_engine(for_capture=True, detection=_NONE)
    assert isinstance(eng, MockSTT)
    assert info["mock"] is True and info["real_available"] is False and info["real_engine"] is None
    assert "missing: nemo" in info["reason"]


def test_select_engine_matches_host_detection_shape() -> None:
    _, info = select_engine()
    assert info["real_available"] is real_parakeet_available(info["detection"])
    # Phase 17C `.probe` (U74): detection carries the probe's own state + record, so the shell can
    # distinguish "no real engine" from "not asked yet".
    assert set(info["detection"]) == {"nvidia_gpu", "wsl", "nemo", "nemo_state", "probe"}
    assert info["probing"] is False or info["real_available"] is False  # never both


def test_an_unanswered_probe_is_probing_not_mock() -> None:
    """U74/F1 in one assertion: with WSL present and the NeMo probe UNANSWERED, the engine descriptor
    must say `probing`, and must NOT report the real engine as absent. Rendering this state as "mock
    engine" is the lie the operator saw on a host where Parakeet is installed."""
    unprobed = {"nvidia_gpu": True, "wsl": True, "nemo": False, "nemo_state": "unprobed", "probe": None}
    _eng, info = select_engine(for_capture=True, detection=unprobed)
    assert info["probing"] is True and info["real_available"] is False
    assert info["nemo_state"] == "unprobed"
    assert "PROBING" in info["reason"]
    assert "not present on host" not in info["reason"]   # never asserts a negative it has not established


def test_an_answered_negative_probe_is_mock_and_says_why() -> None:
    answered = {"nvidia_gpu": True, "wsl": True, "nemo": False, "nemo_state": "unavailable",
                "probe": {"state": "unavailable", "available": False, "reason": "the NeMo ASR import exited 1",
                          "elapsed_s": 1.5, "timeout_s": 90.0}}
    _eng, info = select_engine(for_capture=True, detection=answered)
    assert info["probing"] is False and info["real_available"] is False
    assert "exited 1" in info["reason"]                  # the operator is told what actually failed


def test_injected_engine_is_honored() -> None:
    eng, info = select_engine(MockSTT())
    assert isinstance(eng, MockSTT)
    assert info["mock"] is True


def test_run_conductor_voice_with_a_real_engine_folds_mock_false(monkeypatch) -> None:
    # a real engine producing the transcript, on a real-stack host ⇒ the feed folds engine.mock:False
    # (a genuine real transcript). Deterministic via a forced full-stack detection.
    import control_plane.orchestration.conductor_voice_feed as feed_mod

    class _RealChat:
        name = "parakeet-wsl"

        def transcribe(self, audio_ref):  # noqa: ANN001, ANN201
            from adapters.voice_parakeet.engine import Transcript
            return Transcript(text="hello there", confidence=1.0)

    monkeypatch.setattr(feed_mod, "detect_voice_stack", lambda **_kw: dict(_ALL))
    feed = run_conductor_voice("audio:whatever", engine=_RealChat())
    assert feed["engine"]["mock"] is False and feed["engine"]["real_available"] is True
    assert feed["delivered"] is True and feed["delivered_text"] == "hello there"


# ---- the three routing outcomes, as the shell FEED ------------------------------------------------
def test_ordinary_speech_folds_to_a_delivered_chat_feed() -> None:
    feed = run_conductor_voice("audio:show-status")   # "show status" — a SAFE verb → ordinary chat
    assert feed["schema"] == CONDUCTOR_VOICE_FEED_SCHEMA
    assert feed["sourced"] is True
    assert feed["outcome"]["kind"] == "chat"
    assert feed["delivered"] is True
    assert feed["delivered_text"] == "show status"    # only ever the text the bridge actually routed
    assert feed["outcome"]["source"] == "voice"
    # the recording sink saw the delivery — the stand-in for the live conductor ConPTY write
    assert feed["deliveries"] == [{"text": "show status", "source": "voice", "semantic_key": "show status"}]
    assert feed["queued"] is False and feed["needs_clarification"] is False


def test_destructive_speech_folds_to_a_queued_feed_never_delivered() -> None:
    feed = run_conductor_voice("audio:terminate-node-b")  # destructive → propose→approve (invariant 25)
    assert feed["outcome"]["kind"] == "proposed_action"
    assert feed["queued"] is True
    assert feed["delivered"] is False
    assert feed["delivered_text"] is None             # never delivered as chat
    assert feed["deliveries"] == []                   # nothing written toward the conductor
    assert feed["outcome"]["queue_item_id"]            # surfaced in the approval drawer


def test_protected_grant_folds_to_a_queued_feed() -> None:
    feed = run_conductor_voice("audio:grant-admin")   # 'grant' is PROTECTED → queued, never inline
    assert feed["outcome"]["kind"] == "proposed_action"
    assert feed["queued"] is True and feed["delivered"] is False


def test_low_confidence_speech_folds_to_a_clarify_feed() -> None:
    feed = run_conductor_voice("audio:mumble")        # 0.35 < 0.6 threshold → clarify, fail closed
    assert feed["outcome"]["kind"] == "clarify"
    assert feed["needs_clarification"] is True
    assert feed["delivered"] is False and feed["queued"] is False
    assert feed["delivered_text"] is None


def test_unknown_audio_ref_fails_closed_to_clarify() -> None:
    feed = run_conductor_voice("audio:not-a-real-ref")  # MockSTT → ("unintelligible", 0.3) → clarify
    assert feed["outcome"]["kind"] == "clarify"
    assert feed["needs_clarification"] is True


# ---- honesty invariants carried on every feed -----------------------------------------------------
def test_feed_engine_is_visibly_mock() -> None:
    feed = run_conductor_voice(DEFAULT_AUDIO_REF)
    assert feed["engine"]["mock"] is True
    assert feed["engine"]["name"] == "mock-stt"
    assert "detection" in feed["engine"] \
        and set(feed["engine"]["detection"]) == {"nvidia_gpu", "wsl", "nemo", "nemo_state", "probe"}


def test_no_tts_and_transcribe_then_discard() -> None:
    feed = run_conductor_voice("audio:show-status")
    assert feed["tts"] is False                       # I-V2/D-VOICE-02 — STT-only, no synthesis
    assert feed["transcribe_then_discard"] is True    # invariant 26 — audio discarded (retained_now 0)
    assert feed["torn_down"] is True                  # bridge/adapter closed before the feed


def test_every_feed_records_the_owed_live_capture() -> None:
    feed = run_conductor_voice("audio:show-status")
    assert feed["live_capture_owed"]["owed"] is True
    assert feed["live_capture_owed"]["issue"] == "16F"


# ---- fail-closed --------------------------------------------------------------------------------
def test_unavailable_feed_is_honest_and_never_claims_delivery() -> None:
    feed = unavailable_feed("BoomError: kaboom", audio_ref="audio:x")
    assert feed["sourced"] is False
    assert feed["reason"] == "BoomError: kaboom"
    assert feed["delivered"] is False and feed["delivered_text"] is None
    assert feed["outcome"]["kind"] == "clarify"       # a fault reads as "repeat", never "delivered"
    assert feed["engine"]["mock"] is True             # never a claimed real engine on a fault
    assert feed["tts"] is False


def test_run_conductor_voice_wraps_a_faulty_engine_fail_closed() -> None:
    class _Boom:
        name = "boom-stt"

        def transcribe(self, audio_ref: str):  # noqa: ANN201
            raise RuntimeError("engine exploded")

    feed = run_conductor_voice("audio:show-status", engine=_Boom())
    assert feed["sourced"] is False
    assert "RuntimeError" in feed["reason"]
    assert feed["delivered"] is False


def test_fold_is_pure_and_derives_delivered_text_only_from_chat() -> None:
    # a PROPOSED_ACTION outcome must never fold a delivered_text even if a chat_message were attached
    from voice_bridge.conductor_voice import ConductorInputKind, ConductorInputOutcome

    outcome = ConductorInputOutcome(
        kind=ConductorInputKind.PROPOSED_ACTION, source="voice", text="terminate node-B",
        confidence=0.93, queue_item_id="ap-x", reason="queued")
    feed = fold_conductor_voice_feed(
        outcome, engine_info={"name": "mock-stt", "mock": True, "real_available": False,
                              "detection": {}, "reason": "mock"},
        usage={"tts": False, "retained_now": 0}, deliveries=[], audio_ref="audio:terminate-node-b")
    assert feed["delivered"] is False and feed["delivered_text"] is None
    assert feed["queued"] is True and feed["outcome"]["queue_item_id"] == "ap-x"


# ---- the emitter (the exact one-line contract the shell parses) -----------------------------------
def test_emit_prints_one_json_line_for_a_chat_utterance(capsys) -> None:
    rc = emit_conductor_voice.main(["--emit-conductor-voice", "--audio-ref", "audio:show-status"])
    assert rc == 0
    out = capsys.readouterr().out
    assert out.endswith("\n") and out.count("\n") == 1
    feed = json.loads(out)
    assert feed["schema"] == CONDUCTOR_VOICE_FEED_SCHEMA
    assert feed["delivered"] is True and feed["delivered_text"] == "show status"
    assert feed["engine"]["mock"] is True and feed["tts"] is False


def test_emit_defaults_the_audio_ref(capsys) -> None:
    rc = emit_conductor_voice.main(["--emit-conductor-voice"])
    assert rc == 0
    feed = json.loads(capsys.readouterr().out)
    assert feed["audio_ref"] == DEFAULT_AUDIO_REF
    assert feed["sourced"] is True


def test_emit_usage_on_no_flag(capsys) -> None:
    rc = emit_conductor_voice.main([])
    assert rc == 2
    assert "emit-conductor-voice" in capsys.readouterr().err


# ---- Phase 17C `.probe` (U74): the engine-state-only feed ------------------------------------------
def test_probe_feed_is_engine_state_only_and_never_routes() -> None:
    """The probe emission exists so the shell can learn the engine state WITHOUT paying for a bridge, a
    broker and a transcript — its only cost is the WSL probe. That is what makes running it off the
    always-visible chrome's path possible, which is what makes the 90 s budget safe."""
    probe = run_voice_probe(blocking=False)
    assert probe["schema"] == VOICE_PROBE_FEED_SCHEMA
    assert "outcome" not in probe and "delivered" not in probe   # it routes nothing and claims nothing
    assert probe["tts"] is False                                  # I-V2/D-VOICE-02, carried everywhere


def test_probe_feed_cached_only_never_spawns_wsl(monkeypatch) -> None:
    """`--cached-only` is the INSTANT read. If it could spawn, the shell's "non-blocking" state would be
    a lie and the always-visible chrome could stall for the whole probe budget."""
    import adapters.voice_parakeet.wsl_parakeet as wp
    wp.reset_probe_cache()
    spawned: list[tuple] = []
    monkeypatch.setattr(wp, "_default_runner", lambda *a, **k: spawned.append(a))
    probe = run_voice_probe(blocking=False)
    assert spawned == []
    if probe["engine"]["detection"].get("wsl"):    # host-dependent: only meaningful where WSL exists
        assert probe["engine"]["nemo_state"] == "unprobed"
        assert probe["engine"]["probing"] is True
        assert probe["engine"]["real_available"] is False   # fail-closed — unprobed is never "yes"
    wp.reset_probe_cache()


def test_probe_emitter_prints_one_json_line(capsys) -> None:
    rc = emit_conductor_voice.main(["--emit-voice-probe", "--cached-only"])
    assert rc == 0
    out = capsys.readouterr().out
    assert out.endswith("\n") and out.count("\n") == 1
    feed = json.loads(out)
    assert feed["schema"] == VOICE_PROBE_FEED_SCHEMA and feed["sourced"] is True
    assert feed["blocking"] is False and feed["forced"] is False
    assert set(feed["engine"]) >= {"mock", "real_available", "probing", "nemo_state", "detection"}


def test_the_probe_feed_never_claims_a_transcript_even_when_the_engine_is_available(monkeypatch) -> None:
    """CONTRACT-level honesty. `mock` answers "did a mock produce the transcript?" and a probe produces
    NO transcript, so it is True whatever the probe found — otherwise the shared render model draws the
    REAL state ("parakeet-wsl") and asserts a transcription that never happened. This lived only in the
    JS consumer until the spec audit of this unit; a single new consumer would have made it an
    operator-visible false claim."""
    import control_plane.orchestration.conductor_voice_feed as mod
    monkeypatch.setattr(mod, "detect_voice_stack", lambda **_kw: dict(_ALL))
    feed = run_voice_probe()
    assert feed["engine"]["real_available"] is True      # what the probe DID establish
    assert feed["engine"]["mock"] is True                # …and what it did not
    assert feed["engine"]["name"] == "parakeet-wsl"


def test_probe_emitter_usage_names_both_modes(capsys) -> None:
    assert emit_conductor_voice.main([]) == 2
    assert "emit-voice-probe" in capsys.readouterr().err


def test_probe_feed_fails_closed_without_claiming_an_engine(monkeypatch) -> None:
    import control_plane.orchestration.conductor_voice_feed as mod

    def _boom(**_kw):
        raise RuntimeError("wsl gone")

    monkeypatch.setattr(mod, "select_engine", _boom)
    feed = run_voice_probe()
    assert feed["sourced"] is False and "wsl gone" in feed["reason"]
    assert feed["engine"]["real_available"] is False and feed["engine"]["mock"] is True
    assert feed["engine"]["probing"] is False       # a FAULT is an answer — it is not "still asking"
