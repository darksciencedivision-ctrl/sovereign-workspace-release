"""Real NVIDIA Parakeet STT adapter over WSL2 — Phase 16E `.real` (directive §15 track 16E; OP-10;
OP-9/§10.3 authorizes the NeMo stack). Closes the operator's host-fact defect: the mock-vs-real
detection probed `import nemo` in the HOST Windows interpreter (structurally always false — NeMo lives
in the WSL2 venv, and Windows has no MSVC to build its numpy stack), so real Parakeet was NEVER
selected even on a host where it is installed. This module probes NeMo *inside* WSL (timeout-bounded)
and routes transcription through the WSL venv interpreter, behind the same `STTEngine` contract the mock
implements (agnosticism lives in the interface — I-A1).

Honesty / fail-closed (invariant 3 / invariant 20 spirit; directive §15 track 16E — *"never silently
pretend to hear"*): a missing WSL, a missing venv/NeMo, a non-zero exit, a timeout, or malformed output
each read as "real Parakeet not available" (→ the visible mock, at the selection layer) or, for a
transcription fault, a raised `VoiceEngineError` the caller folds into the fail-closed feed — never a
fabricated transcript. STT-only (I-V2/D-VOICE-02): there is no synthesis method here by construction.
Audio is transcribe-then-discard (invariant 26): the adapter neither copies nor retains the WAV.

MOCK-FIRST still governs the headless read-source (`.engine`): the real engine is selected ONLY for a
real capture (`for_capture=True`) with a real WAV — the stand-in `audio:` refs the shell's indicator
poll uses carry no PCM and stay on the mock. No credentials, no network from this module (the WSL venv
was operator-installed per docs/OPERATOR_NEMO_INSTALL.md); `wsl.exe` is a local process (directive
§2.2/§2.4 — no `claude`/`codex`, no secret).
"""
from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from adapters.frontier.process_tree import run_managed_process
from adapters.voice_parakeet.engine import Transcript

#: The engine name the shell surfaces as the VISIBLE real-STT badge (never "mock-stt").
PARAKEET_WSL_NAME = "parakeet-wsl"

#: Default model ref (CC-BY-4.0; U4 attribution). The operator install caches it in WSL.
DEFAULT_MODEL_ID = "nvidia/parakeet-tdt-0.6b-v3"

#: How long a WSL probe/transcription may run before it fails closed. Both are hard bounds — a hung WSL
#: can never wedge the shell or the loop (D-P16-0 / D-LOOP-1 spirit).
#:
#: U74 / OP-11 finding F1 (2026-07-25): the operator's shell badged "mock engine" on a host where WSL
#: Parakeet is INSTALLED AND VERIFIED, because this budget was 8.0 s. Two facts, both MEASURED on this
#: host on 2026-07-26 (recorded in docs/evidence/PHASE17C_PROBE_EVIDENCE_REPORT.md):
#:   * the old probe body (`import nemo`) is a ~0.04 s namespace-package import that says NOTHING about
#:     whether ASR can run — so it was both slow-to-fail and weak-when-it-passed;
#:   * the import transcription ACTUALLY performs (`from nemo.collections.asr.models import ASRModel`)
#:     costs **17.91 s** on a cold page cache and **7.02 s** warm — already past 8.0 s by itself,
#:     before `wsl.exe` VM start (measured separately at 4.46 s cold on this host).
#: So the probe now runs the import that matters, under a budget set from that measurement with room for
#: a cold VM: 90 s (directive §16 track 17C requires ≥60 s). Env-overridable — never a wired-in guess.
PROBE_TIMEOUT_S = 90.0
TRANSCRIBE_TIMEOUT_S = 180.0

#: How long a probe RESULT may be reused before it is re-taken. The old code cached the first answer for
#: the life of the process (`functools.lru_cache(maxsize=1)`), which pinned ONE cold miss for the app's
#: whole run — the second half of U74. A positive answer is stable (the venv does not uninstall itself
#: mid-session) so it is held for 15 min; a NEGATIVE answer is held only long enough to stop a poll storm
#: (30 s) and is then re-taken, because "not available" is exactly the state that changes when WSL warms
#: up, the operator finishes an install, or a transient VM start fails.
PROBE_POSITIVE_TTL_S = 900.0
PROBE_NEGATIVE_TTL_S = 30.0

#: Non-blocking probe states (the shell renders these; see terminal/compositor/voice-indicator.js).
#: `unprobed` is NOT `unavailable` — rendering it as "mock engine" is precisely the F1 lie.
PROBE_AVAILABLE = "available"
PROBE_UNAVAILABLE = "unavailable"
PROBE_UNPROBED = "unprobed"
PROBE_PROBING = "probing"


class VoiceEngineError(RuntimeError):
    """A real-engine transcription fault. Caught by `run_conductor_voice` → the fail-closed feed."""


class _Runner(Protocol):
    def __call__(self, cmd: list[str], *, input: str | None, timeout: float) -> Any: ...


@dataclass(frozen=True)
class WslConfig:
    """How to reach the operator-installed NeMo venv in WSL. All fields are host-configurable via env so
    a different distro/venv drops in without a code change; the defaults match
    docs/OPERATOR_NEMO_INSTALL.md. `$HOME` is left UNQUOTED in the venv path so the WSL login shell
    expands it (the operator's username is not known here)."""

    distro: str | None = None            # None ⇒ the WSL default distro; env SOW_WSL_DISTRO overrides
    venv: str = "$HOME/nemo-venv"        # env SOW_NEMO_VENV overrides
    model_id: str = DEFAULT_MODEL_ID     # env SOW_PARAKEET_MODEL overrides
    probe_timeout_s: float = PROBE_TIMEOUT_S        # env SOW_NEMO_PROBE_TIMEOUT_S overrides
    transcribe_timeout_s: float = TRANSCRIBE_TIMEOUT_S  # env SOW_NEMO_TRANSCRIBE_TIMEOUT_S overrides

    @property
    def venv_python(self) -> str:
        # Left unquoted on purpose: `$HOME` must expand under `bash -c`.
        return f"{self.venv}/bin/python"


def _env_seconds(name: str, default: float) -> float:
    """Read a positive float seconds budget from the environment, fail-closed to `default`. A missing,
    empty, unparseable, non-positive, or non-finite value is NOT an error the operator has to debug —
    it falls back to the measured default (a budget is a safety bound, never a reason to refuse)."""
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return default
    if value != value or value in (float("inf"), float("-inf")) or value <= 0:  # NaN/inf/non-positive
        return default
    return value


def config_from_env() -> WslConfig:
    """Build the WSL config from the environment (defaults per the operator install doc). Every `SOW_*`
    override is honoured HERE — including the two timeouts, which before U74 were reachable only by
    editing this file (directive §16 track 17C: *"`SOW_*` env overrides honored"*)."""
    distro = os.environ.get("SOW_WSL_DISTRO") or None
    return WslConfig(
        distro=distro,
        venv=os.environ.get("SOW_NEMO_VENV", WslConfig.venv),
        model_id=os.environ.get("SOW_PARAKEET_MODEL", DEFAULT_MODEL_ID),
        probe_timeout_s=_env_seconds("SOW_NEMO_PROBE_TIMEOUT_S", PROBE_TIMEOUT_S),
        transcribe_timeout_s=_env_seconds("SOW_NEMO_TRANSCRIBE_TIMEOUT_S", TRANSCRIBE_TIMEOUT_S),
    )


def _default_runner(cmd: list[str], *, input: str | None, timeout: float) -> Any:
    """Run WSL inside the same OS-owned descendant boundary as live provider CLIs.

    On Windows the Python emitter owns a kill-on-close Job Object. Therefore both its
    own timeout and an outer shell teardown reap wsl.exe and every descendant rather
    than killing only py.exe and hoping the VM-side import eventually finishes.
    """
    return run_managed_process(
        cmd,
        timeout=timeout,
        env=dict(os.environ),
        stdin=subprocess.PIPE,
        input_text=input,
    )


def _wsl_cmd(config: WslConfig, inner: str) -> list[str]:
    """`wsl.exe [-d <distro>] -- bash -c '<inner>'`. `bash -c` gives `$HOME` expansion; `wsl.exe -- cmd`
    with no shell would NOT expand it (the operator's home dir is unknown here)."""
    cmd = ["wsl.exe"]
    if config.distro:
        cmd += ["-d", config.distro]
    cmd += ["--", "bash", "-c", inner]
    return cmd


def to_wsl_path(path: str) -> str:
    r"""Convert a Windows path to its WSL `/mnt/<drive>/...` form (spaces preserved, NOT escaped — the
    caller quotes it for the shell). An already-POSIX path is returned unchanged. Pure/deterministic."""
    p = str(path)
    m = re.match(r"^([A-Za-z]):[\\/](.*)$", p)
    if not m:
        return p.replace("\\", "/")
    drive, rest = m.group(1).lower(), m.group(2).replace("\\", "/")
    return f"/mnt/{drive}/{rest}"


def parse_transcript(stdout: str) -> Transcript:
    """Parse the WSL transcription program's output (the LAST non-empty line is the result JSON, so NeMo
    log chatter on earlier lines is ignored) into a `Transcript`. Fail-closed: no JSON object with a
    string `text` ⇒ `VoiceEngineError` (never a fabricated transcript).

    Confidence policy (Phase 16E `.real`): NeMo's raw hypothesis score is a LOG-probability (e.g.
    -29.8), NOT a calibrated 0..1 confidence — feeding it to the `ConductorVoiceBridge`'s 0..1 threshold
    would route EVERY real utterance to CLARIFY (voice "unusable" again). So confidence is derived
    honestly from recognition: a non-empty transcript is treated as confident (1.0), an empty one (the
    engine heard nothing) as a repeat (0.0). A JSON `confidence` already in [0, 1] is respected (test
    seam); an out-of-range one (a raw log score) is ignored in favour of the text-derived value."""
    for line in reversed([ln for ln in (stdout or "").splitlines() if ln.strip()]):
        try:
            obj = json.loads(line)
        except (ValueError, TypeError):
            continue
        if isinstance(obj, dict) and isinstance(obj.get("text"), str):
            text = obj["text"]
            conf = obj.get("confidence")
            if isinstance(conf, (int, float)) and 0.0 <= float(conf) <= 1.0:
                confidence = float(conf)
            else:
                confidence = 1.0 if text.strip() else 0.0
            return Transcript(text=text, confidence=confidence)
    raise VoiceEngineError("WSL Parakeet produced no parseable transcript JSON")


# The WSL-side transcription program, streamed to the venv python over stdin (`python - <wav> <model>`)
# so nothing must be path-resolved on the WSL filesystem. It imports NeMo (WSL-only; guarded so a stray
# host import cannot crash) and prints ONE JSON line `{"text","confidence"}`. transcribe-then-discard:
# it opens the WAV read-only and retains nothing. NO synthesis (STT-only).
WSL_TRANSCRIBE_SRC = r'''
import sys, json
def main():
    wav, model_id = sys.argv[1], sys.argv[2]
    from nemo.collections.asr.models import ASRModel
    model = ASRModel.from_pretrained(model_name=model_id)
    out = model.transcribe([wav])
    hyp = out[0] if isinstance(out, (list, tuple)) and out else out
    text = getattr(hyp, "text", hyp if isinstance(hyp, str) else "")
    # Emit TEXT only. NeMo's hypothesis .score is a log-prob, not a 0..1 confidence, so the host derives
    # confidence from recognition (non-empty -> confident) rather than mis-feeding a raw score.
    print(json.dumps({"text": (text or "").strip()}))
if __name__ == "__main__":
    main()
'''


#: What the probe actually imports. NOT the bare `import nemo` the pre-U74 probe used: on this host that
#: is a ~0.04 s namespace-package import that succeeds even if the ASR stack is unusable, so it answered
#: the wrong question. This is the exact import `WSL_TRANSCRIBE_SRC` performs, so a passing probe means
#: transcription's import path works — and its measured 7–18 s cost is what the budget above is set from.
PROBE_IMPORT = "from nemo.collections.asr.models import ASRModel"


@dataclass(frozen=True)
class ProbeResult:
    """One probe's OUTCOME plus how it was reached — so the shell can show the operator why voice is in
    the state it is in, and so the evidence receipt records real timings rather than a claim."""

    available: bool
    reason: str
    elapsed_s: float
    timeout_s: float
    at: float          # monotonic stamp — TTL only; never presented as a wall-clock time

    @property
    def state(self) -> str:
        return PROBE_AVAILABLE if self.available else PROBE_UNAVAILABLE

    def as_dict(self) -> dict[str, Any]:
        return {"state": self.state, "available": self.available, "reason": self.reason,
                "elapsed_s": round(self.elapsed_s, 3), "timeout_s": self.timeout_s}


# Per-config probe cache. Replaces `functools.lru_cache(maxsize=1)`, which pinned the FIRST answer —
# including one cold-start miss — for the whole life of the process (U74, second half). The lock makes
# concurrent readers (the shell's indicator poll vs a talk press) see one consistent record.
_PROBE_CACHE: dict[WslConfig, ProbeResult] = {}
_PROBE_LOCK = threading.Lock()


def reset_probe_cache() -> None:
    """Drop every cached probe result — the explicit "re-probe on demand" hook (a talk press, an
    operator retry after finishing the WSL install). Nothing is pinned for a process lifetime."""
    with _PROBE_LOCK:
        _PROBE_CACHE.clear()


#: Marks a probe answer this process did NOT take itself. Kept in the reason string so it travels all
#: the way into the feed's `probe.reason` and the receipt: a reader must always be able to see whether
#: an "available" came from a WSL import performed HERE or from an answer handed in.
SEEDED_REASON_PREFIX = "seeded from the shell's own probe: "


def seed_probe_result(
    available: bool,
    reason: str = "",
    elapsed_s: float = 0.0,
    config: WslConfig | None = None,
    *,
    clock: Callable[[], float] = time.monotonic,
) -> ProbeResult:
    """Record a probe answer that ANOTHER process already established (U134).

    Phase 17C `.mic`. The probe cache is module state, and the emitter is a one-shot process that
    exits after a single emission — so its cache is always empty, and a real mic capture arriving here
    would see `unprobed`, decline the real engine, and route the operator's actual speech to the mock.
    That is U74's failure re-staged at the process boundary: the shell KNOWS the engine is reachable
    (`VoiceProbe` maintains that fact and paid 7–22 s for it), it just could not say so across the seam.

    This is the seam. The shell passes the answer it holds; nothing is fabricated, because a seeded
    POSITIVE cannot manufacture a transcript — `WslParakeetSTT.transcribe` still runs the real WSL
    round trip and still fails closed (`VoiceEngineError` → the unavailable feed) if NeMo is not
    actually there. The only thing a seed can do is skip a redundant 20 s import; the honest direction
    is preserved in both directions, and the provenance rides in the reason (`SEEDED_REASON_PREFIX`).
    """
    cfg = config or config_from_env()
    detail = str(reason).strip() or ("the WSL NeMo ASR import succeeded" if available else "the WSL NeMo probe did not succeed")
    # A timing is diagnostic; a junk one (None, negative, NaN from a JS `Number` of nothing) must not be
    # able to break a capture or poison a TTL comparison, so it is sanitised rather than trusted.
    try:
        elapsed = float(elapsed_s or 0.0)
    except (TypeError, ValueError):
        elapsed = 0.0
    if elapsed != elapsed or elapsed in (float("inf"), float("-inf")) or elapsed < 0:  # NaN/inf/negative
        elapsed = 0.0
    result = ProbeResult(
        available=bool(available),
        reason=f"{SEEDED_REASON_PREFIX}{detail}",
        elapsed_s=elapsed,
        timeout_s=cfg.probe_timeout_s,
        at=clock(),
    )
    with _PROBE_LOCK:
        _PROBE_CACHE[cfg] = result
    return result


def _ttl_for(result: ProbeResult) -> float:
    return PROBE_POSITIVE_TTL_S if result.available else PROBE_NEGATIVE_TTL_S


def cached_probe(config: WslConfig | None = None, *, clock: Callable[[], float] = time.monotonic) -> ProbeResult | None:
    """The cached probe result for `config` if one is still within its TTL, else None. NEVER spawns
    anything — this is the non-blocking read the shell's always-visible chrome uses."""
    cfg = config or config_from_env()
    with _PROBE_LOCK:
        result = _PROBE_CACHE.get(cfg)
    if result is None:
        return None
    if clock() - result.at >= _ttl_for(result):
        return None
    return result


def probe_state(config: WslConfig | None = None, *, clock: Callable[[], float] = time.monotonic) -> str:
    """The non-blocking probe state: `available` / `unavailable` / `unprobed`. `unprobed` is NOT
    `unavailable` — the caller must render it as "probing/unknown", never as "mock engine" (F1)."""
    result = cached_probe(config, clock=clock)
    return PROBE_UNPROBED if result is None else result.state


def probe_nemo(
    config: WslConfig | None = None,
    *,
    runner: _Runner | None = None,
    clock: Callable[[], float] = time.monotonic,
    store: bool = True,
) -> ProbeResult:
    """BLOCKING: run the real WSL probe once and return its result (also caching it, per TTL).
    Fail-closed on ANY fault — no WSL, a non-zero exit, a timeout, an OS error — each yields
    `available=False` with the reason NAMED, never an exception into the caller's chrome."""
    cfg = config or config_from_env()
    started = clock()

    def done(available: bool, reason: str) -> ProbeResult:
        result = ProbeResult(available=available, reason=reason, elapsed_s=max(0.0, clock() - started),
                             timeout_s=cfg.probe_timeout_s, at=clock())
        if store:
            with _PROBE_LOCK:
                _PROBE_CACHE[cfg] = result
        return result

    if shutil.which("wsl") is None:
        return done(False, "wsl.exe is not on PATH — WSL2 is not installed or not reachable")
    inner = f'{cfg.venv_python} -c {shlex.quote(PROBE_IMPORT)}'
    try:
        proc = (runner or _default_runner)(_wsl_cmd(cfg, inner), input=None, timeout=cfg.probe_timeout_s)
    except subprocess.TimeoutExpired:
        return done(False, f"the NeMo ASR import did not finish within {cfg.probe_timeout_s}s (budget)")
    except Exception as exc:  # noqa: BLE001 — OS error / anything ⇒ not available, reason named
        return done(False, f"the WSL probe failed to run: {type(exc).__name__}: {exc}")
    rc = getattr(proc, "returncode", 1)
    if rc == 0:
        return done(True, f"NeMo ASR imports in the WSL venv ({cfg.venv_python})")
    err = (getattr(proc, "stderr", "") or "").strip().splitlines()
    tail = err[-1][:200] if err else ""
    return done(False, f"the NeMo ASR import exited {rc} in the WSL venv{f': {tail}' if tail else ''}")


def _probe_nemo(config: WslConfig, runner: _Runner) -> bool:
    """Boolean form of `probe_nemo` with an injected runner and NO caching (the shape the pre-U74 tests
    pin). Kept because the answer "is the real engine reachable" is a boolean everywhere it is consumed;
    `probe_nemo` is what callers want when they also need the reason and the timing."""
    return probe_nemo(config, runner=runner, store=False).available


def wsl_nemo_available(config: WslConfig | None = None, *, force: bool = False) -> bool:
    """Is the NeMo ASR stack importable in the WSL venv? BLOCKING (up to the probe budget) but
    TTL-cached, so a warm positive costs nothing and a negative is re-taken every 30 s rather than
    pinned for the process lifetime (U74). `force=True` re-probes NOW — the "on demand" path."""
    cfg = config or config_from_env()
    if not force:
        cached = cached_probe(cfg)
        if cached is not None:
            return cached.available
    return probe_nemo(cfg).available


class WslParakeetSTT:
    """A real `STTEngine` that transcribes a WAV via the WSL venv NeMo (Parakeet). It holds no state
    between calls, never retains audio, and exposes no synthesis method (STT-only). `runner` is injected
    only in tests; production uses the managed process-tree runner."""

    name = PARAKEET_WSL_NAME

    def __init__(self, config: WslConfig | None = None, *, runner: _Runner | None = None) -> None:
        self._config = config or config_from_env()
        self._runner = runner or _default_runner

    @property
    def config(self) -> WslConfig:
        return self._config

    def transcribe(self, audio_ref: str) -> Transcript:
        """Transcribe a real WAV (a Windows or POSIX path). Fail-closed: a stand-in `audio:` ref (no PCM),
        a missing file, a non-zero exit, a timeout, or malformed output ⇒ `VoiceEngineError`."""
        if not audio_ref or audio_ref.startswith("audio:"):
            # a scripted stand-in ref carries no PCM — the real engine has nothing to transcribe.
            raise VoiceEngineError(f"no real audio for ref {audio_ref!r} (real capture is operator-run/16F)")
        wsl_wav = to_wsl_path(audio_ref)
        inner = f"{self._config.venv_python} - {shlex.quote(wsl_wav)} {shlex.quote(self._config.model_id)}"
        try:
            proc = self._runner(
                _wsl_cmd(self._config, inner),
                input=WSL_TRANSCRIBE_SRC,
                timeout=self._config.transcribe_timeout_s,
            )
        except subprocess.TimeoutExpired as exc:
            raise VoiceEngineError(f"WSL Parakeet transcription timed out after {self._config.transcribe_timeout_s}s") from exc
        except Exception as exc:  # noqa: BLE001
            raise VoiceEngineError(f"WSL Parakeet transcription failed to run: {exc}") from exc
        if getattr(proc, "returncode", 1) != 0:
            err = (getattr(proc, "stderr", "") or "").strip()[:200]
            raise VoiceEngineError(f"WSL Parakeet transcription exited {getattr(proc, 'returncode', '?')}: {err}")
        return parse_transcript(getattr(proc, "stdout", "") or "")


def build_real_engine(config: WslConfig | None = None) -> WslParakeetSTT:
    """Factory the selection layer calls when real Parakeet is available (kept small so it is easy to
    inject a stand-in factory in tests)."""
    return WslParakeetSTT(config)
