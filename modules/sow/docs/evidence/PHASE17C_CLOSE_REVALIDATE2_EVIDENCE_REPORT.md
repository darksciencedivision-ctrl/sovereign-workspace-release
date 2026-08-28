# Phase 17C `.close-revalidate2` Evidence Report — CHECKPOINT / GATE FAIL

**Date:** 2026-07-27
**Work commits:** `98800f9b54ee2149df980f7beb2030addc7195d3`,
`98525f3` (mandatory-review safe-direction response)
**Gate verdict:** **FAIL — no `gate/phase-17c` tag**
**Loop disposition:** RUNNING; retry remains `phase-17c.close-revalidate2`

## Objective and source state

The unit began from `phase-17c.close-revalidate2`, iteration 86. Git tags and loop state agreed:
`gate/phase-17b` was the latest Phase 17 tag and `gate/phase-17c` did not exist, so no
state-to-tag reconciliation commit was required.

The objective was the exact continuation recorded by iteration 86: land the existing test-first
delivery checkpoint, replace vendor-mode chrome as authority with a supervisor-owned non-executing
voice-turn boundary while preserving ordinary direct chat, generate a current packaged receipt, run
both mandatory reviews in the foreground, and tag only on PASS.

## Implemented work

`98800f9`:

- extracted the complete conductor body/echo/submit decision into headless, mutation-sensitive tests;
- made the ConPTY echo window monotonic and exact-or-refuse, including ring-buffer eviction;
- refused unknown/modal/permission chrome before writing the body and made partial writes residue-safe;
- scanned the whole normalized utterance for protected/destructive verbs and common inflections;
- pinned a per-launch Claude hook profile by path, runtime, settings, and SHA-256;
- marked direct voice turns and added arm/deny/disarm hook audit events;
- carried boundary observations through the packaged receipt;
- preserved real-engine capture, transcribe-then-discard, the broker path, and no TTS.

The mandatory spec audit then established that a hash-pinned policy executed by the vendor hook
dispatcher is still not supervisor-process enforcement. It also found that an unmarked
`UserPromptSubmit` can clear session-scoped arm state before an earlier voice turn necessarily ends,
that a lost state file is fail-open, and that `StopFailure`/user interruption are not represented by
the original Stop/SessionEnd pair.

`98525f3` is the safe-direction response:

- tickets now state `enforced_by_supervisor_process:false`;
- shell validation rejects a hook policy that claims the value is true;
- production direct voice delivery requires true and therefore refuses before writing any body;
- the packaged self-check also requires true, so this disabled path cannot manufacture a green receipt.

This does not satisfy the positive Phase 17C ordinary-chat criterion. It does ensure that an ungated
checkpoint does not expand voice authority while the criterion remains open. Ordinary physical typed
chat is unchanged.

## Test-first evidence and real command output

The original implementation began with failing module/import/authority tests, then passed focused
delivery, pane-state, launch-profile, ring-buffer, bridge, and mic suites. The review response added
three new assertions first; the foreground red run failed exactly on:

- hook-only delivery was still written;
- a ticket could claim supervisor-process enforcement;
- the emitted ticket omitted the honest enforcement field.

After `98525f3`, the same checks passed.

| Foreground command | Result |
|---|---|
| `npm test` from `apps/desktop` on final checkpoint | **444 passed, 0 failed, 0 skipped** |
| `node --test terminal/test/*.test.js` | **196 passed, 0 failed** |
| `py -3.12 -m pytest tests -q` | **1418 passed**, 61 deprecation warnings, 281.82 s |
| Focused final JS authority/delivery suite | **77 passed, 0 failed** |
| Focused final Python launch/voice suite | **67 passed, 0 failed** |
| `py -3.12 tools/manifest/compute_manifest.py --check` | `freeze check OK: no drift in FROZEN set` |
| `git diff --name-only -- docs/canonical schemas` | empty |
| `git diff --check` | clean |
| `git remote -v` | empty |

One initial full-Python run used a repo-contained `TEMP`. That changed a containment test's premise:
its deliberately non-repository directory became a child of this repository, so Git correctly found
the parent repository and 1 of 1418 tests failed. Re-running that test and the full suite with the
normal OS temporary directory produced 1/1 and 1418/1418. The failed harness override is not counted
as product evidence.

## Packaged live receipt

`node selfcheck/run.js voice-conductor` was run twice in the foreground.

1. The first run failed closed before delivery because Claude Code 2.1.220 emitted an observed
   `manual mode ... ● high · /effort` footer suffix that the bounded pane grammar did not yet know.
   The exact suffix was added with a test proving it is accepted only behind a qualifying boundary.
2. The second run exercised the real production path through the point the provider could process:
   real 16 kHz PCM fixture, WSL `parakeet-wsl` (`mock:false`), transcript
   `Use a tool to calculate 45 plus 46. Answer with only the sum and nothing else.`, bridge CHAT,
   body and submit delivered into the live governed conductor, and `voice_turn_armed` observed before
   model processing. Claude then rendered `You've hit your weekly limit · resets Jul 30, 12pm
   (America/Chicago)` and never attempted a tool or produced an answer.

The checked-in receipt
`docs/evidence/receipts/PHASE17C_CLOSE_SELFCHECK.json` is therefore **failed evidence**, SHA-256
`B4DAC2DB2153A1D60E744A2EDFABD70A22B6273DB363E4EF2389216DD8820074`:

- `ok:false`;
- `real_engine_transcribed:true`, `audio_discarded_after:true`;
- body `written:true`, submit `submitted:true`, `voice_turn_armed_before_model:true`;
- `live_conductor_answered:false`;
- `voice_tool_call_denied_before_execution:false`;
- `voice_turn_disarmed_after_reply:false`;
- `session_killed:true`, `lease_released:true`, `in_use_after_release:0`;
- `capture_files_after:[]`.

The receipt was generated before the work commits and does not carry a source-tree identity. It
cannot validate either `98800f9` or the final safe-direction `98525f3`; it is retained because it is
the honest machine record of the failed foreground attempt. No faithful headless substitution can
prove the missing live reply, dispatcher denial, and disarm sequence.

## Independent mandatory reviews

### Gate-validator — FAIL

The isolated validator ran 442 desktop tests, 196 terminal tests, 67 focused Python tests, the freeze
check, Git integrity/diff checks, and inspected the live receipt. It withheld the gate because the
receipt did not show a live reply, tool denial, or disarm. It also ruled that an automatically
resetting temporary quota is not a directive section 8 terminal blocker: no credential, purchase, or
hardware action is required. Its focused addendum on `98525f3` confirmed that production now refuses
hook-only authority before writing, but the positive Phase 17C criterion remains unmet.

### Spec-auditor — CHANGES_REQUIRED, then narrow safe-direction APPROVED

The isolated spec audit ran 442 desktop tests, 196 terminal tests, and 67 focused Python tests. It
found the vendor-dispatch authority and overlapping-turn/state-loss problems described above,
confirmed the failed receipt is not exact-commit evidence, and carried physical typed-input
equivalence as U149. It found no TTS, discard, canonical, schema, approval-layer, opaque-agent, or
consensus drift. Its focused review of `98525f3` returned **APPROVED for the narrow safe-direction
commit**: real tickets can no longer authorize direct voice CHAT, and no new safety blocker was
introduced. Overall Phase 17C remains unclosable.

## Exit-criterion disposition

| Phase 17C criterion | Disposition |
|---|---|
| Probe ≥60 s, non-blocking/re-probe, overrides | PASS from the gated `.probe` work and current suites |
| Real PCM → WSL Parakeet → bridge | PASS in the failed receipt up to the provider boundary |
| Same live 17A conductor answers | **FAIL** — provider weekly quota rendered instead of an answer |
| Propose-never-execute | Broker negatives PASS; direct CHAT is safely disabled because supervisor-process containment is absent |
| Ordinary direct voice CHAT preserved | **FAIL** — deliberately refused on the final safe checkpoint |
| Transcribe then discard | PASS; filesystem reports no capture residue |
| No TTS | PASS |
| Fixture receipt | Present but `ok:false` and not exact-commit evidence |
| Human physical microphone | Operator first use, as directive section 16 permits |
| Confidence calibration | Limitation remains honestly recorded (U140) |
| Mandatory confirmation | **FAIL / do not tag** |

## Deviations, limitations, and remaining work

- Two product commits precede the evidence commit because mandatory review found a safety defect in
  the first work commit; the second is the smallest fail-closed response and both hashes are recorded.
- No purchase, upgrade, alternate credential, second provider, or extra live exchange was attempted.
- Hook-policy code and tests remain as a non-authorizing checkpoint, but current product delivery
  cannot use it as authority.
- U149 (assembled physical typed/broker equivalence), U140 (confidence calibration), U25 (OS process
  containment), and the new hook-dispatch authority finding remain open.
- The next unit must first design a boundary enforced by the supervisor process (or obtain a canonical
  ruling that explicitly permits a narrower trusted mechanism), then run one minimal packaged receipt
  after provider availability returns, record exact source identity, and rerun both mandatory reviews.

## Gate and next action

**No tag. Status remains RUNNING.** The exact next step remains
`phase-17c.close-revalidate2`. After the recorded provider reset, the smallest runtime action is one
minimal packaged receipt; however, code must not re-enable direct voice CHAT until supervisor-process
enforcement is real and independently confirmed.
