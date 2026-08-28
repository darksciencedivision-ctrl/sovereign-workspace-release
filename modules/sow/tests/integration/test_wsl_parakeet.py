"""Real WSL Parakeet adapter tests — Phase 16E `.real` (directive §15 track 16E; OP-10).

These pin the WSL-routed real `STTEngine` WITHOUT a live NeMo/GPU (an injected runner stands in for
`wsl.exe`), so the command construction, Windows→WSL path conversion, confidence policy, and every
fail-closed branch are deterministic on any host. The live end-to-end transcription is proven separately
on this host by `tools/live/real_parakeet_smoke.py` (receipt
docs/evidence/receipts/PHASE16E_REAL_PARAKEET_SMOKE.json).
"""
from __future__ import annotations

import shutil
import subprocess
from types import SimpleNamespace
import uuid

import pytest

from tests.host_prerequisites import NODE, WINDOWS, WSL, requires

from adapters.voice_parakeet.engine import Transcript
from adapters.voice_parakeet.wsl_parakeet import (
    DEFAULT_MODEL_ID,
    PROBE_IMPORT,
    PROBE_NEGATIVE_TTL_S,
    PROBE_POSITIVE_TTL_S,
    PROBE_TIMEOUT_S,
    WSL_TRANSCRIBE_SRC,
    VoiceEngineError,
    WslConfig,
    WslParakeetSTT,
    _default_runner,
    _probe_nemo,
    _wsl_cmd,
    cached_probe,
    config_from_env,
    parse_transcript,
    probe_nemo,
    probe_state,
    reset_probe_cache,
    to_wsl_path,
    wsl_nemo_available,
)


@pytest.fixture(autouse=True)
def _clean_probe_cache():
    """Every probe test starts and ends with an empty cache — the cache is module state, and a test that
    leaked a cached answer into the next one would hide exactly the staleness bug U74 is about."""
    reset_probe_cache()
    yield
    reset_probe_cache()


@pytest.fixture
def wsl_present(monkeypatch):
    """`probe_nemo` short-circuits on `shutil.which("wsl") is None`, so on a host without WSL these
    tests would stop testing the probe at all — the expects-unavailable ones passing for the wrong
    reason and the rest failing (spec-audit m-6; 17D `.close` F6 corrects the earlier "all vacuous"
    wording). This file's docstring promises determinism on ANY host, so the PATH lookup is pinned
    rather than inherited; `tools/mutation/wsl_path_hermeticity_check.py` measures that it is."""
    monkeypatch.setattr("adapters.voice_parakeet.wsl_parakeet.shutil.which",
                        lambda name: r"C:\Windows\system32\wsl.EXE" if name == "wsl" else None)


class _Clock:
    """A hand-cranked monotonic clock, so TTL expiry is tested without sleeping."""

    def __init__(self, t: float = 1000.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += dt


def _proc(returncode=0, stdout="", stderr=""):
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


class _Runner:
    """Records the last (cmd, input, timeout) and returns a scripted process (or raises)."""

    def __init__(self, result=None, raises=None):
        self.result = result if result is not None else _proc(0, '{"text": "hello world"}')
        self.raises = raises
        self.calls: list[dict] = []

    def __call__(self, cmd, *, input, timeout):  # noqa: A002 — matches subprocess.run kwarg
        self.calls.append({"cmd": cmd, "input": input, "timeout": timeout})
        if self.raises is not None:
            raise self.raises
        return self.result


def test_default_runner_uses_the_managed_process_boundary(monkeypatch) -> None:
    """U158: production WSL launches must sit inside the descendant-killing boundary.

    The JS shell can kill its Python emitter on quit. The Python process owns the Windows
    Job Object, so closing that process also closes the job and reaps wsl.exe descendants.
    """
    calls = []

    def managed(cmd, *, timeout, env, stdin, input_text):
        calls.append({
            "cmd": cmd,
            "timeout": timeout,
            "env": env,
            "stdin": stdin,
            "input_text": input_text,
        })
        return _proc(0, '{"text":"bounded"}', "")

    monkeypatch.setattr("adapters.voice_parakeet.wsl_parakeet.run_managed_process", managed)
    result = _default_runner(
        ["wsl.exe", "--", "bash", "-c", "sleep 60"],
        input="program",
        timeout=0.01,
    )

    assert result.returncode == 0
    assert calls == [{
        "cmd": ["wsl.exe", "--", "bash", "-c", "sleep 60"],
        "timeout": 0.01,
        "env": dict(__import__("os").environ),
        "stdin": subprocess.PIPE,
        "input_text": "program",
    }]


def _node_process_with_marker_exists(marker: str) -> bool:
    probe = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            (
                "if (Get-CimInstance Win32_Process | "
                f"Where-Object {{ $_.Name -eq 'node.exe' -and $_.CommandLine -like '*{marker}*' }}) "
                "{ exit 0 } else { exit 1 }"
            ),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return probe.returncode == 0


@requires(WINDOWS, NODE)          # Windows WSL-boundary induced-hang proof
@pytest.mark.parametrize("path_kind", ["probe", "transcription"])
def test_probe_and_transcription_hangs_reap_the_complete_managed_tree(
    monkeypatch, path_kind: str,
) -> None:
    """U158: both production callers kill a detached grandchild before returning."""
    marker = f"sow-u158-{path_kind}-{uuid.uuid4().hex}"
    script = (
        "const {spawn}=require('child_process');"
        "const c=spawn(process.execPath,['-e','setTimeout(()=>{},60000)',process.argv[1]],"
        "{detached:true,stdio:'ignore'});"
        "c.unref();setTimeout(()=>{},60000);"
    )
    monkeypatch.setattr(
        "adapters.voice_parakeet.wsl_parakeet._wsl_cmd",
        lambda _config, _inner: ["node", "-e", script, marker],
    )
    monkeypatch.setattr(
        "adapters.voice_parakeet.wsl_parakeet.shutil.which",
        lambda name: "wsl.exe" if name == "wsl" else None,
    )

    if path_kind == "probe":
        outcome = probe_nemo(
            WslConfig(probe_timeout_s=0.15),
            store=False,
        )
        assert outcome.available is False
        assert "budget" in outcome.reason
    else:
        engine = WslParakeetSTT(WslConfig(transcribe_timeout_s=0.15))
        with pytest.raises(VoiceEngineError, match="timed out"):
            engine.transcribe(r"D:\caps\hang.wav")

    assert not _node_process_with_marker_exists(marker)


@requires(WINDOWS, WSL)           # real WSL managed-stdin proof
def test_default_runner_streams_the_complete_program_into_real_wsl() -> None:
    marker = f"WSL_STDIN_OK_{uuid.uuid4().hex}"
    result = _default_runner(
        ["wsl.exe", "--", "bash", "-c", "python3 -"],
        input=f"print({marker!r})\n",
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == marker


# ---- to_wsl_path (pure) ---------------------------------------------------------------------------
def test_to_wsl_path_converts_windows_drive_paths() -> None:
    assert to_wsl_path(r"D:\multi model terminal app\x.wav") == "/mnt/d/multi model terminal app/x.wav"
    assert to_wsl_path("C:/Users/op/a.wav") == "/mnt/c/Users/op/a.wav"


def test_to_wsl_path_passes_through_posix() -> None:
    assert to_wsl_path("/mnt/d/already/posix.wav") == "/mnt/d/already/posix.wav"
    assert to_wsl_path("relative\\dir\\a.wav") == "relative/dir/a.wav"


# ---- _wsl_cmd -------------------------------------------------------------------------------------
def test_wsl_cmd_includes_distro_when_set() -> None:
    assert _wsl_cmd(WslConfig(distro="Ubuntu-24.04"), "echo hi") == \
        ["wsl.exe", "-d", "Ubuntu-24.04", "--", "bash", "-c", "echo hi"]


def test_wsl_cmd_omits_distro_for_default() -> None:
    assert _wsl_cmd(WslConfig(distro=None), "echo hi") == ["wsl.exe", "--", "bash", "-c", "echo hi"]


# ---- parse_transcript (confidence policy) ---------------------------------------------------------
def test_parse_transcript_reads_last_json_line_over_log_chatter() -> None:
    stdout = "[NeMo I] loading model...\nsome torch warning\n{\"text\": \"focus pane 3\"}\n"
    t = parse_transcript(stdout)
    assert t.text == "focus pane 3" and t.confidence == 1.0  # non-empty ⇒ confident


def test_parse_transcript_empty_text_is_low_confidence_repeat() -> None:
    t = parse_transcript('{"text": ""}')
    assert t.text == "" and t.confidence == 0.0  # heard nothing ⇒ clarify, never a fabricated hit


def test_parse_transcript_ignores_raw_log_score_confidence() -> None:
    # a NeMo log-prob (-29.8) is NOT a 0..1 confidence — it must be ignored (else every utterance clarifies)
    t = parse_transcript('{"text": "hello", "confidence": -29.8}')
    assert t.confidence == 1.0


def test_parse_transcript_respects_in_range_confidence() -> None:
    t = parse_transcript('{"text": "hello", "confidence": 0.42}')
    assert t.confidence == 0.42


def test_parse_transcript_fails_closed_without_json() -> None:
    with pytest.raises(VoiceEngineError):
        parse_transcript("no json here at all\njust logs")


# ---- WslParakeetSTT.transcribe --------------------------------------------------------------------
def test_transcribe_success_builds_the_wsl_command_and_streams_the_program() -> None:
    runner = _Runner(_proc(0, '{"text": "show status"}'))
    eng = WslParakeetSTT(WslConfig(distro="Ubuntu-24.04", venv="$HOME/nemo-venv"), runner=runner)
    t = eng.transcribe(r"D:\caps\utt.wav")
    assert isinstance(t, Transcript) and t.text == "show status" and t.confidence == 1.0
    call = runner.calls[-1]
    assert call["input"] == WSL_TRANSCRIBE_SRC                      # the program is streamed over stdin
    assert call["cmd"][:5] == ["wsl.exe", "-d", "Ubuntu-24.04", "--", "bash"]
    inner = call["cmd"][-1]
    assert "$HOME/nemo-venv/bin/python -" in inner                 # $HOME left unquoted for shell expansion
    assert "/mnt/d/caps/utt.wav" in inner                          # converted + shell-quoted
    assert DEFAULT_MODEL_ID in inner


def test_transcribe_rejects_a_standin_ref_without_calling_wsl() -> None:
    runner = _Runner()
    eng = WslParakeetSTT(runner=runner)
    with pytest.raises(VoiceEngineError, match="no real audio"):
        eng.transcribe("audio:show-status")  # a scripted stand-in carries no PCM
    assert runner.calls == []                # never spawned WSL for a fake ref


def test_transcribe_fails_closed_on_nonzero_exit() -> None:
    eng = WslParakeetSTT(runner=_Runner(_proc(1, "", "CUDA error")))
    with pytest.raises(VoiceEngineError, match="exited 1"):
        eng.transcribe(r"D:\a.wav")


def test_transcribe_fails_closed_on_timeout() -> None:
    eng = WslParakeetSTT(runner=_Runner(raises=subprocess.TimeoutExpired(cmd="wsl", timeout=180)))
    with pytest.raises(VoiceEngineError, match="timed out"):
        eng.transcribe(r"D:\a.wav")


def test_transcribe_fails_closed_on_malformed_output() -> None:
    eng = WslParakeetSTT(runner=_Runner(_proc(0, "not json")))
    with pytest.raises(VoiceEngineError):
        eng.transcribe(r"D:\a.wav")


# ---- _probe_nemo ----------------------------------------------------------------------------------
def test_probe_true_on_rc0(wsl_present) -> None:
    assert _probe_nemo(WslConfig(), _Runner(_proc(0))) is True


def test_probe_false_on_nonzero(wsl_present) -> None:
    assert _probe_nemo(WslConfig(), _Runner(_proc(1))) is False


def test_probe_false_on_exception(wsl_present) -> None:
    assert _probe_nemo(WslConfig(), _Runner(raises=OSError("boom"))) is False


def test_probe_false_when_wsl_absent(monkeypatch) -> None:
    monkeypatch.setattr("adapters.voice_parakeet.wsl_parakeet.shutil.which", lambda _n: None)
    called = _Runner()
    assert _probe_nemo(WslConfig(), called) is False
    assert called.calls == []  # never even tried to spawn


# ---- Phase 17C `.probe` (U74): what the probe asks, and for how long -------------------------------
def test_probe_runs_the_import_transcription_actually_performs(wsl_present) -> None:
    """U74's first half. The pre-17C probe ran `import nemo` — a namespace-package import measured at
    ~0.04 s in the operator's WSL venv that succeeds whether or not ASR is usable. The probe must run
    the SAME import `WSL_TRANSCRIBE_SRC` performs, or a green probe proves nothing about transcription."""
    runner = _Runner(_proc(0))
    probe_nemo(WslConfig(), runner=runner, store=False)
    inner = runner.calls[-1]["cmd"][-1]
    assert PROBE_IMPORT in inner
    assert PROBE_IMPORT in WSL_TRANSCRIBE_SRC          # the probe asks what transcription will ask
    assert 'import nemo"' not in inner                  # never the weak bare-namespace import again


def test_probe_budget_covers_the_measured_import_cost(wsl_present) -> None:
    """U74's second half. Measured on this host 2026-07-26: the ASR import costs 17.91 s cold / 7.02 s
    warm — the old 8.0 s budget could not pass on a cold host. Directive §16 track 17C requires ≥60 s."""
    assert PROBE_TIMEOUT_S >= 60.0
    runner = _Runner(_proc(0))
    probe_nemo(WslConfig(), runner=runner, store=False)
    assert runner.calls[-1]["timeout"] == PROBE_TIMEOUT_S


def test_probe_records_why_wsl_is_unreachable(monkeypatch) -> None:
    monkeypatch.setattr("adapters.voice_parakeet.wsl_parakeet.shutil.which", lambda _n: None)
    r = probe_nemo(WslConfig(), runner=_Runner(), store=False)
    assert r.available is False and r.state == "unavailable" and "not on PATH" in r.reason


def test_probe_records_why_it_failed(wsl_present) -> None:
    r2 = probe_nemo(WslConfig(), runner=_Runner(_proc(2, "", "ModuleNotFoundError: nemo")), store=False)
    assert r2.available is False and "exited 2" in r2.reason and "ModuleNotFoundError" in r2.reason
    r3 = probe_nemo(WslConfig(), runner=_Runner(raises=subprocess.TimeoutExpired(cmd="wsl", timeout=90)),
                    store=False)
    assert r3.available is False and "budget" in r3.reason


def test_a_negative_probe_is_not_pinned_for_the_process_lifetime(wsl_present) -> None:
    """THE U74 CACHE DEFECT. `lru_cache(maxsize=1)` meant one cold miss decided the app's whole run: the
    operator's install could finish, WSL could warm up, and the shell would still say no. A negative is
    now re-probed once its short TTL passes."""
    clock = _Clock()
    cfg = WslConfig()
    probe_nemo(cfg, runner=_Runner(_proc(1)), clock=clock)
    assert probe_state(cfg, clock=clock) == "unavailable"
    clock.advance(PROBE_NEGATIVE_TTL_S + 1)
    assert cached_probe(cfg, clock=clock) is None          # expired ⇒ the next read re-probes
    assert probe_state(cfg, clock=clock) == "unprobed"     # and it reads as OPEN, not as a "no"


def test_a_positive_probe_is_reused_within_its_ttl_then_retaken(wsl_present) -> None:
    clock = _Clock()
    cfg = WslConfig()
    probe_nemo(cfg, runner=_Runner(_proc(0)), clock=clock)
    clock.advance(PROBE_NEGATIVE_TTL_S + 1)                # a negative would have expired by here
    assert probe_state(cfg, clock=clock) == "available"    # a positive is stable — the venv did not vanish
    clock.advance(PROBE_POSITIVE_TTL_S)
    assert probe_state(cfg, clock=clock) == "unprobed"


def test_reset_and_force_retake_the_probe_on_demand(wsl_present) -> None:
    cfg = WslConfig()
    runner = _Runner(_proc(1))
    probe_nemo(cfg, runner=runner)
    assert probe_state(cfg) == "unavailable"
    reset_probe_cache()
    assert probe_state(cfg) == "unprobed"                  # nothing is pinned; the question reopens
    # `force` re-probes even with a fresh cached answer (the operator's retry after finishing the install)
    probe_nemo(cfg, runner=_Runner(_proc(1)))
    assert wsl_nemo_available(cfg) is False                # served from cache — no new spawn
    calls_before = len(runner.calls)
    assert _probe_nemo(cfg, runner) is False               # an explicit probe always spawns
    assert len(runner.calls) == calls_before + 1


def test_probe_state_is_unprobed_before_anything_ran() -> None:
    assert probe_state(WslConfig()) == "unprobed"           # NOT "unavailable" — the F1 distinction
    assert cached_probe(WslConfig()) is None


def test_cached_probe_never_spawns() -> None:
    """The non-blocking read must be spawn-free: it is what the always-visible chrome calls."""
    called = []
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("adapters.voice_parakeet.wsl_parakeet._default_runner",
                   lambda *a, **k: called.append(a) or _proc(0))
        assert cached_probe(WslConfig()) is None
        assert probe_state(WslConfig()) == "unprobed"
    assert called == []


# ---- config_from_env ------------------------------------------------------------------------------
def test_config_from_env_overrides(monkeypatch) -> None:
    monkeypatch.setenv("SOW_WSL_DISTRO", "Ubuntu-22.04")
    monkeypatch.setenv("SOW_NEMO_VENV", "/opt/venv")
    monkeypatch.setenv("SOW_PARAKEET_MODEL", "nvidia/parakeet-x")
    c = config_from_env()
    assert c.distro == "Ubuntu-22.04" and c.venv == "/opt/venv" and c.model_id == "nvidia/parakeet-x"
    assert c.venv_python == "/opt/venv/bin/python"


def test_config_from_env_honours_the_timeout_overrides(monkeypatch, wsl_present) -> None:
    """Directive §16 track 17C: *"`SOW_*` env overrides honored"*. Before 17C the two budgets were
    reachable only by editing the source, so an operator on a slower host had no lever at all."""
    monkeypatch.setenv("SOW_NEMO_PROBE_TIMEOUT_S", "240")
    monkeypatch.setenv("SOW_NEMO_TRANSCRIBE_TIMEOUT_S", "600.5")
    c = config_from_env()
    assert c.probe_timeout_s == 240.0 and c.transcribe_timeout_s == 600.5
    runner = _Runner(_proc(0))
    probe_nemo(c, runner=runner, store=False)
    assert runner.calls[-1]["timeout"] == 240.0            # the override actually reaches the spawn


@pytest.mark.parametrize("bad", ["", "   ", "abc", "0", "-5", "nan", "inf"])
def test_a_bad_timeout_override_falls_back_to_the_measured_default(monkeypatch, bad) -> None:
    """Fail-closed on ambiguity, but a budget is a safety bound — a junk override must not disable the
    engine or raise into the operator's chrome; it falls back to the measured default."""
    monkeypatch.setenv("SOW_NEMO_PROBE_TIMEOUT_S", bad)
    assert config_from_env().probe_timeout_s == PROBE_TIMEOUT_S


# ---- W-80: the derivation is named for what it does - silence detection, not recognition ----

def test_silence_only_confidence_is_the_named_retraction():
    """W-80/U140. The old inline branch derived 1.0-for-non-empty and let every reader mistake it
    for recognition certainty. The retraction: a NAMED function whose contract says it detects
    silence only, mishearing passes by construction, calibration is PARK-R10."""
    import adapters.voice_parakeet.wsl_parakeet as wp

    assert callable(wp.silence_only_confidence)
    doc = (wp.silence_only_confidence.__doc__ or "")
    assert "NOT recognition confidence" in doc
    assert "PARK-R10" in doc

    assert wp.silence_only_confidence("hello") == 1.0
    assert wp.silence_only_confidence("   ") == 0.0


def test_parse_transcript_behaviour_is_unchanged_under_the_retraction():
    """Control: the JSON [0,1] seam is respected; empty text -> 0.0; non-empty -> 1.0. The
    retraction renamed and documented the derivation; it changed nothing observable."""
    import adapters.voice_parakeet.wsl_parakeet as wp

    ok = wp.parse_transcript('{"text": "hello world", "confidence": 0.42}')
    assert (ok.text, ok.confidence) == ("hello world", 0.42)

    derived = wp.parse_transcript('{"text": "hello world"}')
    assert derived.confidence == 1.0

    silent = wp.parse_transcript('{"text": ""}')
    assert silent.confidence == 0.0
