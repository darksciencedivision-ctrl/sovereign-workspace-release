# Phase 17C `.close-revalidate2` — Iteration 90 failed-gate evidence

Date: 2026-07-28  
Verdict: **FAIL — no tag**

## Objective and source state

This work unit revalidated the Phase 17C voice path against the exact committed product
tree after iteration 89 and the subsequent process-teardown repair. At entry:

- `gate/phase-17b` was the latest Phase 17 gate and `gate/phase-17c` was absent;
- `LOOP_STATE.next_step` was `phase-17c.close-revalidate2`;
- the state and gate tags agreed, so no reconciliation commit was required;
- the pre-existing untracked `apps/desktop/package-lock.json` was preserved and excluded;
- frozen canonical documents, schemas, and `mcp_server/` were unchanged.

The work commit for this unit is `66c2bf3`. It adds a red-first regression and an attempted
repair for an Electron bootstrap PID exiting before an already-observed descendant. The
test was red with `TypeError: guard.waitForWorkspaceExit is not a function`, then green
after implementation. The independent validator later found that the repair still misses
a descendant that reparents before the first inventory; that defect is recorded below and
is not softened.

Post-iteration-89 commits already at entry were:

- `c8af621` — logging and child-process teardown hardening;
- `6b7fd4a` — evidence for that teardown repair;
- `7bb1ff6` — loop-runner backend change.

## Files changed in this unit

Work commit `66c2bf3`:

- `apps/desktop/selfcheck/process-tree.js`
- `apps/desktop/selfcheck/run.js`
- `apps/desktop/test/selfcheck-process-tree.test.js`

Gate artifacts:

- `docs/evidence/receipts/PHASE17C_CLOSE_SELFCHECK.json`
- this report
- `docs/registers/UNRESOLVED_ISSUE_REGISTER.md`

## Test-first and self-check output

Initial red command:

```text
node --test apps/desktop/test/selfcheck-process-tree.test.js
tests 4; pass 2; fail 2
TypeError: guard.waitForWorkspaceExit is not a function
```

After implementation:

```text
node --test apps/desktop/test/selfcheck-process-tree.test.js
tests 4; pass 4; fail 0
```

Fresh foreground suites:

| Command | Result |
|---|---|
| `cd apps/desktop; npm test` | **485 pass, 0 fail** |
| `node --test terminal/test/*.test.js` | **201 pass, 0 fail** |
| `py -3.12 -m pytest tests/ -q` | **1419 pass, 61 warnings** in 378.28 s |
| `py -3.12 tools/manifest/compute_manifest.py --check` | `freeze check OK: no drift in FROZEN set against recorded manifest` |
| `git diff --exit-code gate/phase-17b -- docs/canonical schemas mcp_server` | empty, exit 0 |
| `git diff --check` | empty, exit 0 |

The gate-validator independently ran:

- focused voice/process JavaScript: **214 pass**;
- Phase 12/17C Python subset: **149 pass**;
- full desktop suite: **485 pass**;
- full terminal suite: **201 pass**;
- freeze, canonical-hash, `git fsck`, scope, and diff checks: clean.

The spec-auditor independently ran the full desktop suite (**485 pass**), 25 focused
logging/session/process-tree tests, and 17 Python process-tree/backend tests.

## Exact packaged Electron receipt

Foreground command:

```text
cd apps/desktop
node selfcheck/run.js voice-conductor
```

Artifact: `docs/evidence/receipts/PHASE17C_CLOSE_SELFCHECK.json`

- source commit: `66c2bf3f456bcc06253cd4fbcc8f403f315975aa`;
- tracked product tree clean at launch: `true`;
- SHA-256:
  `4CD02AAA68DE4E4685D6106C840AEE555C22CE3DCDF2CE5567AA68783255CCDD`;
- runtime: Electron 31.7.7, Node 20.18.0, Chrome 126, Windows x64;
- result: **40/42 checks true; `ok:false`**.

Measured live path:

- 218,446 bytes / 6.825 seconds of real PCM fixture input;
- real WSL Parakeet (`mock:false`) transcribed the exact operands;
- the real bridge routed CHAT;
- the governed live Claude conductor ran in pane 1 with exact PID/generation and one
  durable I-X3 lease;
- the utterance was echo-confirmed and submitted;
- a protected utterance was queued and never delivered;
- audio was absent after transcription;
- the exact conductor process exited, the lease returned to zero, the scratch ledger was
  removed, and no product Electron/Claude process survived.

The provider displayed:

```text
You've hit your weekly limit · resets Jul 30, 12pm (America/Chicago)
```

Therefore the two failed checks were:

1. `live_conductor_answered`;
2. `voice_tool_call_denied_before_execution`.

No answer and no tool attempt occurred. A second live exchange was deliberately not spent
after the same automatic provider limit was observed.

Three stale scratch ledgers from earlier aborted/duplicate self-checks were found after the
run. Their holder PIDs were dead; the real subscription ledger was empty. Only those exact
repo-local scratch files were removed. Final reviewer-observed state was zero scratch
ledgers, zero real leases, no capture directory, no fixture file, and no Phase 17C
Electron/WSL/provider process.

## Exit criteria

| Criterion | Result |
|---|---|
| Probe budget at least 60 s | **PASS** — 90 s contract |
| Non-blocking probe and visible `probing…` | **PASS** |
| Re-probe on demand/after failure; no lifetime cache pin | **PASS** |
| `SOW_*` overrides honored | **PASS** |
| Real PCM → WSL Parakeet → bridge | **PASS** |
| Delivery into the governed live 17A conductor | **PASS through submitted input** |
| Same live conductor answers | **FAIL** — provider quota screen |
| Propose-never-execute | **PARTIAL** — protected utterance queued; live direct-chat tool denial not exercised |
| Transcribe then discard | **PASS** |
| No TTS | **PASS** |
| D-P16-0 packaged Electron receipt | **FAIL as gate proof** — exact receipt is red |
| Physical microphone | **OWED to operator first use**, as the directive permits |
| Confidence-calibration limitation disclosed | **PASS** |
| D-LOOP-1 for this measured run | **PASS** |

Canonical Phase 12 criteria remain green in source/tests: STT-only PTT, clarification on
ambiguity, approval for protected/destructive actions, typed/voice control-event
equivalence, offline `network=none`, discard by default, and diagnostic-retention TTL.
The live Phase 17C composition is not green.

## Mandatory independent reviews

Both reviews ran fresh, foreground, read-only, and completed inside this turn.

### Gate-validator: FAIL

The validator independently confirmed exact source identity, receipt hash, 40/42 result,
test totals, frozen hashes, current-run cleanup, tag ordering, and honest quota reporting.
It prohibited `gate/phase-17c` for the two red receipt legs.

It also dynamically falsified the new bootstrap-descendant claim: if the Electron child
reparents before the first process inventory, `tracked` contains only the dead bootstrap
PID and `waitForWorkspaceExit()` returns success while the child remains alive. This is
U157.

### Spec-auditor: FINDINGS

The auditor independently prohibited the tag and reported:

- the red exact-source receipt (blocking);
- incomplete Windows process-tree containment for Python→WSL probe/transcription timeout
  paths (U158);
- the same pre-first-inventory Electron reparent race (U157);
- an unauthorized/contradictory loop-runner execution-contract change at `7bb1ff6`
  (U159);
- teardown wording that overstates what the main-process check measures (U160);
- a receipt-check name that overstates exactness while explicitly excluding the
  pre-existing package lock (U161).

No prohibited TTS, MCP-authority drift, self-canonization, consensus forcing, extra
approval layer, or silent conflict behavior was found.

## Deviations, unresolved issues, and disposition

Substitution remains the directive-authorized fixture-WAV seam for the physical
microphone. Everything below the PCM handoff used the production path. The human-spoken
half remains operator first use. The real-engine confidence limitation remains explicit.

Open items:

- U150: provider quota leaves the exact receipt red;
- U157: pre-observation Electron reparent race;
- U158: Python→WSL timeout containment is not process-tree authoritative;
- U159: loop-runner backend contract contradicts the binding directive/prompt;
- U160: teardown log/evidence wording overclaims scope;
- U161: exact-tree receipt check name overclaims its package-lock exclusion.

`gate/phase-17c` was not created. This is not a directive section 8 blocker: no credential,
purchase, hardware, operator choice, or irreconcilable canonical contradiction is needed
to continue. Status remains `RUNNING`; `consecutive_failures` remains zero because this
unit produced work and evidence commits. The next work unit remains
`phase-17c.close-revalidate2` and must begin by fixing/revalidating U157–U161 before one
minimal exact-source live receipt is retried after provider availability.
