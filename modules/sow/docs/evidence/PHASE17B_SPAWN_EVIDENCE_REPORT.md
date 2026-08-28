# PHASE 17B — sub-step `.spawn` — EVIDENCE REPORT

**Track:** 17B "live workers: picker spawn (U70) + live legs (U58)" — `AUTONOMOUS_BUILD_DIRECTIVE.md` §16
(OP-11). **Sub-step:** `.spawn` (the second of `.ticket` → `.spawn` → `.legs` → `.close`).
**Date:** 2026-07-26. **Iteration:** 79. **Work commit:** see the register commit that carries it.
**Gate:** NONE — `gate/phase-17b` closes at `.close` with the whole-track evidence, exactly as 17A closed.

**Status: WORK-IN-PROGRESS CHECKPOINT, reviewed in-unit.** Both mandatory reviews ran FOREGROUND inside
this work unit against the implemented tree (directive D-LOOP-2: nothing survives a turn, so nothing was
left "in flight"). The gate-validator returned **FAIL** (1 BLOCKING, 2 MAJOR, 6 MINOR) and the spec-auditor
returned **PROHIBITED DRIFT: NONE** with 3 MAJOR / 7 MINOR. **Every finding is fixed or recorded below**,
and the fixes are mutation-proven — but the FIXED state has not itself been independently re-validated.
That re-validation is the first act of the next work unit (`.spawn-revalidate`), per §3.4.

---

## 1. What this sub-step claims — and what it does NOT

**Claims — the operator's picker click now LAUNCHES.** A per-pane model selection performs the governed
live spawn: the shell asks Python for a `worker_launch_ticket@1.0` and, only if one is ISSUED, runs that
exact argv in the pane's ConPTY through the supervised SessionManager, under the Python-minted node
identity, in the authorized workspace, with the named credential vars dropped — and hands the durable
I-X3 terminal back when the session ends, is killed, or the shell quits. A refusal starts nothing and says
which gate refused. **U70's spawn half is closed**; the machine-checkable part of operator finding F3
("selecting a model records + badges but launches nothing") is discharged.

**Also fixes U105** (owed to this sub-step): the credential-scrub NAME list is now classified over the
union of the emitter's environment and the env var names the SHELL holds. This was not cosmetic — see §4.

**Explicitly does NOT claim:**
- **U58 is NOT closed.** No live worker publishes a CANDIDATE; no conductor→worker exchange happens here.
  No prompt is sent to any model in this unit and no model answer is claimed. That is `.legs`.
- Containment beyond what the ticket already discloses (permission-profile binding U78(a), OS job
  object/ACL U25) is unchanged and still owed.
- The operator-visible assembled flow is 17E; this is one governed click, proven in-runtime.

## 2. Exit-criteria self-check (real command output)

| # | Criterion | Evidence (receipt = `docs/evidence/receipts/PHASE17B_SPAWN_SELFCHECK.json`, `ok:true`) |
|---|---|---|
| 1 | A picker selection starts a REAL local model session in a real pane | `local_launched:true`, `local_argv:["…\ollama.EXE","run","qwen3:8b"]`, `local_interactive_argv:true`, `local_session_state:"RUNNING"`, `local_session_pid_alive:true` |
| 2 | …and a REAL frontier session, subscription-governed | `frontier_launched:true`, `frontier_argv:["…\claude.EXE","--model","claude-fable-5"]`, `frontier_session_state:"RUNNING"` |
| 3 | Supervised admission only — invariant 2 | `supervision_ready:true`; the launcher requests no ticket at all while supervision is not READY (`worker-spawn.test.js`, `calls.tickets.length === 0`); `SessionManager.spawn` refuses without an admitted node |
| 4 | The node identity is PYTHON-minted (inv 2/29) | `local_node_id:"worker-pane-2"`, `frontier_node_id:"worker-pane-4"`, both asserted `=== worker-<pane>` |
| 5 | The ConPTY is bound to the governed workspace, on BOTH legs | `local_cwd_passed_to_pty` = `frontier_cwd_passed_to_pty` = the repo root, each read from the REAL node-pty boundary and matched to that pane's own binary first (`*_pty_spawn_is_this_pane:true`) |
| 6 | §2.2 — the child env lost every named credential var, on BOTH legs | `local_env_scrub_names_absent_from_child:true` (7 names), `frontier_env_scrub_names_absent_from_child:true` (7 names), `*_child_env_inherited_verbatim:false`, PATH preserved |
| 7 | U105 — the list is classified over the SHELL's environment | `shell_only_name_in_scrub_list:true`, `shell_only_name_absent_from_child:true` for a var only the shell spells that way (§4) |
| 8 | The pane is not black — the live process's bytes reach the renderer | `local_pane_output_seen:true`, `frontier_pane_output_seen:true` |
| 9 | I-X3: the frontier terminal is durable, session-keyed, cross-process visible | `frontier_lease_id`, `frontier_lease_session_keyed:true`, `frontier_lease_visible_cross_process:true`, `frontier_lease_in_use:1` |
| 10 | D-LOOP-1: released on session end; nothing outlives the unit | `frontier_lease_released_on_exit:true`, `frontier_in_use_after_exit:0`, `sessions_killed:true`, `surviving_pids:[]`; the REAL ledger `.sovereign_store/leases/terminal_leases.json` is untouched (`"leases": []`) |
| 11 | Fail-closed, in-runtime, each leg naming its OWN gate | `forged_launch_refused:true` (`forged_refused_by:"host_enumeration"`, chrome `launch_refused`, no new session), `occupied_pane_refused:true` |
| 12 | A refusal never disturbs a running session — process, RECORD, held terminal, chrome | `occupied_first_session_survived:true`, `occupied_launch_record_intact:true`, `occupied_held_after:true`, `occupied_chrome_intact:true` (§3 BLOCKING-1) |
| 13 | D-P16-0: the check runs inside the packaged Electron runtime | `env: {electron:"31.7.7", node:"20.18.0", chrome:"126.0.6478.234", platform:"win32"}` |

**Suites, fresh foreground (D-LOOP-2), after the final fix:**
```
py -3.12 -m pytest tests/ -q                              -> 1338 passed in 220.26s
cd apps/desktop && node --test test/*.test.js             -> tests 257 / pass 257 / fail 0
node --test terminal/**/*.test.js                         -> tests 175 / pass 175 / fail 0
cd apps/desktop && node selfcheck/run.js worker-spawn     -> shell exited code=0, receipt ok:true
```
(Baseline at the start of the unit: 1326 / 231 / 175. `pyflakes` clean on every Python file touched;
`ruff` remains unavailable on this host — the substitution recorded at `.ticket-revalidate3` stands.)

## 3. The reviews, and every finding

Both ran foreground in this unit, against the implemented tree, in isolated contexts.

### gate-validator — **FAIL** (it re-derived every claim, re-ran two of my mutations and both suites)

| # | Finding | Disposition |
|---|---|---|
| **BLOCKING-1** | **An occupied-pane refusal destroyed the running session's release accounting.** `refuse()` merged into the pane's record, so refusing a click on a pane that is already running a worker overwrote its `running` record with `refused` — and every release gate keys on that state. The durable I-X3 terminal then became **unreleasable for the life of the shell**: not on exit, not on kill, not on quit, and dead-holder reaping cannot fire because the holder is the shell. Two clicks and the operator is locked out of their own subscription. The validator reproduced it against the real module. | **FIXED** — `refuse()` never overwrites a record whose session this launcher still holds (and the attempt's OWN in-flight record is exempted by session key, so a failed launch still reports itself). Mutation-proven both ways: reverting it turns one headless test RED **and** the in-Electron receipt RED with `state=refused, still held=false`. |
| **MAJOR-1** | The same refusal repainted the live pane's chrome as `launch_refused` / `governed:false` and persisted it into the layout snapshot — a running, supervised, Python-authorized node described as dark (inv 3/27). | **FIXED** — a refusal carrying `heldSessionUntouched` leaves the pane's chrome alone; the refusal is still returned in full. |
| **MAJOR-2** | Neither the suite nor the receipt could SEE either defect: the headless occupied-pane test refused into a pane the launcher had never launched into, and receipt leg 3a asserted only the OS process. | **FIXED** — a new test launches first and then refuses, asserting record/held/lease survive; receipt leg 3a now re-reads `workerLaunchState`, `heldSessions()` and the pane chrome after the refusal. Both are the legs that go RED under the mutation above. |
| MINOR-1 | `releaseWorkerTerminalSync` — the entire quit-path release — had no test. | **FIXED** — covered with an injected `spawnSync`, including four fail-closed shapes. |
| MINOR-2 | `record.pid` was declared and never assigned, so a RUNNING pane published `pid:null` while the comment claimed otherwise. | **FIXED** — `spawnSession` returns the pid; a test pins it. |
| MINOR-3 | `ptySpawnObserved()` is the LAST spawn globally; the receipt attributed it to a pane by ordering alone. | **FIXED** — both legs assert the observed spawn's binary IS that pane's before reading its cwd/env as evidence. |
| MINOR-4 | A worker could be launched into the CONDUCTOR pane; only a CSS rule stood in the way (governance in the least-trusted layer). | **FIXED** — `refuseSelection` refuses a selection targeting pane 1 by id, with the reason. |
| MINOR-5 | The shell does not check that `identity.node_id` relates to the pane. | **RECORDED, not fixed** (U109): the `worker-<pane>` rule is Python's, and re-implementing it in the shell is exactly the duplicated-fact class U106 was opened for. The receipt asserts it on both legs; the ticket contract already pins session_id and pane_id. |
| MINOR-6 | `launchWorkerPane` is documented "never throws" but a throwing dependency rejected out of it. | **FIXED** — enforced with an outer catch that releases the terminal and records `failed`; a test injects a throwing scrub. |

### spec-auditor — **PROHIBITED DRIFT: NONE**

| # | Finding | Disposition |
|---|---|---|
| **MAJOR-1** | A launched pane's chrome kept reading `node_state:"running"` / `governed:true` after its session died — including after the fail-closed `killAll` on supervision loss — and every later layout snapshot baked that into what a restart replays (inv 3/27). | **FIXED** — `markWorkerPaneChromeEnded` revises the chrome on exit/kill (keeping the model badge, correcting state/governed/pid), persists it, and pushes it to the renderer over a new read-only `pane:chrome` stream so the operator's badge stops reading `live` for a dead pane. Two now-false comments in `layout-reconstruct.js` corrected. |
| **MAJOR-2** | The receipt's `scope_note` claimed for the FRONTIER leg facts only the LOCAL leg established (cwd binding, credential scrub, minted node id) — the leg that actually consumes a subscription terminal. | **FIXED** — the frontier leg now asserts all of them; the note describes what both legs establish. |
| **MAJOR-3** | "A spawn that throws ⇒ nothing was born" was an assumption the wiring did not honour: the injected `spawnSession` does five things AFTER `manager.spawn` succeeds, so a throw there would release the terminal while a live `claude` kept running — an uncounted live frontier terminal. | **FIXED** — the wiring rolls back (kills the just-spawned session) before rethrowing; the contract is stated at the call site. |
| MINOR-4 | `chrome.pid` always null (same as validator MINOR-2). | **FIXED** (above). |
| MINOR-5 | The §2.2 leftover guard was exact-spelling — blind to the very case divergence U105 exists for. | **FIXED** — the guard is case-insensitive. |
| MINOR-6 / MINOR-7 | Stale comments: the 16B block in `main.js` and the renderer's badge comment both described a shell that no longer exists; the badge itself always read `selected`. | **FIXED** — the 16B block is marked HISTORICAL; the badge renders the real launch state (`live` / `refused` / `failed` / `ended`) from the chrome main pushes. |
| MINOR-8 | The check starts a live frontier session while the ledger is redirected to scratch, so for that session's lifetime a live terminal exists that the REAL ledger does not count — undisclosed. | **FIXED by disclosure** — `scope_note_live_terminal` states it exactly (inherited from the 17A `.pty` pattern, now applied to a second live session class). |
| MINOR-9 | Every `shell_env_names` refusal reported the class default `selection_guard` — cross-gate id borrowing. | **FIXED** — its own gate id `shell_env_names`, asserted by tests on all five branches. |
| MINOR-10 | Dead `SOW_SELFCHECK_FAKE_KEY` save/restore implying a probe that does not exist. | **FIXED** — removed. |
| NIT | `session-manager.js` starts the PTY before asking the supervisor and kills it on refusal. | Pre-existing, not introduced here; unchanged. |

## 4. U105 was a real fail-open on this host, not a tidiness fix

The first version of the U105 receipt leg used an UPPER-CASE var name and **stayed green with the fix
reverted** — both processes spell such a name identically, so the leg proved nothing. Rewritten against
the divergence that is real here:

```
$ node -e "spawn py with env {Anthropic_Probe_Api_Key:'x'} …"
python sees: ['ANTHROPIC_PROBE_API_KEY']      # os.environ upper-cases every key on Windows
node keys:   ['Anthropic_Probe_Api_Key']      # Node keeps the case it was created with
```

The shell deletes from a plain object by exact spelling. So before this fix, a credential-bearing var
created in mixed case was named `ANTHROPIC_…_API_KEY` in the ticket, the shell deleted a key by that
spelling, nothing matched — **and the var reached the child process**. Reverting the fix and re-running the
in-Electron check reproduces exactly that: `shell_only_name_in_scrub_list:false`,
**`shell_only_name_absent_from_child:false`** (exit 1), while the pre-existing scrub leg stayed `true` —
it could not see it either. The classifier remains the ONE Python rule; the shell contributes only the key
spellings Python cannot see, as NAMES (a `name=value` entry is refused outright, its own gate).

## 5. What was built

| File | Role |
|---|---|
| `apps/desktop/picker/worker-spawn.js` (new) | The governed launcher — the ONLY place the shell executes a launch ticket. Injectable, so every governance rule is covered headlessly: admission before the ask, pane occupancy, the session key chosen before the ask (U100), authorization-only spawn, the §2.2 scrub + leftover abort, terminal handback on failure, and the exit/kill/quit release. |
| `apps/desktop/test/worker-spawn.test.js` (new) | 23 tests, one per rule; the occupied-after-launch and never-throws tests exist because the reviews found what their absence hid. |
| `apps/desktop/selfcheck/worker-spawn-selfcheck.js` (new) | The D-P16-0 in-Electron receipt: drives `spawnFromSelection` — the exact function the IPC handler calls — for a local pane, a frontier pane, a fabricated option and an occupied pane. |
| `apps/desktop/main.js` | `spawnFromSelection` LAUNCHES (it recorded a selection and started nothing at 16B); launcher wiring with post-spawn rollback and pid return; conductor-pane guard; release on exit/kill and blocking release on quit; chrome revised when a session ends. |
| `apps/desktop/picker/launch-source.js` | Sends `shell_env_names` (names only, `=`-bearing keys dropped); `releaseWorkerTerminalSync` for the quit path. |
| `node_runtime/supervisor/worker_pane_spawn.py` | `worker_env_scrub_names(shell_env_names=…)` — the union classified by the ONE rule — plumbed through `authorize_worker_pane` to both localities. |
| `tools/live/emit_worker_launch.py` | Parses/bounds the shell's names payload; refuses a `name=value` pair without echoing it; its own gate id. |
| `apps/desktop/renderer/renderer.js`, `preload.js` | The picker result line and the pane badge report the real launch state; a read-only `pane:chrome` stream repaints a pane whose session ended. |
| `terminal/recovery/layout-reconstruct.js` | Comments corrected: a worker pane's chrome can now legitimately carry `governed:true`. |

## 6. Substitutions and honest limits (Directive §6)

1. **The bounded `py -3.12` emitter, not the WS-IPC channel**, remains the shell→Python path (recorded
   since 16B). Unchanged here.
2. **Scratch lease ledger + pinned VRAM budget** in the receipt, both computed/declared, so the check
   never touches the operator's real terminal count and each leg exercises the branch its name claims.
   The budget is deliberately generous — it tests admission MECHANICS, not this host's capacity (U96).
3. **U100 is proven headlessly, not in-runtime.** Forcing a mid-flight emitter failure inside Electron
   would prove the corruption, not the release. Stated in the receipt's scope note.
4. **`ruff` unavailable on this host** — `pyflakes` clean is the substitution (recorded previously).
5. The local leg leaves the model resident in the Ollama daemon's own VRAM for its usual idle timeout —
   a daemon behaviour, not a process leak (`surviving_pids: []`).

## 7. Registers opened by this sub-step

- **U109** — the shell does not verify that a ticket's `node_id` relates to the pane it authorizes
  (validator MINOR-5). Deliberately not fixed: the `worker-<pane>` rule is Python's, and duplicating it
  in the shell is the U106 class. Travels with U104/U106's schema unit.
- **U110** — a worker pane whose session ends keeps its model badge with a corrected state; the pane is
  NOT offered a governed relaunch control. The operator can re-pick from the picker, which is the same
  path; a per-pane "relaunch" affordance is 17E's surface work.
- **U111** — the receipt's live legs consume a real subscription terminal against a SCRATCH ledger, so
  the REAL governor does not see them for the session's lifetime (spec-audit MINOR-8; inherited from
  17A `.pty`). A check that counted against the real ledger would be indistinguishable from the
  operator's own conductor — the honest fix is a governor that separates diagnostic holders, owed to 17E.

## 8. What is owed before `.close`

- **an independent re-validation of THIS fixed state** (`.spawn-revalidate`, the next unit's first act);
- `.legs` — U58: a live worker publishing a CANDIDATE over MCP → gates → conductor synthesis;
- then `.close` — the whole-track evidence, `gate/phase-17b`, and the mandatory reviews of the composition.


---

## APPEND-ONLY NOTE (2026-07-26, after the commits above)

**A scratch lease ledger file can survive the check.** After the final run, D-LOOP-1 verification found
`.sovereign_store/leases/selfcheck-17bspawn-<pid>.json` still on disk (contents: `"leases": []`). The
check removes the scratch file in its `finally`, but the shell's own teardown runs AFTERWARDS: `killAll`
fires kill events, whose async release path writes the ledger again, racing the env restore. So the file
that is left is EMPTY - no lease is held, nothing is counted, and the operator's real ledger
(`terminal_leases.json`) is untouched and empty - but the file itself is litter and the check claims to
"leave the host exactly as found". Removed by hand for this run; recorded here rather than quietly
tidied. The fix (await the pending releases, or remove the scratch file in the shell's teardown rather
than the check's) belongs with the `.spawn-revalidate` unit, which will re-run this receipt anyway.

---

# APPEND-ONLY BLOCK 2 — sub-step `.spawn-revalidate` (2026-07-26, iteration 80)

**What this unit is.** The owed independent re-validation of the FIXED `.spawn` state, per directive
§3.4 ("a FAIL is fixed in this or the next iteration, never softened, and the fixed state has to be
independently confirmed before the track moves on"). The `.spawn` reviews ran against the PRE-FIX
tree; everything above this line was, until now, verified only by the builder's own runs.

**Both reviews ran FOREGROUND in this unit** against the COMMITTED state at `0ec6489` (D-LOOP-2:
nothing survives a turn, so nothing was carried over as "in flight").

| Review | Verdict |
|---|---|
| **gate-validator** | **PASS_WITH_RESERVATIONS** — 1 MAJOR (new, introduced by `.spawn`), 6 MINOR |
| **spec-auditor** | **PROHIBITED DRIFT: NONE** — 2 MAJOR, 9 MINOR, 1 NIT |

**Every finding is fixed** except those recorded with reasons in §7 below. Work commit: see the
register commit that carries it.

## 1. What the validator confirmed as GENUINELY fixed (not re-fixed here)

It re-derived every claim itself and mutation-proved the `.spawn` fixes in BOTH directions:

- **BLOCKING-1** (a refusal destroying a running pane's release accounting, so the operator's durable
  I-X3 terminal became unreleasable for the life of the shell) — reverting the guard turns
  `worker-spawn.test.js:133` RED **and** the in-Electron receipt RED (exit 1,
  `state=refused, still held=false`). It also traced every sibling release path — exit, kill, quit,
  supervision-loss `killAll`, `pane:close`, the post-spawn rollback — and found no second route.
- **U105 / §2.2** on this host's real case divergence (`Anthropic_Selfcheck_<pid>_Api_Key` classified
  and absent from the child; `grep` over `docs/` for placeholder credential strings: no matches).
- The fail-closed legs, the frontier leg's containment assertions, the gate-id split, the pid fix,
  the `ptySpawnObserved` attribution, the never-throws enforcement.
- Suites reproduced at HEAD: **1338 / 257 / 175**, receipt regenerated with only run-identity fields
  differing from the committed one.

## 2. The convergent MAJOR — a restarted shell badged a DEAD pane `live` (both reviewers)

**The defect.** `markWorkerPaneChromeEnded` corrects a worker pane's chrome on an exit/kill EVENT, so
an orderly shutdown persists `session_exited`/`session_killed`. A death WITHOUT teardown — SIGKILL,
a main-process crash, power loss, i.e. precisely what a recovery module exists for — leaves
`{node_state:"running", governed:true}` on disk. `reconstructLayout` carried it verbatim,
`renderer.js` restored it into `paneBadges`, and `applyModelBadge` maps `node_state === "running"` to
the literal badge text **`live`**. On the next boot `paneSeq` restarts at 0, so the operator's first
new worker pane takes `pane-2` — the very id most likely to be in the stale snapshot — and a
brand-new, empty, unadmitted pane came up badged `· live` for a process that died with the last
shell. `needsRelaunch:false`, so no interrupted-notice contradicted it.

Before 17B `.spawn` this was unreachable: a worker chrome could only ever say
`selected_awaiting_governed_spawn` / `governed:false`. **This commit introduced it**, and disclosed it
only in a code comment at `layout-reconstruct.js:213-216` — while two OTHER comments
(`layout-reconstruct.js:216`, `renderer.js:349-350`) asserted the opposite ("Restoring it claims no
live node", "node_state stays awaiting-governed-spawn"). A defect disclosed in a comment, under two
comments denying it, is still a defect.

**The fix.** `_sanitizeRestoredChrome` in `terminal/recovery/layout-reconstruct.js`, applied at the
FOLD (not at capture — a captured `running` was TRUE when written and is false by construction after
a restart). A reconstructed pane has no live session by construction: every worker comes back
`reattach:false` / `admitted:false`. So a stale live `node_state` (`running`, `launching`, `live`,
`ready`) is REWRITTEN to `session_interrupted`, and `governed` is forced false on both branches —
there is no governed node in that pane right now, whatever the last shell wrote. The fact is not
erased: `interrupted_from` records what the pane was doing when the shell died, which is the true
statement the snapshot supports ("this pane WAS running") in place of the false one it made ("this
pane IS running"). The model badge is untouched — the operator picked it and it is what the pane last
ran. `interrupted_from` is DERIVED at the fold, so a corrupt or forged snapshot supplying one has it
dropped by the whitelist first. The renderer renders the new state as `interrupted (last run)`; both
false comments are corrected.

## 3. The other MAJOR — two of the three `.spawn` MAJOR fixes were invisible to every check

Reverting `markWorkerPaneChromeEnded` or the post-spawn rollback left the ENTIRE repo green: both
lived in `main.js`, which cannot be required headlessly (it calls `app.whenReady()` at load), and the
receipt had no field for either — the self-check kills its panes in `finally`, after the last
assertion. The `.spawn` report listed both as **FIXED** in a table whose other rows carry explicit
mutation proof, which is certainty by adjacency. The conductor-pane guard (validator MINOR-4) was in
the same state: correct, and unprovable.

**The fix — `apps/desktop/picker/pane-wiring.js` (new).** The three rules move out of `main.js`, pure
and injectable, exactly as `worker-spawn.js` exists so the launcher's rules are drivable; `main.js`
keeps the wiring and no rules. `apps/desktop/test/pane-wiring.test.js` (15 tests) drives each one, and
the receipt gains two legs that read what the OPERATOR's badge is drawn from:
`ended_chrome_revised` and `conductor_pane_refused`.

The rollback fix also gained the coverage the audit asked for: **every** post-spawn step is inside it,
one test per step (`createPane`, `persistLayoutSnapshot`, `pushState`, `emitLayoutNow`, and the
`registry.get` pid read that spec-audit MINOR-4 found sitting OUTSIDE the guard — a throw from there
would be read by the launcher as "nothing was born" while a live session was registered and running).

## 4. Mutation proofs (every fix, both directions)

Headless — each mutation applied alone, the file restored byte-identically afterwards:

```
RED   MAJOR-1 restored-chrome sanitizer                 exit=1
RED   MAJOR-1 governed:false half alone                 exit=1
RED   ended-chrome governed:false                       exit=1
RED   post-spawn ROLLBACK                               exit=1
RED   conductor-pane guard                              exit=1
RED   case-INSENSITIVE leftover guard (U105 class)      exit=1
RED   session-SCOPED outer catch (validator MINOR-5)    exit=1
RED   launch.cwd workspace binding (spec MINOR-8)       exit=1
```

**One of these caught a bad test of mine.** The first version of the session-scoped-catch test stayed
GREEN under mutation: it drove a SECOND launcher, whose records are its own, so the catch's
`get(paneId)` returned an empty record either way and the mutation was invisible — the same
"a fix whose test cannot see it" defect the reviews had just raised, reproduced inside the fix for it.
Rewritten to toggle a faulting dependency on the SAME launcher that already holds a live session, and
to drive both pre-record dependencies (`isSupervised`, `hasLiveSession`); now RED.

In-Electron (`node selfcheck/run.js worker-spawn`, the two NEW legs, each mutation run in full):

```
MUTATION: ended-chrome revision disabled
  exit=1 ok=False   ended_chrome_node_state='running'  ended_chrome_governed=True  ended_chrome_revised=False
  error: a pane whose governed session was KILLED still reports chrome "running" governed=true …
MUTATION: conductor-pane guard disabled
  exit=1 ok=False   conductor_pane_refused=False  conductor_pane_started_no_session=False
  error: a worker model was not refused into the CONDUCTOR pane pane-1 (no new session=false)
```

The second mutation did not merely fail an assertion — it **launched a live worker into pane 1**
(`started_no_session=false`), which is what makes the guard load-bearing rather than cosmetic.

## 5. Suites and receipt (fresh, foreground, D-LOOP-2)

```
py -3.12 -m pytest tests/ -q                          -> 1338 passed in 213.00s
cd apps/desktop && node --test test/*.test.js         -> tests 277 / pass 277 / fail 0   (was 257)
node --test "terminal/**/*.test.js"                   -> tests 179 / pass 179 / fail 0   (was 175)
cd apps/desktop && node selfcheck/run.js worker-spawn -> shell exited code=0, receipt ok:true
pyflakes tools/live/emit_worker_launch.py node_runtime/supervisor/worker_pane_spawn.py -> clean
```

Receipt (Electron 31.7.7) — the new/changed fields: `conductor_pane_refused:true` (against the REAL
pinned `pane-1`, not a hard-coded id), `ended_chrome_revised:true`
(`session_killed` / `governed:false` / model badge kept), `occupied_chrome_intact` now compares
`governed` and `launch_refused_by` as well as `node_state`, `scratch_ledger_removed:true`,
`real_ledger_unchanged:true`, `surviving_pids:[]`, `frontier_in_use_after_exit:0`.

**D-LOOP-1 verified after every run in this unit** (three full in-Electron runs: two mutations + the
clean regeneration): no surviving `electron.exe`, `.sovereign_store/leases/` contains only
`terminal_leases.json`, and the operator's real ledger is byte-identical (`"leases": []`, mtime
unchanged).

## 6. The scratch-ledger litter — the note's DIAGNOSIS was wrong, and the claim is now measured

Block 1's append-only note asserted a mechanism: "`killAll` fires kill events, whose async release
path **writes the ledger again**, racing the env restore." The validator probed that directly and it
does not hold — a release of an unknown session against an existing ledger leaves it byte-identical
(mtime unchanged), and against a MISSING ledger path creates nothing. Neither the validator's two runs
nor this unit's three reproduced the litter. So the fix the note proposed would have been aimed at a
cause not in evidence.

Rather than act on an unverified diagnosis, the check now **measures the two facts that actually
matter** and gates `ok` on them: `scratch_ledger_removed` (the scratch file is gone) and
`real_ledger_unchanged` (a byte comparison against a read taken BEFORE the redirection). If a
straggler release ever does recreate the file, the receipt goes RED and the real mechanism is learned
from a failing run instead of guessed at. Separately, teardown now **quiesces the pending releases
before restoring the env** — which also discharges spec-audit MINOR-6: the receipt's
`scope_note_live_terminal` claimed the check could "never" touch the operator's real ledger, while the
redirection was in fact torn down with releases still in flight. The comment `// leave the host
exactly as found` no longer stands alone as an assertion.

## 7. Every finding and its disposition

### gate-validator (PASS_WITH_RESERVATIONS)

| # | Finding | Disposition |
|---|---|---|
| **MAJOR-1** | A restarted shell badges a dead worker pane `live` (§2). | **FIXED** — sanitized at the fold, mutation-proven RED both halves. |
| MINOR-1 | The case-insensitive §2.2 leftover guard was uncovered: the only test driving it used an exact-case name, so it passed against the implementation the fix REPLACED. | **FIXED** — a case-divergent test (`Anthropic_Api_Key` in the env, `ANTHROPIC_API_KEY` in the list, an exact-spelling scrub injected); mutation-proven RED. |
| MINOR-2 | The conductor-pane guard had no test and no receipt leg. | **FIXED** — moved to `pane-wiring.refuseSelection` (4 tests) + a receipt leg against the real pinned pane id; both mutation-proven RED. |
| MINOR-3 | The register UNDERSTATED progress: U70/U100/U105 still read OPEN/owed while the report claimed them closed. | **FIXED** — append-only state block (U70 spawn-half RESOLVED / mode-toggle still OPEN; U100 RESOLVED with its disclosed limit restated; U105 RESOLVED). |
| MINOR-4 | The append-only note's litter diagnosis does not hold up under direct probing. | **FIXED** — §6: diagnosis retracted, the claim replaced by two measured, ok-gating fields. |
| MINOR-5 | The outer `launchWorkerPane` catch was not session-scoped for pre-record faults: a throw from `isSupervised`/`hasLiveSession` would release the LIVE session's terminal and overwrite its record — BLOCKING-1's harm by a second route. Latent (unreachable in product today). | **FIXED** — the catch releases and refuses against THIS attempt's key only (`attempt.sessionId`, set when the key is minted); mutation-proven RED on both dependencies. |
| MINOR-6 | OpenCode is absent from the governed picker→launch path, while the track text says "Ollama/OpenCode" and invariant 23 makes it first-class. Pre-existing (16B), fails closed. | **REGISTERED (U112)** — it is a coverage gap, not a hole; disclosed because the report's "does NOT claim" list omitted it. |
| Observation | node-pty `AttachConsole failed` stack noise on every receipt run. | **REGISTERED (U113)** — evidentiary, not functional; it would camouflage a real crash. |

### spec-auditor (PROHIBITED DRIFT: NONE)

| # | Finding | Disposition |
|---|---|---|
| **MAJOR-1** | The recovery half of the previous round's MAJOR-1 was never discharged, and two comments asserted it was. | **FIXED** — §2 (the same defect the validator found independently). |
| **MAJOR-2** | Two of three MAJOR fixes are invisible to every check in the repo; the report reports them FIXED beside mutation-proven rows. | **FIXED** — §3: rules extracted + 15 unit tests + 2 receipt legs, all mutation-proven. |
| MINOR-1 | The LOCAL leg's scrub check was case-SENSITIVE while the frontier leg (added by the previous fix) was case-insensitive — over-claiming on a case-insensitive OS. | **FIXED** — both legs lower-case now. |
| MINOR-2 | = validator MINOR-1. | **FIXED** (above). |
| MINOR-3 | `// leave the host exactly as found` contradicts the append-only note. | **FIXED** — §6. |
| MINOR-4 | The pid read (`registry.get`) sat OUTSIDE the rollback guard; a throw there means "nothing was born" to the launcher, which would be false. | **FIXED** — inside the guard, with its own test in the per-step loop. |
| MINOR-5 | A refusal returned the OTHER session's identity (`state:"running"` beside `launched:false`) as this attempt's result. | **FIXED** — the identity fields are this attempt's or null; the untouched session is reported under its own names (`heldSessionUntouched`, `heldSessionId`). |
| MINOR-6 | `scope_note_live_terminal` claimed "can never" for a window the code did not close. | **FIXED** — §6 (quiesce, then restore; note rewritten to what is established). |
| MINOR-7 | A forged `verified:true` from the RENDERER reached a refused pane's badge — Python closed this on the issue path, the shell's refusal path did not. | **FIXED** — `hostVerifiedFlag()` resolves `model_verified` from the HOST's own enumeration by (adapter, slug); an option this host does not offer is not verified, whatever the caller claimed. |
| MINOR-8 | U109's stated rationale is not the rule this file follows; and the shape contract accepted ANY `launch.cwd`. | **FIXED both halves** — the rationale is corrected in the register (append-only), and `fetchWorkerLaunchTicket` now refuses a ticket binding the session to a workspace the shell did not ask from (case-insensitive on win32 only, where the filesystem is); mutation-proven RED. |
| MINOR-9 | `occupied_chrome_intact` compared one field while the defect flipped three. | **FIXED** — compares `node_state`, `governed` and `launch_refused_by`. |
| NIT | The 1 TiB probe budget was disclosed in code, not in the receipt. | **FIXED** — `scope_note_substitutions` states both budgets and what they do and do not establish. |
| Pre-existing | `pane:new` accepts a renderer-supplied `file`/`args`, so a supervised-but-UNTICKETED model process is reachable from the least-trusted surface. | **REGISTERED (U114)** — outside this diff; recorded because it bounds the claim "the launcher is the only place the shell executes a launch TICKET" (true) against the stronger reading "…the only place the shell starts a model process" (false). Changing what `pane:new` may spawn is a product decision, not a review fix. |

## 8. Honest limits carried forward

1. **U58 is UNCHANGED and OPEN.** No prompt was sent to any model in this unit and no model answer is
   claimed. The conductor→worker CANDIDATE→gate→synthesis legs are `.legs`.
2. **U100's release is proven headlessly, not in-runtime** — unchanged, and restated in the register
   update so the RESOLVED mark cannot be read as more than it is.
3. **The containment the ticket discloses as owed** (permission-profile binding U78(a), OS job object
   U25) is unchanged and still owed.
4. **`ruff` remains unavailable on this host**; `pyflakes` clean is the recorded substitution.
5. **U111 stands**: the receipt's live legs consume a real subscription terminal against a scratch
   ledger, so the real governor does not see them for that window. Now bounded by a measured
   `real_ledger_unchanged`, which proves the ledger is untouched — not that the terminal was counted.
6. **The validator's own caveat, recorded:** its first pytest run showed 1 failure in
   `tests/integration/test_opencode_worktree_live.py` caused by ITS OWN concurrent Electron run
   holding `ollama run qwen3:8b`. It passes in isolation and the clean serial run is 1338. That live
   test is not robust to concurrent local-model load — registered as **U115**.

## 9. What is owed before `.close`

- `.legs` — U58: a live worker publishing a CANDIDATE over MCP → gates → conductor synthesis;
- then `.close` — the whole-track evidence, `gate/phase-17b`, and the mandatory reviews of the
  composition.

`.spawn` is now independently re-validated and CLOSES. No further re-validation of it is owed.
