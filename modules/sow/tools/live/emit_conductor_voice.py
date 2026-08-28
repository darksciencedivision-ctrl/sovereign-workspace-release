"""Conductor voice-IN feed emitter — Phase 16E `.engine` (directive §15 track 16E; OP-8 §13.5).

The shell's talk button must route captured operator speech through the REAL `ConductorVoiceBridge`
and surface the outcome (delivered chat / queued protected action / clarify) with a VISIBLE mock-engine
indicator — closing the READ half of U67. This emitter builds the engine-selected bridge over a REAL
`CommandBroker`, routes ONE captured utterance (an `--audio-ref` stand-in — real PCM is operator-run),
and prints its outcome folded into the stable `conductor_voice_feed@1.0` JSON the shell renders — the
SAME bounded `py -3.12` read-source pattern the 16B picker and the 16C/16D feeds use.

MOCK-FIRST, no live call (directive §6 / §10.4): the bridge runs the mock STT + a local broker, so
`--emit-conductor-voice` NEVER spawns a `claude`/`codex` process (§2.2/§2.4). NO TTS (I-V2/D-VOICE-02):
`tts:False` is carried through. Audio is transcribe-then-discard (invariant 26). Fail-closed
(invariant 3): any fault ⇒ the unavailable feed, a 0-exit JSON line the shell renders as "voice
unavailable", never a fabricated "delivered to the conductor".

`--emit-conductor-voice [--audio-ref <ref>]` prints ONLY the feed JSON (the stable shell contract, one
line).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Run as a script (`py -3.12 tools/live/emit_conductor_voice.py`) — put the repo root on sys.path
# exactly as the sibling emitters do so the shell can invoke this directly.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adapters.voice_parakeet.wsl_parakeet import seed_probe_result  # noqa: E402
from control_plane.orchestration.conductor_voice_feed import (  # noqa: E402
    DEFAULT_AUDIO_REF,
    VOICE_PROBE_FEED_SCHEMA,
    run_conductor_voice,
    run_voice_probe,
    unavailable_feed,
)


def _opt(argv: list[str], flag: str) -> str | None:
    """The value following `flag`, or None. Empty/whitespace values read as absent (fail-closed)."""
    if flag in argv:
        i = argv.index(flag)
        if i + 1 < len(argv) and argv[i + 1].strip():
            return argv[i + 1]
    return None


def _audio_ref(argv: list[str]) -> str:
    """Parse an optional `--audio-ref <ref>`. With `--real-capture` this is a real WAV PATH written by
    the shell from live microphone PCM; without it, a captured-utterance stand-in. Defaults to a
    SAFE-verb stand-in that the bridge delivers as ordinary CHAT."""
    return _opt(argv, "--audio-ref") or DEFAULT_AUDIO_REF


def _seed_engine_state(argv: list[str]) -> dict | None:
    """Phase 17C `.mic` (U134): accept the probe answer the SHELL already established.

    This process exits after one emission, so its probe cache is always cold; a real mic capture that
    had to re-probe would either pay 7–22 s on top of the transcription the operator is already waiting
    for, or (non-blocking) see `unprobed`, decline the real engine, and route real speech to the MOCK —
    U74's failure at the process seam. The shell's `VoiceProbe` maintains that answer; `--engine-state`
    is how it says so.

    ONLY a positive is honoured, and only as a cache seed: `seed_probe_result` cannot manufacture a
    transcript — the real adapter still performs the WSL round trip and still fails closed if NeMo is
    not there. Anything else (absent, `unavailable`, `unprobed`, a typo) falls through to a REAL
    blocking probe, which is the fail-closed direction: we re-establish the fact ourselves rather than
    trust a negative to suppress the real engine.
    """
    if (_opt(argv, "--engine-state") or "").strip().lower() != "available":
        return None
    reason = _opt(argv, "--engine-reason") or ""
    try:
        elapsed = float(_opt(argv, "--engine-elapsed-s") or 0.0)
    except (TypeError, ValueError):
        elapsed = 0.0
    result = seed_probe_result(True, reason, elapsed)
    return {"seeded": True, "reason": result.reason, "elapsed_s": result.elapsed_s}


def emit(audio_ref: str, *, real_capture: bool = False, seeded: dict | None = None) -> dict:
    """Route one utterance through the governed bridge and return the folded feed. `run_conductor_voice`
    is itself fail-closed; this only guards a parse/setup fault.

    Phase 17C `.probe`: on the STAND-IN path `blocking=False`. That ref carries no PCM, so
    `select_engine` ALWAYS lands on the mock here — a blocking WSL probe buys a strictly unused answer
    and charges the operator 7–22 s (up to the 90 s budget) for it on every talk press. The Python probe
    cache is module state in a process that exits after one emission, so it can never be warmed by the
    shell's background probe either. Engine AVAILABILITY is the shell-side `VoiceProbe`'s maintained
    fact; this feed reports the engine that handled THIS utterance and, on the non-blocking read, an
    honest `nemo_state:"unprobed"` rather than a fresh (and unused) verdict.

    Phase 17C `.mic`: with `--real-capture` the ref is a real WAV of the operator's speech, so the real
    engine is both reachable and REQUIRED — `for_capture=True`, and `blocking=True` so that a host
    whose answer was not seeded establishes it properly instead of silently mocking real speech. A
    seeded answer makes that blocking read a cache hit (no WSL spawn).
    """
    try:
        if real_capture:
            feed = run_conductor_voice(audio_ref, for_capture=True, blocking=True)
        else:
            feed = run_conductor_voice(audio_ref, blocking=False)
        # Observable, never load-bearing: a reader can always see whether this emission's engine answer
        # was established here or handed in (and the capture path is distinguishable from the poll).
        feed["real_capture"] = bool(real_capture)
        feed["engine_state_seeded"] = seeded if seeded else None
        return feed
    except Exception as exc:  # noqa: BLE001 — even a setup fault is reported, never faked
        return unavailable_feed(f"{type(exc).__name__}: {exc}", audio_ref=audio_ref)


def emit_probe(*, blocking: bool, force: bool) -> dict:
    """Phase 17C `.probe` (U74): the ENGINE-STATE-ONLY emission. No bridge, no broker, no transcript —
    its only cost is the WSL probe, so the shell can run it OFF its always-visible chrome's path."""
    try:
        return run_voice_probe(blocking=blocking, force=force)
    except Exception as exc:  # noqa: BLE001 — even a setup fault is reported, never faked
        reason = f"{type(exc).__name__}: {exc}"
        return {"schema": VOICE_PROBE_FEED_SCHEMA, "sourced": False, "reason": reason,
                "engine": {"name": "unknown", "mock": True, "real_available": False, "probing": False,
                           "nemo_state": "unavailable", "probe": None, "real_engine": None,
                           "detection": {}, "reason": reason},
                "blocking": bool(blocking), "forced": bool(force), "tts": False}


def main(argv: list[str]) -> int:
    if "--emit-voice-probe" in argv:
        # `--cached-only` never spawns WSL (the instant read); `--force` re-takes the probe now.
        blocking = "--cached-only" not in argv
        sys.stdout.write(json.dumps(emit_probe(blocking=blocking, force="--force" in argv), default=str) + "\n")
        return 0
    if "--emit-conductor-voice" in argv:
        real_capture = "--real-capture" in argv
        # Seed BEFORE routing: `select_engine` reads the cache during `run_conductor_voice`.
        seeded = _seed_engine_state(argv) if real_capture else None
        feed = emit(_audio_ref(argv), real_capture=real_capture, seeded=seeded)
        sys.stdout.write(json.dumps(feed, default=str) + "\n")
        return 0
    sys.stderr.write(
        "usage: emit_conductor_voice.py --emit-conductor-voice [--audio-ref <ref>]\n"
        "            [--real-capture [--engine-state available --engine-reason <text>\n"
        "             --engine-elapsed-s <n>]]\n"
        "  prints the governed conductor_voice_feed@1.0 JSON the shell renders (Phase 16E .engine).\n"
        "  --real-capture says <ref> is a real WAV of operator speech: the REAL engine is selected and\n"
        "  the probe is blocking (Phase 17C .mic). --engine-state available seeds the probe cache with\n"
        "  the answer the shell already established, so the capture pays for no second WSL import\n"
        "  (U134); it can never fabricate a transcript — the WSL round trip still fails closed.\n"
        "   or: emit_conductor_voice.py --emit-voice-probe [--cached-only] [--force]\n"
        "  prints voice_probe_feed@1.0 — the STT engine state alone (Phase 17C .probe, U74).\n"
    )
    return 2


if __name__ == "__main__":  # pragma: no cover - exercised via tests calling main()
    raise SystemExit(main(sys.argv[1:]))
