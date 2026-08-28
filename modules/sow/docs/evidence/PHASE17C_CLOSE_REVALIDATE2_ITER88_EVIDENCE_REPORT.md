# Phase 17C `.close-revalidate2` — Iteration 88 failed-gate evidence

Date: 2026-07-28  
Verdict: **FAIL — no tag**

## Scope and provenance

Tags and `docs/loop/LOOP_STATE.json` agreed at entry: `gate/phase-17b` was the latest
Phase-17 gate, `gate/phase-17c` was absent, and the current step was
`phase-17c.close-revalidate2`. No reconciliation commit was required. The pre-existing
untracked `apps/desktop/package-lock.json` was excluded throughout.

This one work unit produced four test-first product commits:

- `b395a3f` — supervisor-process authority for exact direct-voice turns;
- `c687380` — vendor `Stop`/`StopFailure`/`SessionEnd` made observation-only after an
  independent reviewer reproduced a child-bearer deny-then-forged-lifecycle-then-allow bypass;
- `cf96229` — kill intent separated from node-pty-confirmed process exit for conductor
  authority and lease release;
- `268dae6` — owned fresh-audio quit purge, kill-before-release teardown ordering,
  main-process physical-input recovery, and quota-path protected-action measurements.

Frozen canonical documents and schemas were not changed.

## Test-first and self-check output

The new tests failed before implementation: the authority module, conductor lifecycle
module, operator-resume module, `purgeOwned()`, and `processExited` event facts were absent.
After implementation:

- `node --test apps/desktop/test/*.test.js` — **462 pass, 0 fail** in the builder's
  foreground run;
- `node --test terminal/test/*.test.js` — **197 pass, 0 fail**;
- `py -3.12 -m pytest tests -q` — **1418 pass**, 61 warnings (run before the final
  JS-only teardown fixes; Python product code did not change afterward);
- focused Python Phase-17C tests — **67 pass**;
- manifest freeze check — **OK**;
- `git diff --check` — clean; canonical/schema diffs — empty.

The final independent validator separately reported desktop **437 pass / 25 skip / 0
fail**, terminal **197 pass**, and Python voice **122 pass**. The spec auditor separately
reported the same desktop/terminal totals and **49/49** changed-test checks.

## Exact packaged receipt

Foreground command: `cd apps/desktop; node selfcheck/run.js voice-conductor`

Receipt:
`docs/evidence/receipts/PHASE17C_CLOSE_SELFCHECK.json`

- source commit: `268dae63a4cbdd1659bbc09434479361eb3de597`;
- SHA-256:
  `A7CD59264D5113AA50C2D54996DCFB0754DDCAB19BB3B30CD861CD6C3ACE916D`;
- product tree clean, with only the pre-existing package lock explicitly excluded;
- **39/41 checks passed; `ok:false`**;
- real PCM fixture -> real WSL Parakeet (`mock:false`) -> real bridge -> governed live
  Claude conductor pane;
- exact voice turn armed in the Electron supervisor service; vendor lifecycle did not
  disarm it;
- protected `terminate` utterance was proposed/queued and delivered no bytes to the pane;
- no TTS; capture absent afterward; conductor process killed; durable I-X3 count returned
  to zero; no self-check process or scratch lease survived.

The two failed checks were:

1. `live_conductor_answered`;
2. `voice_tool_call_denied_before_execution`.

The live pane visibly reported: Claude Max weekly limit reached, resetting
2026-07-30 12:00 America/Chicago. Therefore the model produced neither an answer nor a
tool attempt to deny. This is failed gate evidence, not a directive section 8 blocker.

Substitution: automated evidence injected an OS-synthesized WAV at the point the physical
microphone supplies PCM. The product path below that point was unmodified. A human speaking
into the microphone remains operator first use, as allowed by Phase 17C; no substituted
result is presented as that physical act.

## Mandatory independent reviews

Both required reviews ran synchronously in isolated, read-only Codex subprocesses and
completed before this unit ended.

### Gate validator — **FAIL**

The final validator confirmed the receipt/hash and all passing authority, transport,
protected-routing, Parakeet, no-TTS, and cleanup legs. It withheld the tag for the two
quota-dependent failed checks and reproduced these additional defects:

1. **CRITICAL:** a delayed `onExit` from a killed PTY can address a replacement session
   that reused the pane ID, mark it exited, delete its live handle, and cause release of
   the replacement authority/lease;
2. **HIGH:** worker leases release on `kill` intent before process exit;
3. **HIGH:** two shell instances can choose the same millisecond/sequence capture name,
   overwrite one another, and make `purgeOwned()` delete the other instance's capture;
4. **MEDIUM:** physical-input authority recovery depends on renderer-controlled pane focus
   and is not exercised by the packaged receipt.

Decision: `gate/phase-17c` **must not be tagged**.

### Spec auditor — **FINDINGS**

The auditor independently reproduced the stale-exit and capture-name races and confirmed
the worker and focus findings. It additionally found:

- the quit-time conductor branch retains a now-unimported
  `releaseConductorLeaseSessionSync` call behind a swallowing `try/catch`;
- receipt prose says arm/deny/disarm were measured although denial is false, and the
  process-exit release check correlates only a reset reason string rather than an
  independently identified exit generation.

It found no TTS, consensus forcing, extra approval layer, MCP-authority drift, naked spawn,
worker self-canonization, or pricing drift.

## Exit-criterion disposition and next action

Phase 17C remains **failed**. No gate tag or Phase 17D work is authorized. The next
iteration must begin by adding PTY session-generation identity and regression coverage,
holding worker leases until matching confirmed exit, making capture creation
cross-instance unique and exclusive, replacing renderer-focus recovery with an explicitly
main-process-authenticated operator action, removing the dead quit call, and making the
receipt correlate exact exit identity/order without overclaim. Then it must regenerate one
exact-source packaged receipt after provider availability returns and rerun both mandatory
reviews in the foreground.

