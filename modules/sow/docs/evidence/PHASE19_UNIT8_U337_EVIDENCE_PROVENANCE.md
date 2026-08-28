# Phase 19 unit 19.8 — U337 evidence provenance and observed readiness

Date: 2026-08-14  
Work commit: `1d151e1fa48fdfbb164a2096014ed2281a06ab4f`  
Evidence boundary: this report and the two emitted receipts below  
Live-provider exchanges: **0**

## 1. Exit-criterion result

Unit 19.8 closes U337 and U437(e).

1. The packaged Electron shell now has an `orchestration-collaboration` self-check kind. It invokes
   the production governed dispatch source twice (launch-time and fresh check run), exercises the
   Python temporary-store/loopback-MCP collaboration path, observes descriptor assignment,
   CANDIDATE acceptance, synthesis/acceptance, pending operator disposition, renderer output and
   teardown, and emits modern source provenance.
2. `process_supervised` is no longer a spawn-success literal. A running worker record is true only
   when the SessionManager re-observes the exact PID and generation returned by birth. Readiness
   repeats that exact-identity observation. Missing or stale observation is false or absent.
3. The six audited readiness claims are no longer written true by success-branch assignment.
   `mcp_connected` is derived from the current gateway state; `stale` produces false. The runtime has
   no independent observer for `provider_authenticated`, `workspace_accepted`, `mcp_discovered`,
   `identity_validated`, or `permission_resolved`, so those fields are absent. This is the required
   honest outcome, not an omission defect.
4. Both historical `FINAL_*.json` files remain byte-identical. New sibling provenance notes label
   them operator testimony/manual acceptance records and point to the current machine-emitted receipt
   without upgrading its mock-first scope into live acceptance.

## 2. Product and test delta

- `apps/desktop/control/readiness-evidence.js` owns exact process/MCP/node observation shaping.
- `apps/desktop/control/worker-readiness.js`, `picker/worker-spawn.js`, and `main.js` consume those
  observers instead of assigning success literals.
- `apps/desktop/selfcheck/orchestration-collaboration-selfcheck.js`, `selfcheck/run.js`, and
  `main.js` add the bounded in-runtime kind and receipt dispatch.
- The existing readiness-window in-Electron check now obtains PID, generation and supervision from
  its real SessionManager rather than seeding `supervised:true`.
- New unit tests cover exact identity, absent observers, stale MCP, malformed feeds, dirty sources,
  and a stale spawned generation. Existing mutation baselines were re-read, documented, re-pinned,
  and fully rerun.

Work commit output:

```text
$ git show --stat --oneline 1d151e1
1d151e1 feat(desktop): add measured orchestration provenance
16 files changed, 470 insertions(+), 28 deletions(-)
```

## 3. Packaged in-Electron evidence (D-P16-0)

### 3.1 Orchestration/collaboration

Command, run only after the work commit with the tracked product tree clean:

```text
$ cd apps/desktop
$ node selfcheck/run.js orchestration-collaboration --unit 19.8
[selfcheck/run] shell exited code=0 signal=-
[selfcheck/run] ... remaining=-
```

Receipt:
`docs/evidence/receipts/PHASE19_8_ORCHESTRATION_COLLABORATION_SELFCHECK_19.8_20260814T233602Z.json`

```text
schema: phase19_8_orchestration_collaboration_selfcheck@1.0
check: orchestration-collaboration
ok: true
started: 2026-08-14T23:36:04.194Z
finished: 2026-08-14T23:36:05.395Z
electron_main_pid: 35928
source.commit: 1d151e1fa48fdfbb164a2096014ed2281a06ab4f
source.tracked_product_tree_clean: true
source.unexpected_untracked_product_files: []
live_exchanges: 0
failed_checks: []
missing_checks: []
fresh/launch legs: mock/mock
fresh/launch acceptance_verdict: PASS
fresh/launch operator_disposition: pending
fresh/launch torn_down: true
renderer_draws_sourced_dispatch: true
```

SHA-256:
`E57EF0CF3C699062B4A4E66C28E27B9DE8147B200E3599B5B4EBC908C480EEB2`.

This receipt does not claim a live provider, login, trust-modal answer, microphone, or operator
acceptance. It proves the governed mock-first orchestration/collaboration implementation inside the
packaged Electron runtime and preserves U58 as owed.

### 3.2 Readiness observation

```text
$ cd apps/desktop
$ node selfcheck/run.js readiness-window --unit 19.8
[selfcheck/run] shell exited code=0 signal=-
[selfcheck/run] ... remaining=-
```

Receipt:
`docs/evidence/receipts/PHASE19_4_READINESS_WINDOW_SELFCHECK_19.8_20260814T233806Z.json`

```text
check: phase-19.4.readiness-window
unit: 19.8
ok: true
source.commit: 1d151e1fa48fdfbb164a2096014ed2281a06ab4f
source.tracked_product_tree_clean: true
electron_main_pid: 36932
live_exchanges: 0
seeded_launch_record.per_pane[*].pid: observed integer
seeded_launch_record.per_pane[*].sessionGeneration: observed integer
seeded_launch_record.per_pane[*].supervised: true only on exact SessionManager identity
```

SHA-256:
`6FED3D465DE6A7C94B79E10E6ADCA7EA60C828DFCD49CFA5726E0E0DF95AF9D7`.
All child processes were gone at launcher completion (`remaining=-`) in both runs.

## 4. Behavioural validation

Focused unit/negative-control run after the final supervision-observer repair:

```text
$ node --test apps/desktop/test/readiness-evidence.test.js \
    apps/desktop/test/worker-readiness.test.js \
    apps/desktop/test/readiness-window-selfcheck.test.js \
    apps/desktop/test/orchestration-collaboration-selfcheck.test.js \
    apps/desktop/test/worker-spawn.test.js
ℹ tests 107
ℹ pass 107
ℹ fail 0
ℹ skipped 0
```

The load-bearing negatives include:

```text
✔ a stale session is established but is not reported connected
✔ an unavailable observer produces an absent field rather than a fabricated false
✔ a stale process observation never becomes literal supervised evidence
✔ a dirty product tree or malformed production feed fails the receipt
```

Full desktop suite on the exact work bytes:

```text
$ cd apps/desktop
$ npm.cmd test
ℹ tests 1000
ℹ pass 972
ℹ fail 0
ℹ skipped 28
ℹ duration_ms 99024.6131
```

The 28 skips are not hidden here. They are the known `py -3.12` discovery defect assigned to unit
19.9; this unit does not count them as executed.

Full terminal suite:

```text
$ node --test terminal/test/*.test.js
ℹ tests 216
ℹ pass 216
ℹ fail 0
ℹ skipped 0
ℹ duration_ms 202.1209
```

No Python product file changed in 19.8. The full Python timeout diagnosis and committed suite
configuration belong to unit 19.10 and are not pre-claimed here.

## 5. Falsification

All affected harnesses were rerun after the final code fix. Each restored its product files
byte-identically. The first readiness attempt was killed by an insufficient 240-second command
budget while R15 was active; its exact mutation was reversed, the intended SHA-256 restored, the
stale lock removed, and the entire harness rerun. Only the complete clean rerun below counts.

```text
$ node tools/mutation/readiness_signal_mutations.js
ALL 26 READINESS-SIGNAL MUTATIONS CAUGHT
restored .../worker-readiness.js SHA-256 25E5F135... — BYTE-IDENTICAL

$ node tools/mutation/system_pane_write_mutations.js
ALL 32 SYSTEM→PANE MUTATIONS CAUGHT
restored main.js SHA-256 2592555E... — BYTE-IDENTICAL
restored worker-readiness.js SHA-256 25E5F135... — BYTE-IDENTICAL

$ node tools/mutation/pane_input_bypass_mutations.js
ALL MUTATIONS CAUGHT
restored main.js SHA-256 2592555E... — BYTE-IDENTICAL

$ node tools/mutation/orchestration_mutations.js
ALL 14 ORCHESTRATION MUTATIONS CAUGHT; every file restored BYTE-IDENTICALLY
```

The pin comments name the exact 19.8 changes and why each existing mutation remains load-bearing;
the pins were not silently adopted.

## 6. Historical evidence preservation

The two original files were never edited. Their closing hashes equal their entry hashes:

```text
E31F0C8A0D86032B6AC61B8DFF342E78F1BFC14C489FB4C118FC17250A8B1953  FINAL_THREE_NODE_ORCHESTRATION_ACCEPTANCE.json
412C0932494DB8F6DB9B4D456B472BC7519EA267EF18F1221060486E5DDB968C  FINAL_TALK_WORKER_SPAWN_ACCEPTANCE.json
```

The sibling `.PROVENANCE.md` notes are additive. They distinguish testimony from measurement and
say explicitly that the new mock-first receipt neither reconstructs nor upgrades the historical
live claims.

## 7. Prohibitions and boundary

- No casual Electron application launch; only the two bounded self-check modes above.
- No Sovereign MCP server dependency or connection by the builder.
- No live provider run, provider login, trust modal, permission prompt, purchase, credential,
  remote, push, PR or publication.
- No dependency install. Operator-context Python discovery confirmed Python 3.12.10 already exists.
- No change to `tools/loop/run_loop.ps1`, frozen canonical material, or existing tags.
- The pre-existing untracked `.claude/settings.local.json` remains untouched and outside the receipt’s
  declared product paths.

## 8. Unit disposition

U337 is closed. U437(e) is closed. U437(a)-(d), (f) and (g) remain open under their recorded unit
19.9 owners; this unit does not imply their closure. The next work unit is Phase 19.9 / U338.

