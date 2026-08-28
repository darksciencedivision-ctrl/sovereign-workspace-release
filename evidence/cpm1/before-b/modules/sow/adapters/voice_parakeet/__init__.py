"""Voice Input Service adapter (NVIDIA Parakeet, STT-only; I-V1..V3). Mock engine by default;
real Parakeet/NeMo when the GPU+WSL+NeMo stack is present (probed inside WSL — Phase 16E `.real`)."""
from adapters.voice_parakeet.adapter import VoiceAdapter
from adapters.voice_parakeet.engine import (
    MockSTT,
    STTEngine,
    Transcript,
    detect_voice_stack,
    real_parakeet_available,
    real_parakeet_pending,
)
from adapters.voice_parakeet.wsl_parakeet import (
    PARAKEET_WSL_NAME,
    PROBE_AVAILABLE,
    PROBE_PROBING,
    PROBE_UNAVAILABLE,
    PROBE_UNPROBED,
    ProbeResult,
    VoiceEngineError,
    WslConfig,
    WslParakeetSTT,
    build_real_engine,
    cached_probe,
    probe_nemo,
    probe_state,
    reset_probe_cache,
    wsl_nemo_available,
)

__all__ = [
    "VoiceAdapter", "MockSTT", "STTEngine", "Transcript",
    "detect_voice_stack", "real_parakeet_available", "real_parakeet_pending",
    "WslParakeetSTT", "WslConfig", "VoiceEngineError", "PARAKEET_WSL_NAME",
    "build_real_engine", "wsl_nemo_available",
    # Phase 17C `.probe` (U74): the non-blocking probe surface.
    "ProbeResult", "probe_nemo", "probe_state", "cached_probe", "reset_probe_cache",
    "PROBE_AVAILABLE", "PROBE_UNAVAILABLE", "PROBE_UNPROBED", "PROBE_PROBING",
]
