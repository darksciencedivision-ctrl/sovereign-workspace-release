# PHASE 14D EVIDENCE REPORT — Real Parakeet/NeMo (FAILED ENTRY ATTEMPT → SKIP-WITH-RECORD)
Autonomous loop iteration 27 · 2026-07-18Z · **NOT a passed gate — no `gate/phase-14d` tag**
Track: 14D (directive §9 table 14D + §10.3). Outcome: **entry condition unmet in this
non-interactive session → skip-with-record (directive §10.4)**. Does **not** block 14E.
`next_step → phase-14e`.

## Objective the track would prove (directive §9 table 14D)
Real Parakeet/NeMo, specifically the **REAL engine** (mock STT is out of scope for 14D — the
Phase-12 gate already proved the governed broker/equivalence/disposal path with MockSTT behind
the I-A1 interface):

- NeMo in WSL2;
- host WASAPI → WSL microphone bridge, real transcription;
- measure **U1** (streaming latency / VRAM under concurrency) and **U2** (bridge design + PTT trigger);
- verify transcript disposal + typed/voice equivalence **with the real engine**;
- TTS stays absent.
- Precondition: 14A stable (it is — `gate/phase-14a` closed iter 19).

## Entry condition (directive §9 table 14D + §10.3)
> Operator authorizes the WSL pip/NeMo install (network-prohibition amendment §10.3: PyPI/NVIDIA
> indexes; no paid services/accounts/API keys; CC-BY-4.0 checkpoint from its official model
> source, hash recorded, U4 attribution noted). **If the environment cannot support the install
> (driver/CUDA/WSL constraints), record precisely what failed and skip-with-record — never fake.**

Operator authorization is **present** (register OP-4/OP-5, directive §10.3): the WSL/NeMo install
is authorized in principle. The entry condition is therefore **not** an authorization gap — it is
an **environment/executability** gap in this non-interactive session, which §10.3 explicitly names
as a skip-with-record condition.

## Probe — precisely what was checked and what it returned (real command output)

### 1. Host shape
```
$ uname -a
MINGW64_NT-10.0-26200 DESKTOP-03PTABH 3.4.10-2e2ef940.x86_64 2024-07-09 21:35 UTC x86_64 Msys
$ which wsl        →  /c/WINDOWS/system32/wsl        (wsl.exe present on PATH)
```
Native Windows 11 host (Git Bash / MINGW64). `wsl.exe` exists.

### 2. WSL is inaccessible to THIS session
```
$ wsl.exe -l -v      →  "This command requires approval"   (denied; non-interactive, no approver)
$ wsl.exe --status   →  "This command requires approval"   (denied)
```
Every `wsl.exe` invocation is approval-gated and there is no approver in this autonomous loop, so
this session **cannot enter WSL at all** — cannot run `nvidia-smi` inside WSL, cannot verify GPU
passthrough, cannot `pip install` the NeMo/torch stack, cannot import NeMo, cannot run a real
transcription. Host filesystem **outside the repo root** is likewise permission-gated (correct per
prohibition §2.5), so even a filesystem inspection of the WSL distro / NVIDIA driver is unavailable.

### 3. Host-side voice-stack detection (in-repo, no WSL needed) — the decisive signal
Ran the Phase-12 detector (`adapters/voice_parakeet/engine.detect_voice_stack`), a pure host probe
that checks NeMo importability and `nvidia-smi`/`wsl` on PATH:
```
$ py -3.12 -c "import json,sys; sys.path.insert(0,'.'); from adapters.voice_parakeet.engine \
    import detect_voice_stack, real_parakeet_available; \
    print(json.dumps({'detect':detect_voice_stack(),'real_parakeet_available':real_parakeet_available(),'python':sys.version.split()[0]}))"
{"detect": {"nvidia_gpu": true, "wsl": true, "nemo": false}, "real_parakeet_available": false, "python": "3.12.10"}
```
(That line is the literal `json.dumps` stdout of the command shown. The gate-validator ran the
equivalent bare form and got the raw-repr rendering `{'nvidia_gpu': True, 'wsl': True, 'nemo': False} False`
— same three values, `nemo` unimportable, `real_parakeet_available()` False.)
- `nvidia_gpu: true` — an NVIDIA driver/`nvidia-smi` is on the host PATH (consistent with the
  Phase-12 finding: GPU + WSL present).
- `wsl: true` — `wsl` is on PATH (the distro is registered) — but see §2: this session cannot
  *invoke* it.
- **`nemo: false`** — the NeMo Python package is **not importable** on the host Python. The real
  engine is not installed.
- **`real_parakeet_available: false`** — the code's own gate for wiring the real engine (GPU ∧ WSL ∧
  NeMo) is **False**. `adapters/voice_parakeet/engine.py` therefore stays on `MockSTT` behind the
  I-A1 contract, exactly as at Phase 12.

## Why this is a failed entry attempt and not a substitutable criterion
Directive §6 requires substituting the nearest faithful equivalent **and running the full governance
path around it** — but for 14D the substitution (**MockSTT behind the I-A1 interface + the real
Permission Broker**) was **already built and gated at Phase 12** (`gate/phase-12`, 322 tests). 14D's
entire reason to exist is the **REAL** engine: real NeMo transcription, real host-WASAPI→WSL mic
bridge, and real measurements of U1 (latency/VRAM under concurrency) and U2 (bridge/PTT). None of
those is producible here:

1. **No WSL access** — every `wsl.exe` call is denied in this non-interactive session (§2 above); the
   pip/NeMo install the operator authorized cannot be executed by this loop.
2. **NeMo absent** — `real_parakeet_available()` is `False`; there is no real engine to drive even if
   audio were available.
3. **No live audio path** — the WASAPI→WSL microphone bridge and real transcription fundamentally
   require live operator speech into a microphone; a headless, non-interactive loop has no such input
   even with a working GPU/WSL/NeMo stack. U1/U2 are empirical hardware/latency measurements that
   cannot be honestly synthesized.

Building *more* mock would neither advance 14D nor be honest (§6: "Never present a substituted result
as the real-provider result"). The only correct outcome is to **record precisely what failed and
skip-with-record** (§10.3/§10.4).

## What was NOT done (explicit, so nothing is overclaimed)
- **No** WSL entry, **no** pip install, **no** NeMo/torch import, **no** CC-BY-4.0 checkpoint download
  (so §10.3's checksum/source-URL/U4-attribution recording is **moot** — recorded as unused, honest).
- **No** real transcription, **no** mic-bridge exercise, **no** U1/U2 measurement.
- **No** source code changed this iteration (the Phase-12 voice surface is untouched).
- **No** `gate/phase-14d` tag (a skipped track is not a passed gate — directive §9).
- **No** credential handling, no network use, nothing outside the repo root (§2 intact).

## Register effects (append-only)
- **DECISION_REGISTER** — new row: Phase 14D **SKIP-WITH-RECORD** (failed entry attempt; environment
  cannot support the real NeMo install / real transcription in this non-interactive session; operator
  authorization present but un-executable here; does not block 14E; `next_step → phase-14e`).
- **UNRESOLVED_ISSUE_REGISTER** — U1 (Parakeet latency/VRAM under concurrency) and U2 (mic→WSL bridge
  + PTT) stay **OPEN-FOR-HARDWARE**; new note records the 14D failed-entry and the decisive probe.
  U4 (CC-BY-4.0 attribution) stays OPEN — checkpoint never downloaded, attribution not yet required.

## What a future 14D run requires (for the operator/hardening pass)
An **operator-run** session on the Windows host that: (a) opens WSL2 with GPU passthrough
(`nvidia-smi` visible inside WSL); (b) `pip install`s the NeMo/Parakeet stack inside WSL (§10.3
network amendment); (c) downloads the CC-BY-4.0 Parakeet checkpoint from its official source, records
its hash + U4 attribution; (d) wires the host-WASAPI→WSL mic bridge; (e) with live audio, measures U1
(latency/VRAM under concurrency) and U2 (bridge/PTT) and verifies real-engine transcript disposal +
typed/voice equivalence through the existing Permission Broker path. The I-A1 interface
(`adapters/voice_parakeet/engine.py`) already accepts a real `STTEngine` behind the same contract —
only the real engine and the live audio bridge are missing, both hardware/interactive-session bound.

## Gate self-check (skip-with-record)
| Item | Result |
|---|---|
| Entry condition executable in this session? | **NO** — WSL denied; NeMo absent; no live audio |
| Operator authorization present? | YES (OP-4/OP-5, §10.3) — but un-executable here |
| Substitution that advances 14D short of the real engine? | **NONE** — mock path already gated at P12 |
| Anything faked or overclaimed? | **NO** — real probe output only; no synthesized measurement |
| `gate/phase-14d` tag applied? | **NO** — skip-with-record is not a passed gate |
| Blocks 14E? | **NO** — §10.4; `next_step → phase-14e`, degrades honestly |
| §2 prohibitions intact? | YES — no network, no credentials, no out-of-repo writes |

**Outcome: PHASE 14D — SKIP-WITH-RECORD (failed entry attempt, honestly recorded). `next_step → phase-14e`.**
