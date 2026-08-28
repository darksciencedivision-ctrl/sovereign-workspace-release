"""Real-microphone capture path — Phase 17C `.mic` (directive §16 track 17C).

Everything up to `.mic` was driven by a scripted `audio:` ref that carries no PCM, so the real engine
was structurally unreachable from the shell. These tests pin the two seams `.mic` adds, WITHOUT a
microphone and WITHOUT a live NeMo (an injected runner stands in for `wsl.exe`), so they are
deterministic on any host:

  1. **`seed_probe_result`** — the cross-process probe answer (**U134**). The emitter is a one-shot
     process whose probe cache is always empty; a real capture that had to re-probe would either pay
     7–22 s on top of the transcription the operator is already waiting for, or (non-blocking) see
     `unprobed`, decline the real engine, and route the operator's actual speech to the MOCK. That is
     U74 re-staged at the process boundary. The load-bearing property is that a seed can only ever
     SKIP a redundant import — it can never fabricate a transcript.
  2. **the emitter's `--real-capture` argument surface** — that a real WAV selects the real engine
     (`for_capture=True`, blocking), that a stand-in never does, and that only a POSITIVE engine state
     is honoured (a negative must not be able to suppress the real engine across the seam).

The live end-to-end transcription is proven on this host by the in-Electron `.mic` receipt and by
`tools/live/real_parakeet_smoke.py`.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from adapters.voice_parakeet.wsl_parakeet import (
    PROBE_NEGATIVE_TTL_S,
    PROBE_POSITIVE_TTL_S,
    SEEDED_REASON_PREFIX,
    VoiceEngineError,
    WslConfig,
    WslParakeetSTT,
    cached_probe,
    probe_state,
    reset_probe_cache,
    seed_probe_result,
    wsl_nemo_available,
)
from tools.live import emit_conductor_voice as emitter


@pytest.fixture(autouse=True)
def _clean_probe_cache():
    """The probe cache is module state; a leaked answer would hide exactly the staleness class U74 is
    about."""
    reset_probe_cache()
    yield
    reset_probe_cache()


@pytest.fixture
def wsl_present(monkeypatch):
    """Pin the PATH lookup: `probe_nemo` short-circuits when `wsl` is absent, so on a host without WSL
    these would stop exercising the probe — some passing for the wrong reason, others failing (17D
    `.close` F6 corrects the earlier "vacuous" wording). Measured by
    `tools/mutation/wsl_path_hermeticity_check.py`."""
    monkeypatch.setattr("adapters.voice_parakeet.wsl_parakeet.shutil.which",
                        lambda name: r"C:\Windows\system32\wsl.EXE" if name == "wsl" else None)


class _Clock:
    def __init__(self, t: float = 1000.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += dt


def _proc(returncode=0, stdout="", stderr=""):
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


class _Runner:
    def __init__(self, result=None):
        self.result = result if result is not None else _proc(0, '{"text": "hello"}')
        self.calls: list = []

    def __call__(self, cmd, *, input=None, timeout=None):  # noqa: A002
        self.calls.append({"cmd": cmd, "input": input, "timeout": timeout})
        return self.result


# ---- 1. the cross-process probe seed (U134) --------------------------------------------------------
def test_a_seed_lets_a_cold_process_read_available_without_spawning_anything(wsl_present) -> None:
    spawned: list = []
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("adapters.voice_parakeet.wsl_parakeet._default_runner",
                   lambda *a, **k: spawned.append(a) or _proc(0))
        assert probe_state(WslConfig()) == "unprobed", "production is always cold here"
        seed_probe_result(True, "NeMo ASR imports in the WSL venv", 21.5)
        assert probe_state(WslConfig()) == "available"
        assert wsl_nemo_available(WslConfig()) is True
    assert spawned == [], "the seed must not spawn — skipping the redundant import is the entire point"


def test_a_seeded_answer_carries_its_provenance(wsl_present) -> None:
    """A reader must always be able to tell an answer this process established from one handed in; the
    prefix rides into the feed's `probe.reason` and into the evidence receipt."""
    result = seed_probe_result(True, "NeMo ASR imports in the WSL venv", 21.5)
    assert result.reason.startswith(SEEDED_REASON_PREFIX)
    assert "NeMo ASR imports" in result.reason
    assert cached_probe(WslConfig()).reason == result.reason
    assert result.elapsed_s == 21.5


def test_a_seeded_negative_still_expires_fast(wsl_present) -> None:
    """`unavailable` is exactly the state that changes when WSL warms up or an install finishes, so a
    seeded negative must obey the short TTL rather than pin the session (U74's second half)."""
    clock = _Clock()
    seed_probe_result(False, "the venv is missing", 0.5, clock=clock)
    assert cached_probe(WslConfig(), clock=clock).available is False
    clock.advance(PROBE_NEGATIVE_TTL_S + 1)
    assert cached_probe(WslConfig(), clock=clock) is None


def test_a_seeded_positive_obeys_the_positive_ttl(wsl_present) -> None:
    clock = _Clock()
    seed_probe_result(True, "imports", 1.0, clock=clock)
    clock.advance(PROBE_POSITIVE_TTL_S - 1)
    assert cached_probe(WslConfig(), clock=clock).available is True
    clock.advance(2)
    assert cached_probe(WslConfig(), clock=clock) is None


def test_a_seed_cannot_fabricate_a_transcript() -> None:
    """The guarantee that makes seeding safe at all: the real adapter still performs the WSL round trip
    and still fails closed. The worst a wrong seed can do is produce an honest error."""
    seed_probe_result(True, "claimed available", 0.0)
    engine = WslParakeetSTT(WslConfig(), runner=_Runner(_proc(1, "", "ModuleNotFoundError: nemo")))
    with pytest.raises(VoiceEngineError):
        engine.transcribe(r"D:\repo\.voice-captures\capture-1.wav")


def test_seed_defaults_name_the_outcome() -> None:
    assert "succeeded" in seed_probe_result(True).reason
    reset_probe_cache()
    assert "did not succeed" in seed_probe_result(False).reason


@pytest.mark.parametrize("bad", [None, -5.0, float("nan"), float("inf"), "abc"])
def test_a_junk_elapsed_is_sanitised_not_raised(bad) -> None:
    """A timing is diagnostic. A junk one must not break a capture or poison a TTL comparison."""
    result = seed_probe_result(True, "x", bad)
    assert result.elapsed_s == 0.0


# ---- 2. the emitter's --real-capture surface -------------------------------------------------------
def test_seed_engine_state_honours_only_a_positive() -> None:
    """Fail-closed direction across the seam: a NEGATIVE must never suppress the real engine — the
    emitter falls through to a real blocking probe and re-establishes the fact itself."""
    assert emitter._seed_engine_state(["--engine-state", "available", "--engine-reason", "r",
                                       "--engine-elapsed-s", "3.5"]) == {
        "seeded": True, "reason": f"{SEEDED_REASON_PREFIX}r", "elapsed_s": 3.5}
    reset_probe_cache()
    for argv in ([], ["--engine-state", "unavailable"], ["--engine-state", "unprobed"],
                 ["--engine-state", "probing"], ["--engine-state"], ["--engine-state", "  "]):
        assert emitter._seed_engine_state(argv) is None, argv
        assert cached_probe(WslConfig()) is None


def test_a_junk_elapsed_argument_does_not_break_the_seed() -> None:
    out = emitter._seed_engine_state(["--engine-state", "available", "--engine-elapsed-s", "not-a-number"])
    assert out["seeded"] is True and out["elapsed_s"] == 0.0


def test_real_capture_selects_the_real_engine_and_a_stand_in_does_not(monkeypatch) -> None:
    """The single behavioural difference `.mic` introduces: a real WAV ref transcribes `for_capture`
    under a BLOCKING probe; the PCM-less poll stays non-blocking on the visible mock (a blocking probe
    there would charge the operator 7-22 s for an answer it cannot use)."""
    seen: list = []

    def fake_run(audio_ref, **kwargs):
        seen.append({"ref": audio_ref, **kwargs})
        return {"schema": "conductor_voice_feed@1.0", "sourced": True, "outcome": {"kind": "chat"},
                "delivered": True}

    monkeypatch.setattr(emitter, "run_conductor_voice", fake_run)

    feed = emitter.emit(r"D:\repo\.voice-captures\c.wav", real_capture=True, seeded={"seeded": True})
    assert seen[-1] == {"ref": r"D:\repo\.voice-captures\c.wav", "for_capture": True, "blocking": True}
    assert feed["real_capture"] is True and feed["engine_state_seeded"] == {"seeded": True}

    feed = emitter.emit("audio:show-status")
    assert seen[-1] == {"ref": "audio:show-status", "blocking": False}
    assert feed["real_capture"] is False and feed["engine_state_seeded"] is None


def test_a_fault_on_the_real_capture_path_is_the_unavailable_feed_never_a_delivery(monkeypatch) -> None:
    def boom(*_a, **_k):
        raise RuntimeError("WSL vanished")

    monkeypatch.setattr(emitter, "run_conductor_voice", boom)
    feed = emitter.emit(r"D:\c.wav", real_capture=True)
    assert feed["sourced"] is False
    assert feed["delivered"] is False           # never a fabricated delivery
    assert feed["outcome"]["kind"] == "clarify"
    assert feed["engine"]["mock"] is True       # never a claimed real engine
    assert feed["tts"] is False                 # I-V2/D-VOICE-02 on every path


def test_main_wires_real_capture_and_seeds_before_routing(monkeypatch, capsys) -> None:
    """Ordering is load-bearing: `select_engine` reads the cache DURING `run_conductor_voice`, so a
    seed applied afterwards would be applied to nothing."""
    order: list = []
    monkeypatch.setattr(emitter, "seed_probe_result",
                        lambda *a, **k: order.append("seed") or SimpleNamespace(reason="r", elapsed_s=1.0))
    monkeypatch.setattr(emitter, "run_conductor_voice",
                        lambda *a, **k: order.append("route") or {"schema": "conductor_voice_feed@1.0",
                                                                  "sourced": True, "outcome": {"kind": "chat"},
                                                                  "delivered": True})
    rc = emitter.main(["--emit-conductor-voice", "--audio-ref", r"D:\c.wav", "--real-capture",
                       "--engine-state", "available"])
    assert rc == 0
    assert order == ["seed", "route"]
    assert '"real_capture": true' in capsys.readouterr().out


def test_the_owed_record_names_the_applied_boundary_and_current_receipt_debt() -> None:
    """The boundary is wired; the old receipt is never upgraded to current-tree evidence."""
    from control_plane.orchestration.conductor_voice_feed import REAL_CAPTURE_OWED

    assert REAL_CAPTURE_OWED["owed"] is True
    # the remaining debt is named, and it is the microphone
    assert "microphone" in REAL_CAPTURE_OWED["note"]
    # The current boundary is named while fresh packaged evidence stays explicitly owed.
    write = REAL_CAPTURE_OWED["live_conductor_write"]
    assert "PHASE17C_CLOSE_SELFCHECK.json" in write
    assert "NOT current-tree evidence" in write
    assert "supervisor-owned" in write and "non-executing" in write
    # …and it must not claim the ROUTING is paid without naming what is uncalibrated about it: the
    # record carried on every real capture feed is where a debt has to be visible to the running
    # system, not only in an evidence report nobody re-reads (spec-audit MAJOR-6).
    limits = REAL_CAPTURE_OWED["routing_limits"]
    assert "U140" in limits and "U144" in limits
    assert "WHOLE utterance" in limits
    assert "arbitrary semantic paraphrases" in limits
    assert "supervisor-owned" in limits
    assert "non-executing" in limits
    assert "CALIBRATED" in REAL_CAPTURE_OWED["note"]
