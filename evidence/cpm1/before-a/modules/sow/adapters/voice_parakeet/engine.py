"""Voice STT engine (Plan §2.4, Track G; I-A1). Mock by default; real Parakeet/NeMo only when
the NVIDIA GPU + WSL + NeMo stack is detected. Agnosticism lives in this interface, not the
engine — a future CPU/non-NVIDIA STT drops in behind the same contract. NO TTS (STT-only).
"""
from __future__ import annotations

import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

#: Non-blocking NeMo probe states, mirrored from `wsl_parakeet` so this module (which `wsl_parakeet`
#: imports) can name them without importing back into it. Kept as literals for that reason; the
#: `test_probe_state_names_match` test pins the two definitions together.
PROBE_AVAILABLE = "available"
PROBE_UNAVAILABLE = "unavailable"
PROBE_UNPROBED = "unprobed"


@dataclass(frozen=True)
class Transcript:
    text: str
    confidence: float


@runtime_checkable
class STTEngine(Protocol):
    name: str

    def transcribe(self, audio_ref: str) -> Transcript: ...


def detect_voice_stack(*, blocking: bool = True, force: bool = False) -> dict[str, Any]:
    """Detection only — never installs. Records what the host offers so the mock-vs-real choice
    (and its limits) are honest.

    Phase 16E `.real` fix (OP-10 host-fact defect): NeMo is probed *inside WSL2* (a timeout-bounded
    `wsl.exe` import check), NOT via a HOST `import nemo` — the latter is structurally always false here
    because NeMo lives in the WSL venv and Windows has no MSVC to build its stack, so real Parakeet was
    never selected even when installed. The WSL probe is fail-closed: no WSL, no venv, a non-zero exit,
    or a timeout each read as `nemo:false`.

    Phase 17C `.probe` (U74) adds the THIRD answer the pre-U74 shape could not express. `nemo` is a
    boolean, so "we have not asked yet" had to be reported as False — which the chrome drew as "mock
    engine" on a host with Parakeet installed (finding F1). So detection now also carries
    **`nemo_state`**: `available` / `unavailable` / `unprobed`, and callers that must not block
    (the always-visible indicator poll) pass `blocking=False` to get the cached answer or `unprobed`
    WITHOUT spawning WSL. `nemo` stays fail-closed — True only for a real, positive probe.

    `force=True` re-probes now, ignoring the cache (the "re-probe on demand / after failure" path).
    """
    has_wsl = shutil.which("wsl") is not None
    # Lazy import breaks the import cycle (wsl_parakeet imports Transcript/STTEngine from this module).
    nemo_state = PROBE_UNAVAILABLE if not has_wsl else PROBE_UNPROBED
    probe: dict[str, Any] | None = None
    if has_wsl:
        from adapters.voice_parakeet import wsl_parakeet as wp
        if blocking:
            result = wp.probe_nemo() if force else _blocking_probe(wp)
            nemo_state, probe = result.state, result.as_dict()
        else:
            cached = wp.cached_probe()
            nemo_state = wp.PROBE_UNPROBED if cached is None else cached.state
            probe = cached.as_dict() if cached is not None else None
    return {
        "nvidia_gpu": shutil.which("nvidia-smi") is not None,
        "wsl": has_wsl,
        # fail-closed: `nemo` is True ONLY for a positive probe — `unprobed` is never "yes".
        "nemo": nemo_state == PROBE_AVAILABLE,
        "nemo_state": nemo_state,
        "probe": probe,
    }


def _blocking_probe(wp: Any) -> Any:
    """Take the cached probe if it is still fresh, else run a real one. (Split out so `detect_voice_stack`
    reads as the three-branch decision it is, and so the cache path is directly testable.)"""
    cached = wp.cached_probe()
    return cached if cached is not None else wp.probe_nemo()


def real_parakeet_available(detection: Mapping[str, Any] | None = None) -> bool:
    """True iff the full real stack is present (`nvidia_gpu ∧ wsl ∧ nemo`). Accepts a pre-computed
    `detection` dict to avoid re-probing WSL when the caller already has one. Fail-closed: an UNPROBED
    host is not "available" — but it is not "mock engine" either, which is why callers must read
    `nemo_state` (or `real_parakeet_pending`) rather than inferring absence from this False."""
    d = detection if detection is not None else detect_voice_stack()
    return bool(d.get("nvidia_gpu") and d.get("wsl") and d.get("nemo"))


def real_parakeet_pending(detection: Mapping[str, Any] | None = None) -> bool:
    """True iff the real stack COULD still turn out to be present — the host has WSL but the NeMo probe
    has not answered yet. This is the state that must render "probing…", never "mock engine" (U74/F1)."""
    d = detection if detection is not None else detect_voice_stack(blocking=False)
    return bool(d.get("wsl")) and d.get("nemo_state") == PROBE_UNPROBED


class MockSTT:
    """Deterministic STT for the test suite (transcribe-then-discard path exercised without
    audio hardware). The audio_ref is a stand-in for captured PCM: the mock maps a small set of
    scripted refs to (text, confidence); anything else is a low-confidence mumble."""
    name = "mock-stt"

    _SCRIPT = {
        "audio:focus-pane-3": ("focus pane 3", 0.97),
        "audio:show-status": ("show status", 0.95),
        "audio:terminate-node-b": ("terminate node-B", 0.93),
        "audio:spawn-worker": ("spawn worker", 0.9),
        "audio:mumble": ("uh something something", 0.35),
        "audio:grant-admin": ("grant admin to worker-A", 0.9),
        "audio:stop-node": ("stop node-B", 0.9),          # 'stop' synonym -> terminate (destructive)
    }

    def transcribe(self, audio_ref: str) -> Transcript:
        text, conf = self._SCRIPT.get(audio_ref, ("unintelligible", 0.3))
        return Transcript(text=text, confidence=conf)
