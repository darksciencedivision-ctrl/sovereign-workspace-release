# PHASE 16E `.real` — EVIDENCE REPORT (closes gate/phase-16e)

**Work unit:** `phase-16e.real` (final sub-step of the Phase 16E decomposition `.engine → .wire → .real`)
**Date:** 2026-07-25 · **Iteration:** 68 · **Status:** PASS → **gate/phase-16e CLOSES**
**Tag:** `gate/phase-16e` (lands with this unit; whole-track gate, same convention as 14A/15E/16C/16D —
closes only when the final sub-step lands, with independent gate-validator confirmation. 16E is NOT a
directive-flagged high-stakes gate — only 16A/16F are — but independent confirmation was obtained.)
**Governing directive:** `AUTONOMOUS_BUILD_DIRECTIVE.md` **§15 track 16E** (*Talk button → capture → STT →
bridge → conductor input, end-to-end (closes U67): **real Parakeet if NeMo present**, else mock STT with
a VISIBLE "mock engine" indicator; write docs/OPERATOR_NEMO_INSTALL.md; TTS still NOT built*), **§13 item
5 (OP-8)**, **§10.3 / OP-9** (NeMo stack authorized), loop protocol §3, substitution §6, D-P16-0 (in-
Electron self-check), honesty §10.4. Load-bearing invariants: **1** (operator authority; never self-
authorize), **3** (fail-closed; visible engine; no fabricated delivery), **24/26** (STT-only;
transcribe-then-discard), **25** (voice cannot expand authority — propose, never execute), **I-V2/
D-VOICE-02** (no TTS), **I-A1** (engine agnostic behind the interface), **7** (no auth logic in MCP).

---

## 1. The operator defect this closes (OP-10 finding 3: "voice unusable")

The mock-vs-real choice ran `importlib.util.find_spec("nemo")` in the **host Windows** interpreter. On
the canonical topology NeMo is installed in **WSL2** (a Windows-native install cannot build numpy without
MSVC), so the host probe is **structurally always False** — real Parakeet was NEVER selected even on a
host where it is fully installed and working. The shell therefore always showed "mock engine". `.real`
fixes the detection to probe **inside WSL**, adds the real WSL-routed `STTEngine`, and surfaces the state
honestly. **Verified on this host: the real stack is present and works** (NeMo 2.7.3, torch 2.13.0+cu132,
`torch.cuda.is_available()=True`, checkpoint `nvidia/parakeet-tdt-0.6b-v3` cached 2.4 GB).

## 2. What this sub-step delivers

| Area | Change |
|---|---|
| **WSL detection fix** | `adapters/voice_parakeet/engine.detect_voice_stack()` now probes `nemo` via a **cached, timeout-bounded** `wsl.exe -- bash -c '<venv>/bin/python -c "import nemo"'` (fail-closed: no WSL/venv/nemo, non-zero exit, or timeout ⇒ `nemo:false`). `real_parakeet_available(detection=None)` accepts a pre-computed dict to avoid re-probing. A lazy import breaks the module cycle. |
| **Real adapter (I-A1)** | NEW `adapters/voice_parakeet/wsl_parakeet.py`: `WslParakeetSTT` (name `parakeet-wsl`) transcribes a real WAV by streaming a tiny NeMo program to the WSL venv python over stdin (`python - <wav> <model>`), parsing one JSON line. `WslConfig` (distro/venv/model from env, defaults per the install doc), `to_wsl_path` (Windows→`/mnt/...`, spaces preserved), `parse_transcript` (confidence policy below), `_probe_nemo`/`wsl_nemo_available` (lru-cached), `build_real_engine`, `VoiceEngineError`. The `runner` is injectable so every branch is deterministic without a live GPU. |
| **Confidence policy** | NeMo's hypothesis `.score` is a **log-probability** (observed −29.8), NOT a 0..1 confidence — feeding it to the bridge's 0.6 threshold would route **every** real utterance to CLARIFY ("unusable" again). `parse_transcript` derives confidence from recognition: non-empty transcript ⇒ 1.0 (confident), empty ⇒ 0.0 (repeat). A genuine in-[0,1] confidence is respected; a raw log score is ignored. |
| **Honest selection** | `conductor_voice_feed.select_engine(engine=None, *, for_capture=False, detection=None, real_engine_factory=None)`: the real engine is used **only for a real capture** (`for_capture=True`) on a real-stack host; the headless indicator poll (a PCM-less `audio:` stand-in) stays on the mock but reports `real_available:true` + `real_engine:"parakeet-wsl"` truthfully. A real-adapter init fault falls back to the visible mock (fail-closed). Never `mock:false` without a real engine. |
| **3-state indicator** | `terminal/compositor/voice-indicator.voiceEngineIndicator` now renders **real** (a real engine produced the transcript), **ready** (real installed; this stand-in transcript is the mock's → label "`<real engine> ready`"), or **mock** (no real stack → "mock engine"). `mock` is true ONLY when no real stack — the operator's complaint fix. `renderer.js` uses the indicator label. |
| **Self-check (D-P16-0)** | `apps/desktop/selfcheck/voice-selfcheck.js` is host-aware: on a real-stack host it asserts the badge reads "`… ready`" (NOT "mock engine"), `real_available` matches the WSL-probed detection, and the stand-in transcript is still the mock's (no fabricated real transcript). Writes `docs/evidence/receipts/PHASE16E_REAL_SELFCHECK.json`. |
| **Live evidence tool** | NEW `tools/live/real_parakeet_smoke.py` — reproducible on-host proof the real adapter transcribes real speech via WSL→NeMo→GPU (skip-with-record on a host without the stack). |
| **Operator doc** | `docs/OPERATOR_NEMO_INSTALL.md` scope note updated: `.real` landed; how detection/transcription work; what remains OWED to 16F. |

## 3. Self-check — every exit criterion, real command output (fresh, foreground, D-LOOP-2)

- **Python** `py -3.12 -m pytest tests/ -q` → **1109 passed / 0 failed** (209.53 s). +23 vs `.wire`'s
  1086 (NEW `test_wsl_parakeet.py` 18; feed real-path tests +5). Voice subset re-run clean (74 passed).
- **terminal JS** `node --test "terminal/test/**/*.test.js"` → **173 passed / 0 failed** (+3 indicator
  ready-state tests).
- **apps/desktop JS** `node --test "apps/desktop/test/**/*.test.js"` → **158 passed / 0 failed**.
- **In-Electron self-check** `node apps/desktop/selfcheck/run.js voice` (packaged Electron 31.7.7 / Node
  20.18.0 / win32-x64, hard 150 s) → **exit 0 / PASS**. `PHASE16E_REAL_SELFCHECK.json` `ok:true`, all 15
  checks true (`capture_sourced, capture_is_chat, capture_has_transcript, engine_detection_honest,
  no_fabricated_real_transcript, self_authorized_false, no_tts, conductor_write_owed_honest,
  rendered_engine_indicator, badge_not_mislabelled_mock, rendered_outcome, write_reported_written,
  write_echoed_into_pty, protected_queued, protected_not_delivered`). Rendered badge:
  **`🎙 parakeet-wsl ready · Delivered to conductor`** (`engine.real_available:true`, `detection.nemo:true`,
  `engine.mock:true` for the stand-in — honest). A SAFE utterance routed CHAT and echoed into a real
  admitted PTY (`write=true echoed=true`); a destructive utterance ("terminate node-B") routed
  `proposed_action` → **queued, never delivered** (invariant 25).
- **LIVE real transcription** `py -3.12 tools/live/real_parakeet_smoke.py` → **`ok:true`**
  (`PHASE16E_REAL_PARAKEET_SMOKE.json`): an OS-synthesized fixture of the spoken phrase *"testing one two
  three four"* was transcribed by the **real shipped adapter** through WSL→NeMo→GPU in ~37 s →
  `transcript_text = "Testing 1234"`, `confidence = 1.0`, `recognized_spoken_content:true`. This is the
  real engine genuinely recognizing speech on this host.

## 4. Substitutions & honesty (directive §6 / §10.4)

- **Real engine PRESENT and used for real capture; live *mic* PCM + interactive conductor ConPTY session
  remain OWED to 16F.** The headless indicator poll uses the mock stand-in **by design** (a PCM-less ref
  has nothing for a real engine to transcribe); the real adapter is proven end-to-end on real audio by
  the smoke tool above. Nothing is overclaimed: a stand-in `audio:` ref through the real engine RAISES
  `VoiceEngineError` (never a fabricated transcript).
- **Test-fixture generator, NOT product TTS.** `tools/live/real_parakeet_smoke.py` uses the OS speech
  synthesizer to make a transcription **input** WAV. It lives outside the product voice path
  (`adapters/`, `apps/`) and is labeled a test fixture. The PRODUCT still exposes **no** speech-synthesis
  method or affordance — **I-V2 / D-VOICE-02 intact** (`tts:false` carried on every feed/result).
- **Mock-first, no live model call (§2.4/§10.4):** the voice path spawns no `claude`/`codex`. Only local
  `wsl.exe` (NeMo) and, in the evidence tool, `powershell.exe` (fixture) are spawned — **no credential,
  no network** (the NeMo stack was operator-installed under OP-9/§10.3). D-LOOP-1: all subprocess calls
  are synchronous (`subprocess.run`) — no lingering process.
- **Fail-closed everywhere (invariant 3):** absent WSL/venv/NeMo, non-zero exit, timeout, malformed
  output, or a stand-in ref each read as not-available / `VoiceEngineError`; the indicator shows "mock
  engine" ONLY when no real stack — never a claimed real engine without one.
- **Confidence policy — disclosed tradeoff (both reviewers, non-blocking, owned for 16F).** NeMo emits a
  log-prob, not a calibrated 0..1 confidence, so `parse_transcript` derives confidence from recognition
  (non-empty ⇒ 1.0, empty ⇒ 0.0). This FIXES the original defect (a raw −29.8 score fed to the bridge's
  0.6 threshold would route **every** real utterance to CLARIFY — "unusable" again). The tradeoff: the
  graduated "mumble → clarify" gate is inactive on the real path (any non-empty recognition is treated as
  confident); only an empty transcript clarifies. Invariant 25 is **unaffected** (destructive/protected
  verbs queue via verb classification, independent of confidence). A calibrated real-confidence source
  would restore gradation — recorded as a **16F calibration item**, not a failure.

## 5. Independent review

- **spec-auditor: CLEAN** (no invariant violations). Confirmed I-V2/D-VOICE-02 (product exposes no
  synthesis method; the only `SpeechSynthesizer` call is the out-of-product test-fixture generator in
  `tools/live/`, deleted on exit, labeled as such — legitimate, not TTS drift), 24/25/26 (STT-only;
  destructive verbs queue via verb classification regardless of the new engine; no PCM retained),
  invariant 1 (shell forwards, Python decides), invariant 3 (every fault ⇒ not-available / VoiceEngineError,
  never a fabricated transcript or claimed real engine), §2.2/§2.4/§2.5/§2.7 (only local `wsl.exe`/
  `powershell.exe`; no credential; no `claude`/`codex`), invariant 7 (`mcp_server/` untouched), I-A1,
  D-LOOP-1 (synchronous `subprocess.run`). **1 MINOR + 2 NITs, all disclosed/non-blocking** — see §4
  honesty note on the confidence policy.
- **gate-validator: PASS_WITH_RESERVATIONS — "Gate may close."** Reproduced in an isolated context on
  this host (no builder receipt taken on faith): `pytest tests/` → **1109 passed (215.66 s), twice**;
  `node --test` terminal **173** / apps/desktop **158**; the in-Electron self-check **regenerated by the
  validator** → `ok:true`, all 15 checks, badge `🎙 parakeet-wsl ready`; `tools/live/real_parakeet_smoke.py`
  **re-run** → `"Testing 1234"` / confidence 1.0 / `recognized_spoken_content:true` (41.8 s).
  **Load-bearing falsification** (in-process monkeypatch, zero byte mutation): breaking `_probe_nemo`
  flips `detect_voice_stack()['nemo']` → False and `select_engine(for_capture=True)` → visible mock
  (honest); restored, `git status` unchanged. Frozen canonical 4-hash set verified intact (6D3FD03B /
  8C9B7240 / 668089B5 / CC414372); `docs/canonical/`, `mcp_server/`, `schemas/`, `CLAUDE.md` diff empty.
  Reservations (owned, non-blocking): (1) real-engine confidence is presence-based → the graduated
  low-confidence CLARIFY guard is inactive on the real path (see §4 — a 16F calibration item, not a
  failure); (2) D-LOOP-1 orphan-freedom evidenced indirectly (clean exit codes / synchronous
  `subprocess.run` / `bridge.close()` — no leak, just not `tasklist`-enumerated); (3) validation was
  against the pre-commit working tree (expected — this commit closes the sub-step).

## 6. Files

New: `adapters/voice_parakeet/wsl_parakeet.py`, `tests/integration/test_wsl_parakeet.py`,
`tools/live/real_parakeet_smoke.py`, `docs/evidence/receipts/PHASE16E_REAL_SELFCHECK.json`,
`docs/evidence/receipts/PHASE16E_REAL_PARAKEET_SMOKE.json`, this report.
Edited: `adapters/voice_parakeet/engine.py`, `adapters/voice_parakeet/__init__.py`,
`control_plane/orchestration/conductor_voice_feed.py`, `terminal/compositor/voice-indicator.js`,
`apps/desktop/renderer/renderer.js`, `apps/desktop/selfcheck/voice-selfcheck.js`,
`terminal/test/voice-indicator.test.js`, `tests/integration/test_conductor_voice_feed.py`,
`tests/integration/test_voice_input.py`, `docs/OPERATOR_NEMO_INSTALL.md`.

**U67 status:** READ half (`.engine`) + WRITE half (`.wire`) + **REAL engine (`.real`)** all closed.
**gate/phase-16e CLOSES.** Remaining for 16F (operator-run assembled run): real microphone PCM capture
and the admitted live interactive conductor ConPTY session (voice → live conductor, end-to-end).
