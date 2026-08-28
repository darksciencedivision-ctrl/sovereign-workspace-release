# Phase 19 · unit 19.9 — U338: orchestration coverage that can fail

**Unit:** `phase-19.9`  
**Work commit:** `324811be4706a2731f65ab0db7c24069a30a36cf`  
**Gate:** none; Phase 19 gates only after unit 19.10 and two cold reviews.  
**Live provider calls / Sovereign MCP connections / Electron launches:** zero. The operator prohibited
all three in this session.

## 1. Entry and scope

The unit began at the recorded 19.8 boundary `63096eb`. Units 19.1–19.7 were not reopened. Disk and
the directive agreed that 19.8 was closed, `LOOP_STATE` named `phase-19.9`, and OP-13.2 authorized
Codex to build through the Phase 19 gate subject to the directive.

The remaining orchestration surface in `main.js` was smaller than the audit's original description:
assignment verdicts, worker readiness, pane writes, conductor admission and gateway lifecycle were
already modules. This unit extracted only what remained: application-control sequencing and timers,
conductor readiness, and operational-state projection.

## 2. Product result

- `control/application-control.js` owns role checks, worker spawn/stop, assignment preflight and
  delivery, status, collaboration notification delivery and bounded work/peer/debate deadlines.
- `control/conductor-readiness.js` owns the admitted multi-turn readiness state machine. The
  extraction exposed and fixed a real live-only `ReferenceError`: the 19.8 inline success record
  read block-scoped `toolSucceeded` and `answered` after their loop. The behavioral test drives two
  turns and reads the resulting evidence outside the loop.
- `control/operational-state.js` owns worker/conductor status and dispatch projection. The
  operator-facing `MCP-unverified` sentence is now tested by executing the projection, not by slicing
  `main.js` as text.
- `main.js` now supplies Electron/PTY/gateway bindings to those modules. The remaining source-shape
  tests are limited to thin shell wiring and raw PTY-site exclusivity.
- `SovereignToolRuntime._assign_task` invokes the real shell preflight before `create_task`; the shell
  repeats it before the first pane write. A stale second owner therefore creates neither a partial
  first-owner delivery nor a durable routine `BLOCKED` task row.
- `SupervisorVoiceTurnAuthority.stop()` now has a 5 s default bound, destroys held sockets halfway,
  reports `{closed, forced, timed_out, timeout_ms, waited_ms}`, and participates in the normal-quit
  completion verdict. The application-control gateway's no-server result now has the same shape.
- All 28 desktop tests whose availability depends on `py -3.12` print an explicit reason when skipped.

## 3. Real MCP protocol coverage

`tests/unit/test_sovereign_tools_protocol_e2e.py` creates three authenticated real
`SovereignToolRuntime` instances over one real SQLite/CAS root. Only the Electron application seam is
a deterministic fake. Every declared tool is called through a JSON-RPC `tools/call` request and the
test asserts that the called-name set equals the declared `TOOLS` set:

`list_models`, `spawn_worker`, `stop_worker`, `assign_task`, `get_worker_status`, `send_message`,
`read_messages`, `publish_progress`, `open_debate`, `post_debate_turn`, `close_debate`,
`abort_debate`, `publish_artifact`, `read_artifact`, `publish_candidate`, and `publish_synthesis`.

The scenario persists and reads messages, progress, two debates (one closed, one aborted), a CAS
artifact, both worker candidates and the conductor synthesis. Protocol-boundary negative controls
prove conductor candidate publication and worker synthesis publication return `isError:true` before
any CAS write. A third negative control makes preflight refuse and proves `list_tasks(...) == []`.

## 4. Mutation quality

O1 no longer mutates `main.js` and asks a grep to notice the same line. It mutates the executable
shared-launch call in `application-control.js`; the behavioral spawn test must fail. O11 moved with
the assignment caller, and O12/O14 moved with the operational projection. O2–O5 remain the original
real HTTP/SQLite/process-environment falsifications.

The harness now requires both exit status 1 **and the name of the expected failing test** in child
output. A syntax error, missing file or startup failure is therefore `SURVIVED/SETUP-FAIL`, not
`CAUGHT`. This closes U439's classification hole.

The system→pane harness also followed conductor readiness into its module: M3 is graded by the modal
leg's observed zero writes. Main's raw write-site exclusivity remains a thin-binding mutation.

## 5. Validation — literal closing summaries

All commands below ran after the final executable change. Comment-only hash-pin corrections were
followed by a fresh complete orchestration mutation event.

```text
> & "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m pytest -q \
    tests/unit/test_sovereign_tools_protocol_e2e.py \
    tests/unit/test_mcp_collaboration.py \
    tests/unit/test_collaboration_policy_delegation.py
..................................................................       [100%]
66 passed in 1.98s
```

```text
> npm.cmd test                         # apps/desktop, operator context with Python 3.12
ℹ tests 1015
ℹ pass 1015
ℹ fail 0
ℹ skipped 0
ℹ duration_ms 99104.7917
```

The earlier restricted-sandbox run printed each unavailable test as, for example,
`# py -3.12 unavailable`, and summarized `986 pass / 28 skipped`; it also exposed two stale extraction
pins. Those were repaired and the complete suite above was rerun. The failed intermediate event is
not counted as acceptance evidence.

```text
> node --test terminal/test/*.test.js
ℹ tests 216
ℹ pass 216
ℹ fail 0
ℹ skipped 0
```

```text
> node tools/mutation/orchestration_mutations.js
CAUGHT O1 ... O14
ALL 14 ORCHESTRATION MUTATIONS CAUGHT; every file restored BYTE-IDENTICALLY

> node tools/mutation/system_pane_write_mutations.js
CAUGHT P1 ... M6
ALL 32 SYSTEM→PANE MUTATIONS CAUGHT
restored main.js, pane-writer.js, conductor-readiness.js, worker-readiness.js and
modal-affordance.js BYTE-IDENTICALLY

> node tools/mutation/pane_input_bypass_mutations.js
CAUGHT all rows
restored main.js ... BYTE-IDENTICAL
ALL MUTATIONS CAUGHT

> node tools/mutation/disarm_authority_mutations.js
CAUGHT U178-A ... U185
ALL 11 MUTATIONS CAUGHT
turn-authority.js and every other target restored BYTE-IDENTICALLY
```

`node --check` passed for `main.js`, all three extracted modules, both edited self-check/authority
modules, and all edited harnesses. `git diff --check` was clean. No dependency was installed.

## 6. Carried-item disposition

- **U432 remains OPEN in narrowed form.** Closed here: control-gateway and voice-authority outcomes
  now participate in quit success; the duplicate application-control decisions moved out of
  `main.js`. Still open: observed-vs-derived `was_listening`, discarded `server.close()` callback
  error, UI emphasis of freshness, and the heartbeat-linked status semantics. Owner: the next
  orchestration runtime-hardening phase.
- **U434 remains OPEN.** A gateway heartbeat is a protocol/lifecycle addition, not necessary to make
  U338's coverage executable. This unit did not manufacture one. Owner: next orchestration protocol
  phase, before claiming on-demand verification.
- **U435 CLOSED.** A real `net.Socket` that sends no newline cannot own shutdown; the test completed
  in about 68–79 ms under a 120 ms budget and reported forced clean closure.
- **U436 CLOSED.** Pre-create and pre-write preflights are both executable. The real JSON-RPC/SQLite
  negative control proves a routine refusal appends no task.
- **U437(a), (b), (c) and (g) implemented.** Universal stop shape, shared established-state predicate,
  exact production E1 payload, and `finally` cleanup for all three self-check servers are in the work
  commit. **U437(d) is instrumented but not emitted:** drawer cleanup is now a required self-check
  boolean. The explicit no-Electron constraint prevented a new packaged receipt, so (c), (d) and (g)
  remain measurement-owed at the Phase 19 gate. **U437(f)** remains a historical disclosure and is
  superseded only when unit 19.10 records a fresh full-Python result. U437(e) was already closed by
  U441 in 19.8.
- **U438 remains owned by 19.10.** This unit did not run tests concurrently and does not reclassify
  the recorded host-load failure.
- **U439 CLOSED.** Every mutation row must now name its intended failing test in output.

## 7. Prohibitions and boundary

No Electron application was launched; no Sovereign MCP server was contacted; no provider worker or
live-provider execution occurred; no dependency was installed; no remote, push, PR, publication,
credential, purchase or login occurred. `tools/loop/run_loop.ps1`, frozen canonical material and
existing tags were untouched. The pre-existing untracked `.claude/settings.local.json` was excluded
from both commits.

Unit 19.9 is closed on work commit `324811be4706a2731f65ab0db7c24069a30a36cf`. Unit 19.10 owns the
committed pytest configuration, full-suite diagnosis, carried U438/U437(f) result, two independent
cold reviews and Phase 19 gate decision.
