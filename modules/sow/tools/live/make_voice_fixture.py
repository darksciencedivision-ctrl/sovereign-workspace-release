"""Author a spoken-audio TEST FIXTURE — Phase 17C `.mic` (directive §16 track 17C).

    py -3.12 tools/live/make_voice_fixture.py <out.wav> ["<phrase>"]

The `.mic` in-Electron receipt has to push REAL PCM through the shell's real capture handler on a host
where nobody is speaking into a microphone. This writes that PCM: 16 kHz mono 16-bit WAV of a spoken
phrase, produced by the Windows OS speech synthesizer.

**This is not TTS in the product sense, and it is deliberately kept where it cannot become that.**
I-V2 / D-VOICE-02 prohibit the SYSTEM speaking back to the operator; the frozen invariant is about the
product's voice OUTPUT surface. This tool synthesizes a transcription INPUT for a test, lives in
`tools/` rather than in a product tree (`apps/`, `adapters/`, `voice_bridge/`, `control_plane/`), and
plays nothing to any speaker — it writes a file. It is not, however, *unreachable* from the product:
the packaged Electron main requires the self-checks, which SPAWN this script under `SHELL_SELFCHECK`
(see the correction below — that reachability is the honest fact, and the file-only sink is what
actually enforces I-V2). The identical carve-out was made and recorded at Phase 16E
`.real` (`tools/live/real_parakeet_smoke.py`, receipt `PHASE16E_REAL_PARAKEET_SMOKE.json`: *"OS
System.Speech (test input only; NOT product TTS)"*); this is the same precedent, restated rather than
assumed.

**One clause of that argument went stale and is corrected here (Phase 17C `.close`, spec-audit
MINOR-8).** It used to say this tool "is imported by no shipped module". Since `.mic` and `.close` the
in-Electron self-checks SPAWN it, and those modules are `require`d unconditionally by the packaged
Electron main process — so the shipped app does contain a code path that reaches `System.Speech`. It is
reachable only under `SHELL_SELFCHECK`, and the self-checks now assert that themselves rather than
relying on nobody calling them by accident. The substantive guarantee is unchanged and is enforced
below by construction: the synthesizer's only sink is a file, verified present before `Speak` is
called at all.

Prints one JSON line describing what it wrote (or why it could not) and exits 0/1. Local processes
only (`powershell.exe`); no network, no credential, no model call (directive §2.2/§2.4).
"""
from __future__ import annotations

import json
import subprocess
import sys
import wave
from pathlib import Path

DEFAULT_PHRASE = "testing one two three four"
#: The format the WSL Parakeet path expects end-to-end — matching it here means the fixture exercises
#: the same container the renderer's encoder produces, not a lenient special case.
SAMPLE_RATE = 16000
CHANNELS = 1
BITS = 16
#: Generous: a cold System.Speech first use pays an assembly-load cost.
SYNTH_TIMEOUT_S = 90.0


def _powershell_script(out: Path, phrase: str) -> str:
    """The synthesis script, written so that **`Speak` can only ever reach a FILE**.

    This is where I-V2/D-VOICE-02 is actually enforced, and it has to be enforced by CONSTRUCTION
    rather than by the comment above. Under PowerShell's default `$ErrorActionPreference = 'Continue'`
    a .NET method exception is NON-terminating: if `SetOutputToWaveFile` throws — the path locked by
    antivirus, a handle left by a crashed run, a read-only directory, a full disk — execution would
    continue to the next `;` and `$s.Speak(...)` would render to the **default audio device**. The
    operator's machine would say the phrase out loud, `powershell.exe` would still exit 0 because
    `$s.Dispose()` succeeded, and this tool would report "wrote no file" — sending a reader looking for
    a filesystem problem rather than for the fact that the system just talked back.

    So: `$ErrorActionPreference='Stop'`, the whole thing in a try/catch that exits non-zero, and
    `SetOutputToWaveFile` verified to have taken effect before `Speak` is called at all.
    """
    # Single-quoted PowerShell literals; a quote inside the phrase is escaped by doubling it.
    lit = phrase.replace("'", "''")
    path_lit = str(out).replace("'", "''")
    return (
        "$ErrorActionPreference='Stop'; "
        "try { "
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        f"$fmt = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo({SAMPLE_RATE},"
        "[System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen,"
        "[System.Speech.AudioFormat.AudioChannel]::Mono); "
        f"$s.SetOutputToWaveFile('{path_lit}',$fmt); "
        # Belt and braces: only speak once the file sink is demonstrably in place. If redirection
        # silently failed, `Speak` would go to the speakers — so refuse instead.
        f"if (-not (Test-Path -LiteralPath '{path_lit}')) {{ throw 'the WAV sink was not created — refusing to synthesize to the default audio device' }}; "
        f"$s.Speak('{lit}'); "
        "$s.Dispose() "
        "} catch { [Console]::Error.WriteLine($_.Exception.Message); exit 1 }"
    )


def make_fixture(out: Path, phrase: str = DEFAULT_PHRASE) -> dict:
    """Write `out` and return a record of it. Fail-closed: any fault yields `ok:false` with the reason
    NAMED and no claim about a file that is not there — never a fabricated fixture."""
    record: dict = {
        "schema": "voice_fixture@1.0",
        "method": "OS System.Speech (test input only; NOT product TTS — I-V2/D-VOICE-02 stands)",
        "phrase": phrase,
        "path": str(out),
        "sample_rate": SAMPLE_RATE,
        "channels": CHANNELS,
        "bits_per_sample": BITS,
        "wav_bytes": 0,
        "seconds": None,
        "ok": False,
        "error": None,
    }
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        proc = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", _powershell_script(out, phrase)],
            capture_output=True, text=True, timeout=SYNTH_TIMEOUT_S, check=False,
        )
        if proc.returncode != 0:
            record["error"] = f"System.Speech exited {proc.returncode}: {(proc.stderr or '').strip()[:200]}"
            return record
        if not out.exists():
            record["error"] = "System.Speech reported success but wrote no file"
            return record
        record["wav_bytes"] = out.stat().st_size
        # Verify the container rather than assume it: a fixture that is silently 8 kHz or stereo would
        # make a downstream transcription failure look like an engine fault.
        with wave.open(str(out), "rb") as wf:
            record["sample_rate"] = wf.getframerate()
            record["channels"] = wf.getnchannels()
            record["bits_per_sample"] = wf.getsampwidth() * 8
            frames = wf.getnframes()
            record["seconds"] = round(frames / float(wf.getframerate() or SAMPLE_RATE), 3)
        if record["channels"] != CHANNELS or record["bits_per_sample"] != BITS:
            record["error"] = (f"fixture is {record['channels']}ch/{record['bits_per_sample']}-bit; "
                               f"the capture path requires mono 16-bit")
            return record
        if not record["wav_bytes"] or not record["seconds"]:
            record["error"] = "fixture contains no audio frames"
            return record
        record["ok"] = True
    except subprocess.TimeoutExpired:
        record["error"] = f"System.Speech did not finish within {SYNTH_TIMEOUT_S}s"
    except Exception as exc:  # noqa: BLE001 — reported, never faked
        record["error"] = f"{type(exc).__name__}: {exc}"
    return record


def main(argv: list[str]) -> int:
    if not argv:
        sys.stderr.write("usage: make_voice_fixture.py <out.wav> [\"<phrase>\"]\n")
        return 2
    record = make_fixture(Path(argv[0]).resolve(), argv[1] if len(argv) > 1 else DEFAULT_PHRASE)
    sys.stdout.write(json.dumps(record) + "\n")
    return 0 if record["ok"] else 1


if __name__ == "__main__":  # pragma: no cover - exercised via tests calling make_fixture()
    raise SystemExit(main(sys.argv[1:]))
