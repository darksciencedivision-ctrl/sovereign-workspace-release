# PHASE 16E `.engine` — EVIDENCE REPORT

**Work unit:** `phase-16e.engine` (sub-step 1 of the Phase 16E decomposition: **`.engine`** → `.wire`)
**Date:** 2026-07-25 · **Iteration:** 66 · **Status:** PASS (sub-step)
**Tag:** none. `gate/phase-16e` closes only at `.wire`, when the shell talk button is wired to deliver a
CHAT transcript into the conductor input, the in-Electron D-P16-0 self-check receipt lands, and
`docs/OPERATOR_NEMO_INSTALL.md` is written. (16E is NOT a directive-flagged high-stakes gate — only
16A/16F are — but independent gate-validator confirmation is obtained on the closing sub-step.)
**Governing directive:** `AUTONOMOUS_BUILD_DIRECTIVE.md` **§15 track 16E** (*Talk button → capture → STT
→ bridge → conductor input, end-to-end (closes U67): real Parakeet if NeMo present, else mock STT with a
VISIBLE "mock engine" indicator; TTS still NOT built*), **§13 item 5 (OP-8 — voice INPUT to the
conductor)**, loop protocol §3, substitution rules §6, honesty §10.4. Load-bearing canonical invariants:
**24** (voice is STT-only), **25** (voice cannot expand authority — propose, never execute), **1**
(operator holds final authority — the app never self-authorizes), **26** (transcribe-then-discard by
default), **I-V2/D-VOICE-02** (the system does not talk back — **no TTS**), **§2.4/§10.4** (mock-first;
no live call in this unit).

---

## 1. Decomposition (directive §3.2 — one named sub-step per iteration for a large phase)

Track 16E is decomposed exactly as 16D/15E/14A were (a whole-track gate tag + gate-validator close only
when ALL sub-steps land; no per-sub-step tag):

- **`.engine` (this unit)** — the honest, engine-SELECTED read half of U67: pick the STT engine (real
  Parakeet only when the host stack is present AND a real adapter exists — track 14D; else the mock
  behind the same `STTEngine` contract, ALWAYS surfaced as a VISIBLE mock engine), route ONE captured
  utterance through the REAL `ConductorVoiceBridge` over a REAL `CommandBroker` (mock-first, no live
  call), and fold the outcome into `conductor_voice_feed@1.0` — the bounded `py -3.12` read-source the
  16B/16C/16D feeds use. No shell/UI (`main.js`/`renderer`/`preload`) change this unit, so no
  in-Electron self-check is due yet (D-P16-0 governs shell/UI changes to the running app).
- **`.wire` (next unit)** — wire the existing 🎤 talk button (`voice:propose`) to source this feed and,
  on a CHAT outcome, deliver the transcript into the conductor session via the same `pane:input` /
  `SessionManager.write` path typed input uses; the in-Electron D-P16-0 self-check receipt
  (`PHASE16E_VOICE_SELFCHECK.json`); `docs/OPERATOR_NEMO_INSTALL.md`; then `gate/phase-16e` with the
  mandatory independent gate-validator.

## 2. What this sub-step delivers

The routing AUTHORITY already exists (Phase-15E `ConductorVoiceBridge`, 17 tests). `.engine` adds the
engine honesty + the shell-renderable feed, composing the existing machinery (Directive §4 — a thin
deterministic coordinator, no re-implemented classifier/lifecycle/authority):

- **`control_plane/orchestration/conductor_voice_feed.py` (NEW)** — the read path:
  - `select_engine()` — HONEST engine choice. `detect_voice_stack()` on this host yields
    `{nvidia_gpu, wsl, nemo: false}` ⇒ `real_parakeet_available()` = **False** ⇒ the mock `STTEngine`.
    The engine is ALWAYS reported `mock:True`; if the host stack WERE present it says so and marks the
    real adapter OWED (track 14D) — it never constructs a fake "real" engine and never reports
    `mock:False` without one (the safe, fail-closed direction: the UI can never imply real speech).
  - `run_conductor_voice(audio_ref)` — routes ONE utterance through the REAL bridge over a REAL broker
    with a REAL `ApprovalQueue` mirror (so a proposed action carries a `queue_item_id`); a
    `_RecordingSink` (submit-only) stands in for the interactive conductor ConPTY write (the operator-run
    surface, owed to `.wire`/16F). Wrapped fail-closed: ANY fault ⇒ `unavailable_feed`.
  - `fold_conductor_voice_feed()` — PURE fold into `conductor_voice_feed@1.0`; `delivered_text` is only
    ever the text a CHAT outcome actually routed; `tts:False` carried through; `transcribe_then_discard`
    from `retained_now==0`.
- **`tools/live/emit_conductor_voice.py` (NEW)** — `--emit-conductor-voice [--audio-ref <ref>]` prints
  ONLY the feed JSON (one line), mock-first, fail-closed. The stable shell contract.
- **`terminal/compositor/voice-indicator.js` (extended)** — NEW `voiceEngineIndicator(engine)` renders
  the VISIBLE mock/real indicator: REAL only when `mock:false ∧ real_available:true`; anything else
  (absent, malformed, or a `mock:false` claim without host detection) folds to `mock:true` with the
  label **"mock engine"** and an install hint pointing at `docs/OPERATOR_NEMO_INSTALL.md`. `voiceControl`
  surfaces it; `summarizeVoice` always appends `[mock engine]` on this host. Still no speaker/TTS key.
- **`apps/desktop/voice/voice-source.js` (NEW)** — the bounded `py -3.12` read-source glue
  (`sourceConductorVoiceFeed`, injectable `spawn`), fail-closed to `unavailableVoiceFeed` (a CLARIFY
  outcome + a VISIBLE mock engine, never a fabricated delivery). Headlessly tested; NOT yet imported by
  the running shell (that is `.wire`).

### Scope discipline (kept honest, NOT faked)
No shell/UI change to the running app this unit — the talk-button delivery into the conductor ConPTY and
the in-Electron self-check are `.wire`. The live STT engine stays mock (real Parakeet is track 14D,
unmet — `nemo` absent). Voice-OUT (TTS) is FLAGGED OWED-BY-OPERATOR-DECISION (OP-8 §13.6, reversing
I-V2/D-VOICE-02) and is **not built**.

## 3. Substitution (directive §6) — proven headlessly vs operator-run

- **Proven headlessly (governance-bearing):** engine selection honesty (mock, visible, never a claimed
  real engine); the full three-way routing as the shell FEED (CHAT delivered / protected+destructive
  QUEUED never delivered / low-confidence CLARIFY); the `queue_item_id` mirror; NO TTS;
  transcribe-then-discard; the JS engine indicator + fail-closed fold; the source glue (parse / timeout /
  non-zero / non-JSON / malformed all fail closed). Two LIVE JS integration tests drive the REAL emitter
  end-to-end (real bridge → real broker) — not a mock, not skipped when `py -3.12` is present.
- **Operator-run / owed to `.wire`+16F:** the rendered mic control, real mic capture, and the write of a
  CHAT transcript into the interactive conductor ConPTY (`live_capture_owed`, issue 16F). The bounded
  read-source is used instead of the WS-IPC surface for the SAME reason `.statusbar`/`.approvals` are
  (swapping the shell's `EchoControlSurface` gateway would displace the supervisor liveness path —
  first-launch regression class D-P16-0).

**No live model call was made in this work unit.**

## 4. Self-check — every exit criterion with real command output

| Exit criterion (§15 track 16E, this sub-step) | Evidence |
|---|---|
| STT engine selected HONESTLY; mock on this host, VISIBLE, never claims real | `test_select_engine_is_mock_and_visible_on_this_host`, `test_select_engine_never_claims_real_without_a_real_adapter`; JS `voiceEngineIndicator` tests (real only when `mock:false ∧ real_available:true`; a `mock:false` claim without detection still folds mock) |
| Ordinary speech → CHAT delivered (the conductor-input path) | `test_ordinary_speech_folds_to_a_delivered_chat_feed` (`delivered_text=="show status"`, recording sink saw it) |
| Destructive/protected → QUEUED, never delivered (invariant 25) | `test_destructive_speech_folds_to_a_queued_feed_never_delivered`, `test_protected_grant_folds_to_a_queued_feed` (queue_item_id set, `delivered=False`, `deliveries==[]`) |
| Low/absent confidence → CLARIFY (fail closed) | `test_low_confidence_speech_folds_to_a_clarify_feed`, `test_unknown_audio_ref_fails_closed_to_clarify` |
| VISIBLE "mock engine" indicator (never silently pretend to hear) | `test_feed_engine_is_visibly_mock`; JS `summarizeVoice` appends `[mock engine]`; fail-closed indicator |
| NO TTS (I-V2/D-VOICE-02) | `test_no_tts_and_transcribe_then_discard` (`tts:False`); no speaker/synth key in `voiceControl` |
| Transcribe-then-discard (invariant 26) | `test_no_tts_and_transcribe_then_discard` (`transcribe_then_discard`, `torn_down`) |
| Fail-closed feed never claims delivery | `test_unavailable_feed_is_honest_and_never_claims_delivery`, `test_run_conductor_voice_wraps_a_faulty_engine_fail_closed`; JS non-zero/non-JSON/malformed/timeout/launch fail closed |
| Emitter prints exactly one JSON line (shell contract) | `test_emit_prints_one_json_line_for_a_chat_utterance`, `test_emit_defaults_the_audio_ref`; LIVE JS `sourceConductorVoiceFeed` |

**Test totals (real output):**
- Python: `py -3.12 -m pytest tests/ -q` → **1086 passed** (0 skipped; 61 warnings; 217.09s). New: `tests/integration/test_conductor_voice_feed.py` (17).
- JS: `node --test "terminal/test/*.test.js"` → **170 passed** (voice-indicator 18, +8 over 10). `node --test "apps/desktop/test/*.test.js"` → **149 passed** (new `voice-source.test.js` = 14, incl. 2 LIVE).
- `node --check` clean on `voice-indicator.js` + `voice-source.js`.

## 5. Invariant / prohibition check

- **Inv 24 / I-V2 / D-VOICE-02 (STT-only, no TTS)** — `tts:False` folded from the adapter; the JS control
  exposes no speaker key; the indicator offers install of a real STT engine, never synthesis. ✔
- **Inv 25 (voice cannot expand authority)** — a protected/destructive verb routes through the real
  `CommandBroker` queue (`queue_item_id`), is NEVER folded `delivered` and the recording sink never sees
  it; only a SAFE-verb / conversational utterance is delivered as chat. ✔
- **Inv 1 (operator holds final authority)** — the feed RECORDS a routing outcome; it approves/executes
  nothing; the recording sink is submit-only. ✔
- **Inv 26 (transcribe-then-discard)** — reused unchanged from `VoiceAdapter`; `retained_now==0`. ✔
- **Inv 3 / §6 / §10.4** — mock-first: no `claude`/`codex`, no `subprocess`/`socket`/`urllib` in the new
  Python; fail-closed everywhere; the mic render + live capture + conductor write are owed (16F),
  never overclaimed. ✔
- **Directive §4** — composes the existing bridge/broker/adapter; re-implements no authority. ✔
- Frozen canonical set untouched (`6D3FD03B`, `8C9B7240`, `668089B5`, `CC414372`); `docs/canonical/`
  untouched; `config/live_operation.json` untracked. `gate/phase-16e` ABSENT. `apps/desktop/package-lock.json`
  is host-local npm noise — NOT committed.

## 6. Reviews (fresh this iteration, foreground per D-LOOP-2 PRINT-MODE FACT)

- **spec-auditor (substantive new code): CLEAN** — no invariant violations, no prohibited drift. Traced
  every named invariant to source: **I-24/I-V2** (no synthesis method/affordance; `tts:False` carried;
  no speaker key), **I-25** (only GATED_VERBS route to the broker queue; `sink.deliver` is reached ONLY
  in the CHAT branch; the fold gates `delivered`/`delivered_text` on `kind==CHAT` — a `proposed_action`
  can never fold delivered or reach the recording sink), **I-1** (records only; `mirror_broker_outcome`
  does not re-classify; broker `approve()` enforces operator role and is unreachable here), **I-26**
  (transcribe-then-discard preserved, bridge closed before the feed), **I-3/§6/§10.4** (no
  `claude`/`codex`/`subprocess`/`socket`/`urllib` in the new Python; every fault path returns the
  fail-closed feed; the engine indicator is `mock:True` unless `mock:false ∧ real_available:true` — never
  pretend-to-hear). No `mcp_server/` auth, no float-for-money, no credentials. **3 NITs, all
  non-blocking:** (1) the `select_engine` reason string hardcoded "(nemo missing)" — **FIXED this
  iteration** to name the actually-absent component from the authoritative `detection` dict; (2)
  injected non-mock engine trusted-as-real on stack presence — clarifying guard comment **ADDED** (still
  gated on `real_available`; the emitter never injects); (3) the "Delivered to conductor" label on a
  recorded (not-yet-live-written) CHAT — honest, disclosed via `live_capture_owed` on every feed, the
  real write is `.wire`. No blocking change.
- **gate-validator (sub-step, isolated): OVERALL PASS.** Independently reproduced every count in its own
  context: `17 passed` Python (0.18s), `18` voice-indicator JS, `14` voice-source JS (the **2 LIVE tests
  RAN** — 134.7ms/133.3ms — driving the real `py -3.12` emitter, not skipped). Reproduced all six exit
  criteria directly from the emitter (`audio:show-status`→chat/delivered, `audio:terminate-node-b`→
  queued/never-delivered/`queue_item_id:ap-1`/empty sink, `audio:mumble`→clarify; `engine.mock:true`,
  `tts:false`, one JSON line, exit 2 on no-flag). **Load-bearing mutation probe (invariant 25):** SHA-256
  of `voice_bridge/conductor_voice.py` recorded, `GATED_VERBS` neutralized to `frozenset()` → a
  destructive utterance then WRONGLY folded `delivered:true`/populated sink (gate is load-bearing), file
  restored via `git checkout` byte-identical (SHA re-verified), re-ran green. Confirmed `gate/phase-16e`
  ABSENT, the four frozen canonical hashes unchanged, `docs/canonical/` clean, and the `.wire` deferrals
  (`voice-source.js` not yet imported; live capture/ConPTY write owed to 16F) honestly disclosed. No
  reservations beyond the disclosed deferrals.

## 7. Owed / deferred (honest limits)

- **U67 (read half closed here; write half owed to `.wire`):** the shell wiring of the talk button to
  source this feed and deliver a CHAT transcript into the conductor ConPTY, plus the in-Electron
  self-check, are `.wire`.
- **Real Parakeet/NeMo** (track 14D) unmet on this host (`nemo` absent) — mock STT behind the same
  interface (I-A1); U1/U2/U4 stay open-for-hardware. `docs/OPERATOR_NEMO_INSTALL.md` is due at `.wire`.
- **Voice-OUT (TTS)** OWED-BY-OPERATOR-DECISION (OP-8 §13.6) — not built, not faked.

**Work commit:** `4ea5650` · **Evidence/register commit:** the following commit.
