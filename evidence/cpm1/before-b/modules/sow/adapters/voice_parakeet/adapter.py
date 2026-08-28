"""Voice Input Service adapter — NVIDIA Parakeet, STT-only (Plan §2.4, §9.9; I-V1..V3).

A TRANSDUCER class, not a reasoning node: it converts operator speech into PROPOSED control
commands that enter the same command bus as typed input. It never auto-executes anything
(propose_command → broker → clarification/approval → logged control event). Audio is
transcribe-then-discard by default; an optional bounded, local-only, off-by-default diagnostic
retention keeps raw audio for a TTL then purges it. There is NO speech synthesis (no TTS) —
the interface has no such method by construction.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from adapters.voice_parakeet.engine import MockSTT, STTEngine, Transcript
from voice_bridge.command_broker import (
    DESTRUCTIVE_VERBS,
    PROTECTED_VERBS,
    Proposer,
    ProposedCommand,
)
from voice_bridge.spoken_verbs import split_spoken_command


@dataclass
class _RetainedAudio:
    audio_ref: str
    captured_ts: float


class VoiceAdapter:
    def __init__(self, proposer: Proposer, engine: STTEngine | None = None, *,
                 diagnostic_retention: bool = False, retention_ttl_s: int = 7 * 24 * 3600,
                 network: str = "none") -> None:
        # a SUBMIT-ONLY capability: the transducer structurally cannot approve/execute (I-V1/25)
        self._engine = engine or MockSTT()
        self._proposer = proposer
        self._capturing = False
        self._diag_retention = diagnostic_retention   # OFF by default
        self._ttl_s = retention_ttl_s
        self._network = network                        # "none" under the offline profile
        self._retained: list[_RetainedAudio] = []
        self._usage = {"utterances": 0, "discarded": 0, "retained": 0}

    # -- capture lifecycle (push-to-talk / trigger) ---------------------------
    def start_capture(self) -> None:
        self._capturing = True

    def stop_capture(self) -> None:
        self._capturing = False

    # -- transcription --------------------------------------------------------
    def transcribe(self, audio_ref: str) -> Transcript:
        self.purge_expired()  # auto-purge: TTL-expired diagnostic audio is dropped automatically
        t = self._engine.transcribe(audio_ref)
        self._usage["utterances"] += 1
        # audio retention policy: transcribe-then-discard by default (D-VOICE-04)
        if self._diag_retention:
            self._retained.append(_RetainedAudio(audio_ref, time.time()))
            self._usage["retained"] += 1
        else:
            self._usage["discarded"] += 1
        return t

    def stream_transcribe(self, audio_ref: str) -> Transcript:  # single-shot stub for the mock
        return self.transcribe(audio_ref)

    def get_confidence(self, audio_ref: str) -> float:
        return self._engine.transcribe(audio_ref).confidence

    # -- command proposal (never auto-executes) -------------------------------
    def propose_command(self, audio_ref: str) -> Any:
        """Transcribe → map to a candidate control command → submit to the broker. The adapter
        NEVER executes; the broker decides (clarify / approval queue / execute-as-control-event)."""
        t = self.transcribe(audio_ref)
        verb, target, args = self._map(t.text)
        proposed = ProposedCommand(source="voice", verb=verb, target=target, args=args,
                                   raw_text=t.text, confidence=t.confidence)
        return self._proposer.submit(proposed)  # submit-only: never executes

    @staticmethod
    def _map(text: str) -> tuple[str, str, dict[str, Any]]:
        # one shared normalization for both voice surfaces (voice_bridge.spoken_verbs) so a spoken
        # synonym escalates identically here and in the conductor voice bridge — no drift.
        verb, target = split_spoken_command(text, DESTRUCTIVE_VERBS | PROTECTED_VERBS)
        return (verb, target, {})

    # -- retention maintenance ------------------------------------------------
    def purge_expired(self, *, now: float | None = None) -> int:
        now = time.time() if now is None else now
        before = len(self._retained)
        self._retained = [r for r in self._retained if (now - r.captured_ts) < self._ttl_s]
        return before - len(self._retained)

    def retained_count(self) -> int:
        return len(self._retained)

    def get_usage(self) -> dict[str, Any]:
        return {**self._usage, "network": self._network, "diagnostic_retention": self._diag_retention,
                "retention_ttl_s": self._ttl_s, "local_only": True, "auto_purge": True,
                "retained_now": len(self._retained), "engine": self._engine.name, "tts": False}

    def close(self) -> None:
        self._capturing = False
        self._retained.clear()  # discard any retained audio on close
