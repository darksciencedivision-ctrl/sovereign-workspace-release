# PHASE 16E `.wire` — EVIDENCE REPORT

**Work unit:** `phase-16e.wire` (sub-step 2 of the Phase 16E decomposition, now **`.engine` → `.wire` → `.real`**)
**Date:** 2026-07-25 · **Iteration:** 67 · **Status:** PASS (sub-step)
**Tag:** none. `gate/phase-16e` closes only when the final `.real` sub-step lands (WSL real-Parakeet
detection + adapter), with the independent gate-validator. (16E is NOT a directive-flagged high-stakes
gate — only 16A/16F are — but gate-validator confirmation was obtained for this sub-step too.)
**Governing directive:** `AUTONOMOUS_BUILD_DIRECTIVE.md` **§15 track 16E** (*Talk button → capture → STT →
bridge → conductor input, end-to-end (closes U67): real Parakeet if NeMo present, else mock STT with a
VISIBLE "mock engine" indicator; write docs/OPERATOR_NEMO_INSTALL.md; TTS still NOT built*), **§13 item 5
(OP-8 — voice INPUT to the conductor, same command path as typing)**, loop protocol §3, substitution
§6, D-P16-0 binding (in-Electron self-check), honesty §10.4. Load-bearing invariants: **1** (operator
holds final authority — the app never self-authorizes), **25** (voice cannot expand authority — propose,
never execute), **24/26** (STT-only; transcribe-then-discard), **I-V2/D-VOICE-02** (no TTS), **3**
(fail-closed; a mock engine is always visibly indicated; no fabricated delivery).

---

## 1. Re-decomposition — a `.real` sub-step is added (directive §3.2)

`.engine` scoped the decomposition as `.engine → .wire`. This sub-step **re-decomposes to
`.engine → .wire → .real`**, recorded honestly here and in `LOOP_STATE.json`. Rationale:

- The track spec has two arms: *"real Parakeet if NeMo present, **else** mock STT with a VISIBLE mock
  indicator."* `.wire` ships the shell WIRING end-to-end with the **mock** arm, always visibly indicated
  — exactly the "else" clause, and honest.
- The **real** arm is larger than a wiring change and the operator flagged it precisely (host-fact note,
  2026-07-24): `adapters/voice_parakeet/engine.detect_voice_stack()` probes `import nemo` in the **host
  Windows** interpreter, which is structurally always false under the canonical topology (NeMo is
  installed in **WSL2**, Windows-native install fails to build numpy without MSVC). Fixing this requires
  (a) a timeout-bounded WSL probe (`wsl.exe -d Ubuntu-24.04 -- <venv>/python -c "import nemo"`), (b) a
  real `STTEngine` adapter that routes transcription through that interpreter, and (c) a fail-closed mock
  fallback — a substantial, verify-heavy unit with its own capability probe. Folding it into `.wire`
  would exceed one reviewable work unit (the exact over-reach that stalled 16d.recovery). It is deferred
  to `.real`, keeping each unit test-first and reviewable. The mock engine is **visibly** the mock until
  then (never a silent pretend-to-hear), so nothing is overclaimed.

## 2. What this sub-step delivers (the WRITE half of U67)

`.engine` shipped the read half (`apps/desktop/voice/voice-source.js` sourcing `conductor_voice_feed@1.0`
from the REAL `ConductorVoiceBridge`; not yet imported by the shell). `.wire` connects it to the shell:

| Area | Change |
|---|---|
| **Delivery decision (pure)** | `apps/desktop/voice/deliver.js` — `decideDelivery(feed)` delivers a transcript into the conductor input **only** for a sourced CHAT outcome with real text; a `proposed_action`/`queued` is refused (invariant 25), a `clarify` is refused. `buildCaptureResult(feed, write)` folds the sourced feed + the actual PTY-write result; `delivered_to_conductor` is true **only** when the write landed (never fabricated). 10 unit tests. |
| **Main handler** | `apps/desktop/main.js` — `voice:capture` (replaces record-only `voice:propose`) sources the feed, routes by `decideDelivery`, and on CHAT calls `deliverConductorChat(text)` → `manager.write(conductorPaneId, text+"\r")` — the **same command path as typing** (`pane:input`). Returns `selfAuthorized:false` (the shell forwards the bridge's verdict; it decides nothing — invariant 1). `voiceState()` now carries the VISIBLE engine indicator. |
| **Preload / renderer** | `preload.js` exposes `captureVoice`; the 🎤 talk button (`renderer.js`) calls it then `refreshVoice()`; the conductor chrome paints a `.cvoice` badge — engine tag (`mock engine`, always visible) + last outcome (Delivered / Queued / repeat). CSS in `index.html`. |
| **Fail-closed resize guard** | `pane:resize` now guards on `manager.registry.has(id)` (fail-closed to `{resized:false}`) instead of throwing a TypeError on the session-less pinned CONDUCTOR placeholder pane — a real unguarded-error class the gate-validator flagged; fixed. |
| **In-Electron self-check (D-P16-0)** | `apps/desktop/selfcheck/voice-selfcheck.js` (+ `run.js`/`main.js` `voice` kind) drives the REAL talk-button path inside the packaged runtime and writes `docs/evidence/receipts/PHASE16E_VOICE_SELFCHECK.json`. |
| **Operator doc** | `docs/OPERATOR_NEMO_INSTALL.md` — the two-command WSL NeMo/Parakeet install (with the verified RTX-5060-Ti/cu132 caveat + the "do not re-resolve pins" caution), and the honest note that TTS is prohibited (I-V2) pending OP-9. |

## 3. Self-check every exit criterion (real command output)

**JS unit suites** (`node --test`, this host, foreground):
- `apps/desktop/test/*.test.js` → **158 passed / 0 failed** (incl. `voice-deliver.test.js` 10 tests +
  two LIVE tests exercising the real Python emitter: chat-with-visible-mock-engine-and-no-TTS, and
  destructive-utterance-queued-never-delivered).
- `terminal/test/*.test.js` → **170 passed / 0 failed** (incl. the voice-indicator engine-visibility tests).

**Python suite** (`py -3.12 -m pytest tests/ -q`, foreground): **1086 passed / 0 failed** (205.74 s).
No Python changed this sub-step; re-run fresh per D-LOOP-2, not trusted from `.engine`.

**In-Electron voice self-check** (`node apps/desktop/selfcheck/run.js voice`, packaged Electron runtime,
hard 150 s timeout): **exit 0 / PASS**. Receipt `PHASE16E_VOICE_SELFCHECK.json` — `ok:true`, all 13
checks true:
`capture_sourced, capture_is_chat, capture_has_transcript, engine_visible_mock, self_authorized_false,
no_tts, conductor_write_owed_honest, rendered_engine_indicator, rendered_outcome, write_reported_written,
write_echoed_into_pty, protected_queued, protected_not_delivered`. Badge rendered:
`🎙 mock engine · Delivered to conductor`. A SAFE utterance ("show status") routed CHAT and its transcript
was **written into a real admitted PTY and echoed back** (`write=true echoed=true`); a
protected/destructive utterance ("terminate node-B") routed `proposed_action` → **queued, never
delivered** (invariant 25). The transient `pane:resize` TypeError seen on the first run is gone after the
guard fix (re-run clean).

## 4. Independent review

- **spec-auditor:** CLEAN — no MAJOR/MINOR invariant violations. Confirmed inv 1 (forwards, never
  self-authorizes), inv 25 (protected queued, not delivered), inv 26 (no PCM retained), I-V2/D-VOICE-02
  (`tts:false`, no synthesis affordance), inv 3 (mock always visible; no fabricated delivery), §2.4/§10.4
  (mock-first, no live `claude`/`codex` call). One non-blocking docstring-precision note (self-check
  step-4 wording) — **addressed** (the write targets a fresh admitted PTY standing in for the operator-run
  live conductor session; the production conductor pane is separately asserted write-OWED-to-16F).
- **gate-validator:** **PASS_WITH_RESERVATIONS**. Re-ran both JS suites (158/170) and the in-Electron
  self-check itself (ok:true, 13/13). **Load-bearing falsification confirmed** (not a rubber stamp):
  moving `tools/live/emit_conductor_voice.py` aside made the self-check FAIL (`sourced:false`,
  every capture degraded to CLARIFY "voice unavailable"); the file was **restored byte-identical**
  (SHA-256 `003cdc18…acff03` before and after; `git status` clean). Reservations: (1) the `pane:resize`
  TypeError — **fixed** this sub-step; (2) the receipt was untracked — **committed** as the `.wire`
  evidence artifact; (3) `.real` correctly deferred (engine `mock:true`, `real_available:false`,
  `detection.nemo:false`) — the gate stays open until `.real`.

## 5. Substitutions & honesty (directive §6 / §10.4)

- **Bounded `py -3.12` read-source, not the WS-IPC channel** — identical §6 substitution to the
  16B/16C/16D feeds (swapping the shell's `EchoControlSurface` gateway would displace the supervisor
  liveness path, a first-launch regression class D-P16-0 warns against). Recorded.
- **Mock-first (§2.4/§10.4):** the shell voice path spawns no `claude`/`codex`; the feed runs the bridge
  over the mock STT + a local broker. **No live model call.**
- **OWED to 16F:** real microphone PCM capture and the **admitted live interactive conductor ConPTY
  session** are operator-run. A CHAT routed with no admitted conductor session is reported OWED
  (`delivered_to_conductor:false`, note "OWED to 16F"), never fabricated as delivered. The `.wire` WRITE
  path itself is proven against a real admitted supervised PTY.
- **No TTS (I-V2/D-VOICE-02):** carried `tts:false`; no synthesis method or affordance exists.
- **`.real` OWED:** real WSL-Parakeet detection + transcription route (operator NeMo stack verified
  end-to-end on host per LOOP_STATE) is the next sub-step; until then the mock is visibly indicated.

## 6. Files

New: `apps/desktop/voice/deliver.js`, `apps/desktop/test/voice-deliver.test.js`,
`apps/desktop/selfcheck/voice-selfcheck.js`, `docs/OPERATOR_NEMO_INSTALL.md`,
`docs/evidence/receipts/PHASE16E_VOICE_SELFCHECK.json`, this report.
Edited: `apps/desktop/main.js`, `apps/desktop/preload.js`, `apps/desktop/renderer/renderer.js`,
`apps/desktop/renderer/index.html`, `apps/desktop/selfcheck/run.js`.

**U67 status:** READ half closed (`.engine`); WRITE half (shell wiring + conductor-input delivery)
closed (`.wire`). Fully closes when `.real` activates real WSL-Parakeet detection and 16F proves the
live mic + interactive conductor session.
