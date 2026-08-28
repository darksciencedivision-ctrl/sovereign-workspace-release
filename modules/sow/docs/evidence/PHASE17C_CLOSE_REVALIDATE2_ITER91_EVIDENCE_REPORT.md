# Phase 17C `.close-revalidate2` — Iteration 91 failed-gate evidence

Date: 2026-07-28  
Verdict: **FAIL — no tag**  
Final work source: `514d9fca2bd043030c3d41c568ae85a8d298c707`

## Objective and source state

This work unit addressed every local source/evidence defect opened by iteration 90
(U157–U161), then independently revalidated the Phase 17C gate. At entry,
`gate/phase-17b` was the latest Phase 17 tag, `gate/phase-17c` was absent, and
`LOOP_STATE.next_step` was `phase-17c.close-revalidate2`; tags and state agreed, so no
reconciliation commit was needed.

The pre-existing untracked `apps/desktop/package-lock.json` was preserved and excluded
from commits. Frozen canonical documents, schemas, and `mcp_server/` were unchanged.

Work commits:

- `cb27f86` — pre-spawn Windows Job ownership for packaged Electron checks; managed
  Python→WSL boundary; honest receipt/teardown wording; restored print-mode runner.
- `af818fb` — GO-gated managed target assignment before spawn; real outer-emitter-kill
  WSL regression; Claude-only loop runner.
- `b8df384` — raw, exact gate read so managed WSL program stdin is preserved.
- `514d9fc` — narrowed the text-mode stdin test claim to supported ASCII/LF input.

## Test-first record

Initial red checks:

```text
node --test apps/desktop/test/selfcheck-process-tree.test.js
tests 7; pass 4; fail 3

py -3.12 -m pytest tests/integration/test_wsl_parakeet.py \
  tests/integration/test_selfcheck_windows_job.py \
  tests/unit/test_loop_runner_contract.py -q
4 failed, 36 passed
```

After the first independent audit found assignment-after-spawn and runner-truth defects,
new red checks produced `2 failed, 2 passed`. After the second audit found buffered
handshake prefetch, the two production-stdin checks both failed: the generic target
received `""` instead of `PAYLOAD-123\nSECOND\n`, and real
`wsl.exe -- bash -c "python3 -"` produced no marker. The final raw-descriptor handshake
made both green.

Final exact-`514d9fc` focused output:

```text
py -3.12 -m pytest \
  tests/integration/test_frontier_process_tree.py \
  tests/integration/test_wsl_parakeet.py \
  tests/integration/test_selfcheck_windows_job.py \
  tests/unit/test_loop_runner_contract.py -q
47 passed in 43.86s

node --test apps/desktop/test/selfcheck-process-tree.test.js
tests 7; pass 7; fail 0
```

Broad suites were run after the final runtime change (`b8df384`); `514d9fc` changed only
a test name/docstring and its exact renamed test passed afterward:

| Command | Result |
|---|---|
| `cd apps/desktop; node --test test/*.test.js` | **488 pass, 0 fail** |
| `node --test terminal/test/*.test.js` | **201 pass, 0 fail** |
| `py -3.12 -m pytest tests/ -q` | **1429 pass, 61 warnings** in 479.08 s |
| `py -3.12 -m pyflakes <changed Python files>` | clean |
| PowerShell parse of `tools/loop/run_loop.ps1` | clean |
| `py -3.12 tools/manifest/compute_manifest.py --check` | frozen set clean |
| `git diff --exit-code gate/phase-17b -- docs/canonical schemas mcp_server` | empty |
| `git diff --check` | clean |
| `git fsck --no-dangling` | clean |

No marked self-check/job-member/WSL process spawned by this unit remained. The capture
directory contained zero files. The active outer loop process was observed to be the
pre-existing invocation of the old `-Builder codex` runner; it was not spawned or killed
by this unit. Current committed runner source is Claude-only and matches D-LOOP-2.

## Exit criteria and local defect closure

| Criterion | Result |
|---|---|
| Probe budget ≥60 s | **PASS** — 90 s |
| Non-blocking probe and visible `probing…` | **PASS** |
| Re-probe on demand/after failure; no lifetime pin | **PASS** |
| `SOW_*` overrides honored | **PASS** |
| U157 pre-first-inventory Electron ownership | **PASS** — assigned gated member before Electron spawn |
| U158 probe/transcription whole-tree containment | **PASS** — assignment-before-target, induced hangs, real outer-kill WSL proof |
| Managed WSL program stdin | **PASS** — supported ASCII/LF input executes through real `wsl.exe → python3 -` |
| U159 D-LOOP-2 runner truth | **PASS in committed source** — Claude-only |
| U160 teardown wording | **PASS** — limited to measured sessions/gateway |
| U161 receipt check naming | **PASS** — disclosed exclusions named |
| Propose-never-execute | **PASS in deterministic source/tests** |
| Transcribe-then-discard | **PASS in source/tests** |
| No TTS | **PASS** |
| Confidence-calibration limitation | **PASS — still disclosed** |
| Physical microphone | **OWED to operator first use**, as Phase 17C permits |
| Exact-source PCM→real Parakeet→bridge→live conductor receipt | **FAIL / absent** |
| Same live conductor answers | **FAIL / not exact-source proven** |
| Live tool call denied before execution | **FAIL / not exact-source proven** |

## Packaged receipt disposition

No live exchange was spent in this unit because the existing provider evidence records a
weekly limit with automatic reset on 2026-07-30 at 12:00 America/Chicago. The checked-in
receipt is unchanged:

- SHA-256:
  `4CD02AAA68DE4E4685D6106C840AEE555C22CE3DCDF2CE5567AA68783255CCDD`;
- source: `66c2bf3f456bcc06253cd4fbcc8f403f315975aa`, not `514d9fc`;
- result: `ok:false`, 40/42;
- red legs: `live_conductor_answered`,
  `voice_tool_call_denied_before_execution`.

It cannot gate the changed containment source. No claim is made that this iteration
completed the live composition.

## Mandatory independent reviews

Both reviewers ran fresh, foreground, read-only, and were awaited inside this turn.

The gate-validator independently passed U157–U161, 47 focused Python tests, seven JS
process-tree checks, real WSL stdin, real outer-kill WSL cleanup, the Claude-only runner,
Phase 17C source criteria, and freeze/scope checks. Final verdict: **FAIL; no tag
authorized**, solely because no passing exact-`514d9fc` packaged live receipt exists.

The spec-auditor first found and caused repair of the assignment race and runner mismatch,
then found and caused repair of the buffered-stdin defect. Its final exact-tree verdict
after the claim narrowing was **CLEAN**; no authority, audio-discard, TTS, MCP-authority,
or evidence-label drift remained.

## Deviations, unresolved issues, and disposition

The fixture-WAV substitution remains the directive-authorized machine-checkable seam for
the physical microphone. The human-spoken half remains operator first use. No provider
call was substituted or represented as live evidence.

U157–U161 are resolved in source and independently confirmed. U150 remains open: Phase
17C still needs one passing exact-source packaged receipt after provider availability,
then fresh mandatory reviews and the complete Phase 17C evidence report.

`gate/phase-17c` was not created. This is not a directive section 8 blocker: no credential,
purchase, hardware action, operator choice, or irreconcilable canonical contradiction is
required. Status remains `RUNNING`; `consecutive_failures` resets to zero because this
unit produced work and evidence commits. Next step remains
`phase-17c.close-revalidate2`.
