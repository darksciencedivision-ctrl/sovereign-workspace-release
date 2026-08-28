# PHASE 15E `.voice` — EVIDENCE REPORT

**Work unit:** `phase-15e.voice` (sub-step 5 of the Phase 15E decomposition:
`.picker` → `.spawn` → `.conductor-pane` → `.objective` → **`.voice`** → `.recovery` → `.gate`)
**Date:** 2026-07-24 · **Iteration:** 55 · **Status:** PASS (sub-step)
**Tag:** none. `gate/phase-15e` is a HIGH-STAKES phase gate and closes only at `.gate`, when all
seven sub-steps have landed and the mandatory independent gate-validator confirms the phase.
**Governing directive:** `AUTONOMOUS_BUILD_DIRECTIVE.md` **§13 item 5 (OP-8 — voice INPUT to the
conductor: the operator speaks; transcribed text enters the conductor's input on the same command
path as typing; propose→approve for destructive/protected actions per I-V3; ordinary chat flows
directly)**, §11 track 15E, loop protocol §3, substitution rules §6, honesty §10.4. Load-bearing
canonical invariants: **24** (voice is STT-only), **25** (voice cannot expand authority — propose,
never execute), **1** (operator holds final authority — the app never self-authorizes), **26**
(transcribe-then-discard by default), **I-V2/D-VOICE-02** (the system does not talk back — **no
TTS**), **§2.4/§10.4** (mock-first; no live call in this unit).

---

## 1. What this sub-step delivers

OP-8 §13.5: *"the operator can speak to the conductor; transcribed text enters the conductor's input
on the same command path as typing (propose→approve for destructive/protected actions per I-V3;
ordinary chat flows directly)."* This is DISTINCT from the Phase-12 voice surface (voice as a
shell-control command bus): here voice is a second INPUT surface over the **conductor conversation**.
This sub-step is that router. It **composes** the machinery already built and **re-implements none of
it** (Directive §4 — a thin deterministic coordinator).

- **`voice_bridge/conductor_voice.py` (NEW)** — `ConductorVoiceBridge`, the router:
  - transcription + **transcribe-then-discard** + bounded diagnostic retention are the **unchanged
    Phase-12 `VoiceAdapter`** (STT-only); the bridge uses only its `transcribe()`.
  - deterministic routing (never model output; fail-closed): **(1)** a VOICE transcript with
    low/absent STT confidence, or blank text on either surface → **CLARIFY** (never delivered into
    the conversation, never proposed — I-V3); **(2)** a leading verb ∈ `PROTECTED ∪ DESTRUCTIVE`
    (imported from the broker — one source of truth) → **PROPOSED_ACTION**: submitted to the real
    `CommandBroker`, which QUEUES it for operator approval (**never auto-executes — invariant 25**)
    and is mirrored into the ONE operator approval drawer; NOT delivered as chat; **(3)** anything
    else → **ordinary CHAT** delivered verbatim to an injected **submit-only** conductor chat sink
    (the "same command path as typing").
  - **typed/voice equivalence:** `speak()` (voice) and `type_message()` (typed) share ONE `_route`,
    so the same text routes identically and a delivered `ConductorChatMessage` carries the same
    `semantic_key` regardless of surface (only the `source` tag differs).
  - **no speech-OUT** (I-V2/D-VOICE-02): the bridge has no `synthesize`/`speak`/`say`/`tts` method by
    construction; `get_usage()` carries `tts: False` through from the adapter.
- **`voice_bridge/spoken_verbs.py` (NEW)** — shared spoken-verb normalization
  (`split_spoken_command` + `VOICE_VERB_SYNONYMS`) extracted so the Phase-12 `VoiceAdapter` AND the
  new bridge normalize identically (a spoken synonym — `stop`→terminate, `make`→spawn — escalates the
  same on both, **no drift**). `adapters/voice_parakeet/adapter.py` refactored to import it; its
  private `_VERB_SYNONYMS`/`re` copy removed (behavior-preserving).
- **`terminal/compositor/voice-indicator.js` (NEW)** — the pure render model for the conductor
  push-to-talk mic + last-utterance badge. `speechOut:false` always; NO speaker/TTS affordance;
  fail-closed to a CLARIFY badge (never a fabricated "delivered") on malformed input; an unknown
  `source` is dropped to `null`, never trusted.
- **Shell wiring (operator-run surface, directive §6)** — `apps/desktop/main.js` `voice:state`
  (reads the mic affordance with the same pure core) + `voice:propose` (RECORDS a push-to-talk
  request, **self-authorizes nothing, drives no session, delivers no text** — exactly as
  `conductor:succeed` / `approvals:decide` record without acting); `preload.js` bridges
  `voiceState()` / `proposeVoice()` (no speech-out intent); `renderer.js` + `index.html` draw a
  **🎤 talk** button on the **conductor pane chrome ONLY** (CSS `.cptt` hidden unless
  `.pane.conductor`) — no speaker button anywhere.

### Scope discipline (kept honest, NOT faked)
This sub-step delivers the voice-IN router and its governance. The live STT engine (mock unless the
GPU+WSL+NeMo stack is present — real Parakeet is track 14D, unmet on this host) and the interactive
conductor ConPTY write are operator-run surfaces, recorded (**U67**), not claimed. Voice-OUT (TTS)
is FLAGGED as OWED-BY-OPERATOR-DECISION (OP-8 §13.6, reversing I-V2/D-VOICE-02) and is **not built**.
Restart recovery of the conductor-first layout is the next sub-step (`.recovery`).

---

## 2. Substitution (directive §6) — what is proven headlessly vs operator-run

- **Proven headlessly (governance-bearing):** the full deterministic router (chat-vs-propose-vs-
  clarify), invariant-25 gating through a real `CommandBroker` to the ONE drawer + operator-approval
  round-trip to a real control event, typed/voice equivalence, transcribe-then-discard + no-TTS, and
  the JS mic/badge render model — all pure/deterministic, no live STT, no `claude` process
  (§2.4/§10.4).
- **Operator-run metric (like every GUI in this build):** the rendered mic control + last-utterance
  badge, the live STT capture, and the write of chat text into the interactive conductor ConPTY. The
  shell currently RECORDS a PTT request (no fabricated transcript, no delivered text); wiring the live
  STT → bridge → conductor-write path is owed with the live conductor path (**U67**), exactly as the
  approval-queue feed (U66) and the conductor selection literals (U65) are.

**No live model call was made in this work unit.**

---

## 3. Self-check — every exit criterion with real command output

| Exit criterion (OP-8 §13.5) | Evidence (`tests/integration/test_conductor_voice.py` unless noted) |
|---|---|
| Ordinary chat flows **directly** to the conductor input | `test_ordinary_speech_flows_directly_to_the_conductor` (delivered verbatim); `test_conversational_command_word_is_not_a_shell_control_command` (a safe verb no longer hijacks conductor speech) |
| Destructive/protected **propose→approve, never execute** (inv 25) | `test_destructive_speech_proposes_and_queues_never_executes`, `test_voice_cannot_instantiate_a_node_via_the_conductor`, `test_voice_cannot_expand_permissions_via_the_conductor`, `test_spoken_synonym_escalates_to_the_destructive_queue` (all APPROVAL_QUEUED, no control_event, not delivered) |
| Proposed action surfaces in the ONE operator drawer, routes back | `test_destructive_speech…` (drawer item `PROTECTED_ACTION`, `ref == pending_id`); `test_operator_approval_of_a_spoken_action_executes_through_the_broker` (operator approve → real broker control event) |
| **Only the operator** may approve (inv 1) | `test_non_operator_cannot_approve_a_spoken_action` (worker refused; still queued, nothing executed) |
| Low/absent confidence → **clarify**, never conversation/execution | `test_low_confidence_clarifies_and_does_not_enter_the_conversation`, `test_absent_confidence_fails_closed_to_clarify`, `test_empty_transcript_fails_closed_to_clarify` |
| **Typed/voice equivalence** (same command path as typing) | `test_typed_and_voice_chat_are_equivalent` (identical `semantic_key`), `test_typed_and_voice_destructive_route_identically` (both PROPOSED_ACTION), `test_typed_chat_delivers_verbatim` |
| Transcribe-then-discard by default (inv 26) | `test_transcribe_then_discard_by_default` (`retained_now==0`, `diagnostic_retention False`) |
| **NO TTS** (I-V2/D-VOICE-02) | `test_bridge_has_no_speech_out_capability` (no synth/speak/say/tts method); JS `voice-indicator.test.js` "the control object exposes no speaker/tts affordance" + `speechOut:false` |
| Least privilege: transducer/sink cannot approve/execute (inv 25) | `test_chat_sink_is_submit_only`; the adapter holds `broker.as_proposer()` (a `SubmitOnly`) |

**Test totals (real output):**
- Python: `py -3.12 -m pytest tests/ -q` → **1011 passed** (0 skipped; +17 over the 994
  `.objective` baseline). New: `tests/integration/test_conductor_voice.py` (17).
- JS: `node --test "terminal/test/*.test.js"` → **144 passed** (+12 over 132; new file
  `terminal/test/voice-indicator.test.js` = 12). `node --test "apps/desktop/test/*.test.js"` → **35
  passed** (unchanged).
- Shell files (`main.js`, `preload.js`, `renderer/renderer.js`, `voice-indicator.js`) pass
  `node --check`.
- Phase-12 no regression: `tests/integration/test_voice_input.py` green (the `spoken_verbs`
  extraction is behavior-preserving).

**Mutation-intent check (invariant 25):** the protected/destructive gate is load-bearing — see the
gate-validator's load-bearing probe in §5 (disabling `GATED_VERBS` makes exactly 7 tests fail; a
spoken `terminate node-B` would then reach the conductor as chat).

---

## 4. Invariant / prohibition check

- **Inv 24 / I-V2 / D-VOICE-02 (STT-only, no TTS)** — the bridge exposes no synthesis method by
  construction; the JS control offers no speaker affordance (`speechOut:false`); the shell exposes no
  speech-out intent. Voice-OUT stays OWED-BY-OPERATOR-DECISION (OP-8 §13.6), not built, not faked. ✔
- **Inv 25 (voice cannot expand authority — propose, never execute)** — a spoken protected/
  destructive verb routes through the `CommandBroker` queue (operator approval required), never
  auto-executes or instantiates; even *safe* verbs never reach the broker's EXECUTED path via this
  bridge (they become chat) — the only execution path is operator approval via
  `apply_protected_decision`. The transducer and the chat sink are submit-only. ✔
- **Inv 1 (operator holds final authority; app never self-authorizes)** — the bridge/shell never
  approve/execute; `voice:propose` only RECORDS; approval still requires an operator `Identity`
  (re-checked in `CommandBroker.approve` AND `ApprovalQueue.resolve`). ✔
- **Inv 26 (transcribe-then-discard)** — reused unchanged from `VoiceAdapter`, not weakened. ✔
- **§2.4/§10.4 / §6** — mock-first: no `claude`/live call; no `subprocess`/`socket`/`urllib` in the
  new Python; the mic render + live STT + conductor write are operator-run, recorded (U67), never
  overclaimed. ✔
- **Directive §4** — the module composes the existing `CommandBroker` + `VoiceAdapter` + the
  operator-surface mirror; re-implements no classifier, no lifecycle, no authority (the one shared
  extraction, `spoken_verbs`, is behavior-preserving). ✔
- Frozen canonical set untouched: all four pinned canonical hashes verified intact
  (`6D3FD03B`, `8C9B7240`, `668089B5`, `CC414372`); `docs/canonical/` untouched;
  `config/live_operation.json` remains gitignored/untracked. `gate/phase-15e` tag ABSENT.

## 5. Reviews (fresh this iteration, foreground per D-LOOP-2 PRINT-MODE FACT)

- **spec-auditor (substantive new code): CLEAN** — no invariant violation, no prohibited drift.
  Traced the highest-risk invariants to source: **inv 24/I-V2** (no synthesis method; `speechOut:false`;
  no speaker affordance; `tts:False` preserved), **inv 25** (gated verbs route to the broker queue and
  are never delivered as chat / never executed; submit-only sink + `SubmitOnly` proposer; even safe
  verbs cannot emit a control event via this bridge — the only execution path is operator approval),
  **inv 1** (shell records only; approval operator-only in two places), **inv 26** (transcribe-then-
  discard reused, not weakened), and confirmed the `spoken_verbs` extraction is behavior-preserving,
  `GATED_VERBS` is imported from the broker (single source of truth, cannot drift), the routing is
  deterministic, no authz added to `mcp_server/`, no float, no credential handling, and the shell
  comments claim only what the code does. Two NITs, both non-blocking and requiring no action (the
  bridge's local `_log` records `kind/source/reason` only — fully covered by the broker's own
  append-only log; and the openly-disclosed over-gating of a conversational sentence whose first word
  is a destructive verb — the safe/fail-closed direction). Correctly-tracked owed item: **U67**.
- **gate-validator (sub-step, isolated): OVERALL PASS.** Independently reproduced every count in its
  own context (`1011 passed` Python in 200.25s / `144` terminal JS / `35` apps/desktop; `node --check`
  clean on all four shell files). **Load-bearing mutation probe (invariant 25):** recorded the
  baseline SHA-256 of `conductor_voice.py`, disabled the gate (`GATED_VERBS = frozenset()`), and saw
  exactly **7 tests fail** — with the gate off, `"terminate node-B"` routed to `CHAT` and was
  DELIVERED to the sink (a spoken kill would have reached the conductor) — then restored the file
  **byte-identical (SHA-256 re-verified)** and re-ran to green, leaving no probe artifacts. Confirmed
  typed/voice equivalence is real (`speak`/`type_message` share `_route`), NO TTS (grep of new
  Python+JS; bridge exposes no synthesis method; `speechOut:false`), the Phase-12 refactor did not
  regress (`test_voice_input.py` green), the mic button is conductor-pane-only with no speaker button,
  the shell handlers RECORD only, the four frozen canonical hashes unchanged, `docs/canonical/`
  untouched, `config/live_operation.json` untracked, `gate/phase-15e` ABSENT, and mock-first (no
  `subprocess/socket/urllib` in the new Python). One disclosed, **non-blocking** observation (the
  over-gating trade-off — the safe direction, consistent with invariant 25). No reservations.

## 6. Owed / deferred (honest limits)

- **U67 (new):** the shell RECORDS a push-to-talk request; capturing operator audio, running the live
  STT engine, routing the transcript through `ConductorVoiceBridge`, and writing chat text into the
  interactive conductor ConPTY are owed with the live conductor path (a later 15E wiring), like the
  approval-queue feed (U66) and the conductor selection literals (U65).
- **Voice-OUT (TTS)** is FLAGGED OWED-BY-OPERATOR-DECISION (OP-8 §13.6, reversing I-V2/D-VOICE-02) —
  not built, not faked. It becomes a 16th track only on an explicit operator OP-9-style reversal.
- **Real Parakeet/NeMo** (track 14D) is unmet on this host (no GPU+WSL+NeMo) — the engine is the mock
  STT behind the same interface (I-A1); U1/U2 stay open-for-hardware.
- U58 (live flow workers), U63/U64, U65, U66, NIT-3 carried into 15E remain open.
- The shell mic/badge is an operator-run surface: its DATA shape is headlessly tested
  (`terminal/test/voice-indicator.test.js`), the painting is operator-verified.

**Work commit:** `8bcbfa1` · **Evidence/register commit:** this commit.
