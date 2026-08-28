# Operator guide — real Parakeet/NeMo voice-IN (WSL2)

**Status:** the shell ships with voice-IN wired end-to-end (talk button → STT → the Sovereign
`ConductorVoiceBridge` → conductor input). When the real NeMo/Parakeet stack below is installed, the
shell **detects it inside WSL and uses the real engine** for your live speech; the conductor pane's
voice badge then shows `<engine> ready` (and a real transcript when you speak) instead of `mock engine`.
Without the stack, the engine is a **mock**, always shown as `mock engine`, so you are never misled into
thinking real speech recognition is running. This guide is the **operator-run** install that provides
the real **NVIDIA Parakeet** engine (NeMo, in WSL2). It is optional; nothing here creates an account,
uses a paid service, or handles a credential (directive §2). The checkpoint is CC-BY-4.0 (U4 noted).

> **Scope note (Phase 16E).** `16E.wire` closed the shell WIRING of voice-IN (this doc + the talk button
> + delivery into the conductor). **`16E.real` (landed) activates the real engine:** it fixes stack
> **detection** to probe NeMo *inside* WSL (a cached, timeout-bounded `wsl.exe` import check — a
> Windows-native `import nemo` is structurally always false here) and routes real transcription through
> the WSL venv interpreter (`adapters/voice_parakeet/wsl_parakeet.WslParakeetSTT`), fail-closed to the
> visible mock. Verified on this host: `py -3.12 tools/live/real_parakeet_smoke.py` transcribed spoken
> audio via WSL→NeMo→GPU (receipt `docs/evidence/receipts/PHASE16E_REAL_PARAKEET_SMOKE.json`). Still
> **owed to 16F** (operator-run): real *microphone* PCM capture and the admitted live interactive
> conductor ConPTY session; the headless indicator poll uses the mock stand-in by design (no PCM).

## Prerequisites

- Windows 11 with an NVIDIA GPU and a recent driver (CUDA UMD ≥ 13.x visible from WSL).
- WSL2 with a **real** Ubuntu distro as default (not the Docker Desktop stub — it has no python/sudo):
  ```powershell
  wsl --install -d Ubuntu-24.04
  wsl --set-default Ubuntu-24.04
  ```

## The two-command install (run inside WSL)

From `wsl -d Ubuntu-24.04`:

```bash
# 1) create an isolated venv and install NeMo's ASR stack
python3 -m venv ~/nemo-venv && ~/nemo-venv/bin/pip install --upgrade pip "nemo-toolkit[asr]"

# 2) fetch + verify the Parakeet checkpoint (downloads ~2.5 GB to ~/.cache/huggingface on first run)
~/nemo-venv/bin/python -c "import nemo; from nemo.collections.asr.models import EncDecRNNTBPEModel as M; M.from_pretrained('nvidia/parakeet-tdt-0.6b-v3'); print('Parakeet ready')"
```

If step 2 prints `Parakeet ready`, the stack is good.

## GPU-specific caveat (verified on this host — RTX 5060 Ti / Blackwell sm_120)

Newer Blackwell GPUs need a CUDA-13 torch build; the default `cu126` wheels carry no kernel image for
`sm_120` and fail at `.to(cuda)`. If you hit `torch.AcceleratorError`, replace torch and repair the pins
NeMo's cu12 extras pull back:

```bash
~/nemo-venv/bin/pip install --force-reinstall torch --index-url https://download.pytorch.org/whl/cu132
~/nemo-venv/bin/pip install "cuda-pathfinder>=1.4.2" "cuda-python>=13.0" "setuptools>=79" "fsspec==2024.12.0"
```

Verify: `wsl -d Ubuntu-24.04 -- nvidia-smi` shows the GPU, and
`~/nemo-venv/bin/python -c "import torch; print(torch.__version__, torch.cuda.is_available())"` reports a
`+cu132` build with `True`.

> **Do NOT** reinstall `nemo-toolkit[asr,cu12]` or otherwise re-resolve the pins afterward — it
> reintroduces the broken `cu126` torch. The venv intentionally mixes NeMo's cu12 extras with the cu13
> torch stack; that combination is runtime-verified working.

## How the shell invokes it (for reference — `16E.real` wires this)

```
wsl.exe -d Ubuntu-24.04 -- /home/<you>/nemo-venv/bin/python <transcribe args>
model id: nvidia/parakeet-tdt-0.6b-v3
```

The stack **detection** the shell runs must therefore probe *inside* WSL, because a Windows-native
`import nemo` is structurally always false here (no MSVC to build numpy). When the WSL probe fails or
times out, the shell falls back to the visible mock engine — it never silently claims real speech.

### The probe, and its two knobs (Phase 17C, U74)

The probe runs the import a transcription actually performs —
`wsl.exe [-d <distro>] -- bash -c '<venv>/bin/python -c "from nemo.collections.asr.models import ASRModel"'`
— not a bare `import nemo`, which on this stack is a ~0.04 s namespace import that succeeds even when
ASR is unusable. Measured on the build host 2026-07-26: **17.9 s cold, 7.0 s warm**. It runs in the
background at launch, so the badge never blocks the window; while it is open the badge reads
`probing…`, and **clicking the badge re-checks now** (useful the moment you finish this install).

| Environment variable | Default | What it does |
|---|---|---|
| `SOW_WSL_DISTRO` | the WSL default distro | which distro to enter |
| `SOW_NEMO_VENV` | `$HOME/nemo-venv` | where the venv lives |
| `SOW_PARAKEET_MODEL` | `nvidia/parakeet-tdt-0.6b-v3` | the checkpoint |
| `SOW_NEMO_PROBE_TIMEOUT_S` | `90` | how long the probe may take before it fails closed — raise it on a slow/cold host |
| `SOW_NEMO_TRANSCRIBE_TIMEOUT_S` | `180` | how long one transcription may take |

Both timeouts are honoured end-to-end (the shell derives its own ceilings from them, so raising one
here is not silently overridden). A malformed value falls back to the default rather than disabling
voice. A positive probe result is reused for 15 minutes; a negative one for 30 seconds, after which it
is re-taken automatically — an answer is never pinned for the life of the app.

## What voice-IN does and does not do

- **Does:** transcribe your speech and route it to the conductor on the *same path as typing* — ordinary
  speech becomes conductor chat; a protected/destructive command becomes a **proposal queued for your
  approval** (never auto-executed — invariant 25); a low-confidence utterance asks you to repeat. Audio
  is **transcribe-then-discard** (invariant 26).
- **Does NOT:** speak back. Voice **output/TTS is prohibited** by the frozen invariant I-V2 / D-VOICE-02
  (voice input only). Spoken replies would require an explicit operator reversal (register OP-9) — until
  then, the conductor answers in text.
