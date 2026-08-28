"""Reproducible on-host evidence: the real `WslParakeetSTT` adapter transcribes real speech via
WSL2 -> NeMo -> GPU (Phase 16E `.real`; directive §15 track 16E; OP-10; OP-9/§10.3 authorizes the NeMo
stack). Run on the Windows host after the operator install (docs/OPERATOR_NEMO_INSTALL.md):

    py -3.12 tools/live/real_parakeet_smoke.py

It (1) generates a short WAV with the OS speech synthesizer as a TEST-INPUT FIXTURE ONLY — this is a
transcription input generator, NOT a product feature; the PRODUCT never synthesizes speech and exposes
no speak/TTS method (frozen invariant I-V2 / D-VOICE-02), and this tool lives outside the product voice
path (adapters/apps) — then (2) transcribes it with the REAL shipped adapter and writes a machine-
readable receipt. Skips-with-record (exit 0, ok:false, reason) when the real stack is absent, so it is
safe on any host. Spawns only local processes (`powershell.exe` for the fixture, `wsl.exe` for NeMo);
no `claude`/`codex`, no credential, no network (directive §2.2/§2.4). transcribe-then-discard: the
fixture WAV is deleted on the way out (invariant 26)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adapters.voice_parakeet.engine import detect_voice_stack, real_parakeet_available  # noqa: E402
from adapters.voice_parakeet.wsl_parakeet import DEFAULT_MODEL_ID, WslParakeetSTT  # noqa: E402

RECEIPT = ROOT / "docs" / "evidence" / "receipts" / "PHASE16E_REAL_PARAKEET_SMOKE.json"
PHRASE = "testing one two three four"


def _make_fixture(wav: Path) -> int:
    """Synthesize the TEST INPUT phrase to a FILE, and to nothing else.

    Hardened at Phase 17C `.disarm` (spec-audit M-2) toward the standard
    `tools/live/make_voice_fixture.py` set -- the speaker path is closed by construction here too,
    though this one still does not escape its interpolated path/phrase the way that module does, and
    its caller keys off ``wav.exists()`` rather than the shell's exit code (spec-audit m-B).
    The previous body ran under PowerShell's default
    ``$ErrorActionPreference = 'Continue'``: a throwing ``SetOutputToWaveFile`` is NON-terminating,
    so ``Speak`` would then have rendered the phrase to the host's DEFAULT AUDIO DEVICE. Nothing
    shipped reaches this script -- it is an operator-run diagnostic in ``tools/`` -- so I-V2 /
    D-VOICE-02 were never at risk in the product. But a latent path from this repo to a loudspeaker
    is not something to leave lying next to an invariant that says the system never speaks.

    Now: errors are terminating, the sink is asserted to be the file BEFORE ``Speak`` is called, and
    any failure is a non-zero exit rather than an audible one.
    """
    ps = (
        "$ErrorActionPreference = 'Stop'; "
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        "$fmt = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000,"
        "[System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen,"
        "[System.Speech.AudioFormat.AudioChannel]::Mono); "
        "try { "
        f"$s.SetOutputToWaveFile('{wav}',$fmt); "
        # The file must exist before a single word is spoken: if the sink is not the file, the only
        # other sink is a speaker, and this script must fail instead.
        f"if (-not (Test-Path -LiteralPath '{wav}')) {{ throw 'wave sink was not created' }}; "
        f"$s.Speak('{PHRASE}'); "
        "} finally { $s.Dispose() }"
    )
    subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps],
                   capture_output=True, text=True, timeout=60, check=False)
    return wav.stat().st_size if wav.exists() else 0


def main() -> int:
    detection = detect_voice_stack()
    receipt: dict = {
        "schema": "phase16e_real_parakeet_smoke@1.0",
        "check": "phase-16e.real",
        "host_detection": detection,
        "model_id": DEFAULT_MODEL_ID,
        "fixture": {"method": "OS System.Speech (test input only; NOT product TTS)", "phrase": PHRASE},
        "transcribe_seconds": None,
        "transcript_text": None,
        "transcript_confidence": None,
        "recognized_spoken_content": False,
        "error": None,
        "ok": False,
    }
    if not real_parakeet_available(detection):
        receipt["error"] = "real Parakeet/NeMo not available on this host — skipped-with-record"
        _write(receipt)
        return 0  # skip-with-record is not a failure

    wav = ROOT / "tools" / "live" / "_parakeet_fixture.wav"
    try:
        receipt["fixture"]["wav_bytes"] = _make_fixture(wav)
        t = time.time()
        tr = WslParakeetSTT().transcribe(str(wav))
        receipt["transcribe_seconds"] = round(time.time() - t, 1)
        receipt["transcript_text"] = tr.text
        receipt["transcript_confidence"] = tr.confidence
        receipt["recognized_spoken_content"] = bool(
            tr.text and any(w in tr.text.lower() for w in ("testing", "test", "1", "234"))
        )
        receipt["ok"] = receipt["recognized_spoken_content"]
    except Exception as exc:  # noqa: BLE001
        receipt["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        try:
            wav.unlink()  # transcribe-then-discard: retain no audio
        except OSError:
            pass
    _write(receipt)
    return 0 if receipt["ok"] else 1


def _write(receipt: dict) -> None:
    RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    RECEIPT.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    raise SystemExit(main())
