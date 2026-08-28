# PHASE 17A `.pty` — EVIDENCE REPORT

**Work unit:** `phase-17a.pty` (second named sub-step of directive §16 track **17A — live conductor
session in pane 1**, HIGH-STAKES gate). **Not a gate close:** no tag is cut by this unit;
`gate/phase-17a` closes at `.close`, after `.roundtrip`, with the mandatory gate-validator on the
whole track.
**Date:** 2026-07-25 · **Loop iteration:** 72 · **Basis:** OP-11 (directive §16), OP-9 (live terms),
OP-6 (I-X3 = 2/subscription).
**Work commit:** see the register commit that carries this report.

---

## 1. What this unit ends

Operator first-use finding **F3**: conductor pane 1 reads `awaiting_live_conductor` — a black pane.
`.lease` built the two prerequisites (a durable cross-process I-X3 lease, and a governed **launch
ticket** the shell could execute) and shipped nothing operator-visible, on purpose.

`.pty` executes that ticket. On launch — and from an explicit **▶ live** control on pane 1's chrome —
the shell now spawns the **real interactive `claude` session inside pane 1's ConPTY**, through the
supervised session path, under the governed identity, bound to the governed workspace, with the
credential-bearing environment removed, holding one durable I-X3 terminal that is visible to other
processes and handed back when the session ends.

The receipt shows the operator's own pane rendering the live CLI:

```
▐▛███▜▌ Claude Code v2.1.215 ▝▜█████▛▘ fable-5 · Claude Max ▘▘ ▝▝
D:\multi model terminal app\sovereign-orchestration-workspace …
```

**Deliberately NOT claimed here:** the type→answer round trip (that is `.roundtrip` — this unit sends
no prompt and asks for no completion), live worker legs (17B/U58), and the OS job-object containment
that remains the Node Runtime's (U25).

---

## 2. What was built

| Artifact | Role |
|---|---|
| `apps/desktop/main.js` → `launchConductorSession()` | The governed launch: ticket → `SessionManager.spawn` (supervised admission, governed `nodeId`, workspace `cwd`, scrubbed env) → observable state. Called on shell launch, from `conductor:launch` (the ▶ live control), and by the in-Electron check — one path, no test-only variant. |
| release paths | On session **exit/kill** (async, by session key), on **quit** (bounded blocking release), and on every failure after the lease was taken (undelivered ticket, governed refusal, spawn failure). D-LOOP-1. |
| `node_runtime/supervisor/terminal_lease.py` | Lease keyed to `(subscription_ref, node_id, session_id)` — schema `@1.1`, reads `@1.0` as sessionless and **upgrades** a sessionless lease held by the same pid in place. `release_session()`. `seed_governor` projects by **lease key** so two sessions of one node cannot collapse into one holder. |
| `node_runtime/supervisor/subscription_governor.py` | `canonical_subscription_ref(provider)` — one spelling per subscription. Naming, not authority. |
| `tools/live/emit_conductor_launch.py` | `--session-id` **required**; `--release-session`; the ticket now carries `launch.cwd` (governed workspace), `launch.executable` (the binary the presence gate resolved), `identity.session_id`/`workspace`, and a containment block that names what the shell must bind **and what nothing binds yet**. |
| `tools/live/emit_subscription_status.py` | The always-visible n/2 bar is seeded from the **durable ledger** under the canonical ref; an unreadable ledger yields `status:null` (the em-dash unknown), never a fabricated `0/2`. |
| `apps/desktop/conductor/launch-source.js` | Session-keyed fetch (refuses a ticket for another session), stricter shape (cwd + executable + session key + lease-session agreement), `releaseConductorLeaseSession(+Sync)`. |
| `terminal/session/session-registry.js` `forget()` | Drops a **terminal** session record so pane 1 can relaunch; refuses while alive; the append-only log is untouched (invariant 12). |
| `terminal/compositor/pane-model.js` `attachSession()` | Binds a session to the pane that existed from first paint. |
| `apps/desktop/selfcheck/conductor-pty-selfcheck.js` (+ `run.js`, `main.js` wiring) | The D-P16-0 in-Electron receipt. |
| Tests | `tests/unit/test_terminal_lease.py` (+7), `tests/unit/test_emit_conductor_launch.py` (+7), `tests/unit/test_emit_subscription_status.py` (+5), `apps/desktop/test/conductor-launch-source.test.js` (+6), `terminal/test/pane-model.test.js`, `terminal/test/session-registry.test.js`. |

---

## 3. Exit criteria for this sub-step, with real command output

All commands run on the Windows host in this turn (foreground; D-LOOP-2 print-mode).

| # | Criterion | Result |
|---|---|---|
| 1 | The shell runs the REAL interactive `claude` in pane 1's ConPTY through the **supervised** path — no naked session (invariant 2) | **PASS** — receipt: `launched:true`, `session_registered:true`, `session_state:"RUNNING"`, `node_id:"conductor-pane-1"`, live pid. Validator mutation replacing `manager.spawn` with a direct `ptyFactory` call ⇒ receipt FAIL, exit 1 |
| 2 | argv INTERACTIVE (no `-p`/`--print`/`--output-format`) | **PASS** — `["claude","--model","fable-5"]`, `interactive_argv:true` |
| 3 | Workspace binding OBSERVED, not asserted | **PASS** — `cwd_passed_to_pty` = repo root (recorded at the node-pty boundary) **and** `cwd_observed_in_child:true` (the child's own banner prints the workspace) |
| 4 | §2.2 scrub OBSERVED on the environment the child was given | **PASS** — `child_env_inherited_verbatim:false`, `env_scrub_names_absent_from_child:true` (5 credential-bearing names present in this shell's env, none in the child's 66 keys; PATH retained) |
| 5 | **U75** — the durable terminal is keyed to the SESSION | **PASS** — `lease_session_keyed:true`; Python: two sessions of `conductor-pane-1` = 2 terminals, the third REFUSED at allowance 2 |
| 6 | **U76** — one canonical ref, and the always-visible bar reads the held terminal | **PASS** — `statusbar_row {ref:"sub-claude_code", label:"1/2", state:"active"}` read through the SAME function the product IPC uses; launch ticket / 16C spawn feed / status feed now agree on one spelling |
| 7 | **U77** — a lease is never stranded by an undelivered ticket | **PASS** — validator mutated the emitter to return a ticket for another session: `durable I-X3 terminal … RELEASED (ticket undelivered)`, receipt FAIL. Spawn failure path likewise: `RELEASED (spawn failed)` |
| 8 | Cross-process visibility of the count | **PASS** — `lease_visible_cross_process:true` (a separate `py` process sees the lease held by the Electron pid) |
| 9 | The pane is no longer black | **PASS** — `pane_output_seen:true`, the live CLI banner rendered into the renderer's xterm buffer |
| 10 | D-LOOP-1 — no live session, no terminal, outlives the unit | **PASS** — `session_killed:true`, `lease_released:true`, `in_use_after_release:0`, `node_state_after_exit:"live_conductor_exited"`; the operator's real ledger is byte-identical (`sha256 cb9ab75b…`, `"leases": []`) and no `claude.exe` started by this unit survives |
| 11 | Suites green | **PASS** — `py -3.12 -m pytest tests/ -q` → **1160 passed** (209 s); `apps/desktop` `npm test` → **177 pass / 0 fail**; `node --test terminal/test/*.test.js` → **175 pass / 0 fail** (the directory form is not supported by this Node 20.18 — the glob is the correct invocation) |
| 12 | D-P16-0 in-Electron receipt, `ok:true`, load-bearing | **PASS** — `docs/evidence/receipts/PHASE17A_PTY_SELFCHECK.json`; proven load-bearing by mutation (see §4) |
| 13 | Anti-overfit | **PASS** after two tautological ref tests were REPLACED with cross-module product-constant assertions (see §4) |

**Independent reviews (both run in the foreground this turn, per D-LOOP-2):**
- **gate-validator (isolated context):** first pass **FAIL** (two findings: the receipt asserted a cwd
  binding and a credential scrub it did not observe). Both fixed in-unit and re-validated — see §4.
- **spec-auditor:** **no PROHIBITED DRIFT**, 14 findings. Explicit rulings: the auto-launch is the
  operator's own instruction (§16 17A "on launch"), not the app self-authorizing — and it is revocable
  by deleting `config/live_operation.json`, which the gate chain re-reads per launch; the per-session
  lease key and the canonical ref are minimal mechanisms, not a new governance layer (invariant 30);
  the durable count grants nothing (invariant 21/22, OP-6 cap intact); badge honesty is preserved.

---

## 4. Review findings FIXED in this unit (re-verified after the fix)

| Ref | Finding | Fix |
|---|---|---|
| validator 1 (FIXED-REQUIRED) | `cwd_bound` compared the ticket to itself. Mutating the spawn to `os.homedir()` still produced `ok:true` — while the child genuinely ran in `C:\Users\Sslaw` — and the `scope_note` claimed the binding was proven | `ptyFactory` records the spec node-pty was ACTUALLY handed; the receipt asserts `cwd_passed_to_pty === REPO_ROOT` **and** `cwd_observed_in_child` (the child's own printed workspace, whitespace-squashed so pane wrapping cannot break the match) |
| validator 2 (FIXED-REQUIRED) | The credential scrub was a COUNT of names in the ticket; a shell that ignored `scrubbedLaunchEnv` entirely would still have passed, and the `scope_note` claimed the scrub was proven | Measured on the environment the child was given: `inheritedEnv` must be false, every credential name present in this process's env absent from the child's key set, PATH retained |
| validator 3 | After the session exited, pane 1 could never relaunch (the registry never forgets) and ▶ live silently no-opped | `SessionRegistry.forget()` (refuses a live session, keeps the append-only log) + relaunch; every early return now records its reason, logs it and pushes state, so the control's tooltip says why |
| validator 4 / auditor F3 | U76 was only partly true: `emit_conductor_spawn` still used `claude-sub` and runs on every shell start | Switched to `canonical_subscription_ref`; the ref tests now compare the PRODUCT constants to each other (the previous ones compared a constant to the function that defines it — they would have passed while this drifted) |
| validator 5 | `@1.0` → `@1.1`: a live shell holding a sessionless lease that then took a session-keyed one for the same session consumed 2 of 2 | `acquire` UPGRADES a sessionless lease in place when it is the same (ref, node) held by the same pid; another process's sessionless lease is never adopted. Two tests |
| auditor F1 | `pane:new` let the RENDERER — the least-trusted surface — choose a child's `env` and `cwd`, both of which now carry governance | `sanitizeRendererSpec` strips them and logs that it did; governed env/cwd come only from a launch ticket on the main-process path |
| auditor F2 | A ledger read fault left the always-visible bar rendering `0/2` with no warning — the exact display defect U76 was opened for ("0 is a claim") | An unreadable ledger now yields `status:null` ⇒ the em-dash unknown, with the fault named in `durable_leases.error` and `live_session_tracking.ledger_error` |
| validator 7 / auditor F7 | The receipt's `lease_released` was fail-open: a failed status read folded to `in_use:0` and was recorded as a released terminal | The release assertion requires `after.ok`; an unreadable count records `null` and fails |
| auditor F4 | The ticket's `owed_to` quietly dropped U78(a)'s **permission-profile binding**, which nothing performs (the ticket carries `permission_profile_id`; no one applies it) | `containment.still_owed` names it explicitly alongside the job object and the heartbeat; asserted in tests and restated in §5 and the register |
| auditor F8/F9/F12, F11 | Silent early-return no-ops; `SOW_CONDUCTOR_AUTOLAUNCH` undocumented; `live_session_tracking.owed:false` beside an `issue:"17B"`; stale `@1.0` docstrings and a sentence implying pid-recycling was fixed | Refusals are observable; the env var is documented in `apps/desktop/RUN_ON_WINDOWS.md`; `owed` stays true (worker leases are owed to 17B) with `conductor_counted:true`; docstrings corrected |

---

### 4a. Re-validation (same isolated validator, after the fixes) — **VERDICT: PASS**

The validator re-ran everything itself: pytest **1160 passed**, desktop **177 pass**, terminal
**175 pass**, `node selfcheck/run.js conductor-pty` **PASS/exit 0** with receipt values identical to
those recorded here. Four mutations proved the receipt is now load-bearing where it was not:

| Mutation | Result |
|---|---|
| M1 — the original `cwd: launch.cwd → os.homedir()` (previously PASSED) | **FAIL, exit 1**: "the ConPTY was started in `C:\Users\Sslaw`, not the governed workspace" |
| M2 — break only the REAL child, leaving the recorded boundary honest | **FAIL, exit 1**: "the live session did not report the governed workspace in its own output" — the two assertions are independent, and a shell that lied at the observation hook is still caught by the child's own words |
| M3 — pass an explicitly unscrubbed `env` (defeating the `inheritedEnv` flag) | **FAIL, exit 1**: child key count 71 vs the clean 66 — exactly the 5 credential names |
| M4 — revert `emit_conductor_spawn` to `claude-sub` | the replaced test bites: "one real subscription, 2 spellings: ['claude-sub', 'sub-claude_code']" — the tautological version could not |

Findings 4 and 5 confirmed closed behaviorally (all three product refs equal; same-pid legacy lease
upgraded in place at `in_use 1`, another pid's never adopted at `in_use 2`). Finding 3 confirmed
**real but partial** — the wedge is gone and refusals are recorded/pushed, the immediately-visible
message is not; opened as **U79** rather than papered over. Cleanliness re-confirmed: the operator's
ledger byte-identical (`sha256 cb9ab75b…`), no `claude.exe` from any run surviving, workspace restored.

Three new NOTES accepted and carried (none blocking, none silently fixed after validation — the
committed code is exactly what was validated): `ptySpawnObserved()` returns the last pty spawn
process-wide rather than keyed by session (sound for this one-spawn check); the operator-facing log
line still prints the ticket's `cwd` rather than the observed one (the line that misled the first
pass); and killing the conductor very early in its startup can emit a Node fatal-error dump from the
`claude` child (pre-existing kill-path behaviour, not introduced here). All three are carried to
`.roundtrip`, which regenerates an in-Electron receipt anyway.

## 5. Limitations, substitutions and OWED items — recorded, not implied away

**Scope honesty.** This unit proves a live, governed, supervised conductor session RUNS and RENDERS.
It does **not** prove the operator can type and get an answer — no prompt is sent and no completion is
requested (live-budget discipline, §16 "live exchanges MINIMAL"). That is `.roundtrip`.

**Containment, precisely.** Enforced for this child: supervised admission (the session cannot exist
without a currently-verified control-plane channel, and every session is killed if it is lost), the
governed `node_id` the shell cannot mint, the workspace `cwd`, and the §2.2 credential scrub — all
four observed in the receipt. **Not enforced, and named in the ticket's `containment.still_owed`:**
the **permission-profile binding** (U78(a)) and the OS **job-object/ACL** containment (U25 — the
pid→job handoff needs the IPC write op; unchanged for every shell session in this build) and the
per-node heartbeat.

**Substitutions (directive §6):** the emitter remains a bounded one-shot `py -3.12` read-source rather
than the WS-IPC channel — identical to the 16B picker, the 16C feeds, the 16D status bar and `.lease`,
and recorded for the same reason. `ruff` is **still not installed on this host** (`which ruff` → not
found; `py -3.12 -m ruff` → no module), so the CLAUDE.md ruff-clean bar could not be machine-checked;
style was held by hand against the surrounding modules. Recorded, not claimed.

**Host-dependence of one receipt field:** `env_scrub_count: 5` counts the credential-bearing names
that exist in *this* shell's environment (they are `CLAUDE_CODE_*` vars present because the check was
launched from inside a Claude Code session). On a clean operator launch it may legitimately be 0; the
load-bearing assertion is that whatever those names are, the child did not receive them and did not
inherit the environment verbatim.

**OWED, carried forward (register updated append-only):**
- **U75 — RESOLVED** (per-session lease key, upgrade path for `@1.0`, seeding by lease key).
- **U76 — RESOLVED** (one canonical ref across the launch ticket, the 16C spawn feed and the status
  feed; the bar reads the durable ledger; a ledger fault yields the honest unknown).
- **U77 — RESOLVED** (`--release-session` + release on every post-acquire failure, proven live by the
  validator's mutation).
- **U78 — NARROWED, still OPEN:** (a) the permission-profile binding and the heartbeat remain owed
  (session registration and workspace binding are done); (b) the scrub RULE is still name-resolved in
  the emitter rather than carried; (c) `operator_terms_confirmed` is still a code literal — and it now
  rides a path that runs automatically at every shell start, which raises its exposure (the auditor's
  F5; recorded in the register); (d) `release` still performs no ownership check. Owner: 17D/hardening.
- **New, opened this unit:** **U79** — after a live conductor session ends the shell can relaunch, but
  the *renderer* only reports a refusal to the console; the reason reaches the ▶ live tooltip on the
  next conductor push, not as a visible message. **U80** — `BANNED_FLAGS`/`argv[0] === "claude"` put
  vendor-CLI specifics in the shell layer; they must move behind the capability descriptor when the
  conductor runtime becomes genuinely selectable (I-SC1/I-03).
- **Unchanged owed:** U25 (job object), U58 (live worker legs), U70 (picker spawn) — 17B.

**Prohibitions honored:** no push/remote/publication; **no credential read, stored or transmitted**
(the ticket carries env var NAMES; the receipt records key names only, never values); no purchase;
nothing outside the repo root; `docs/canonical/` untouched; `config/live_operation.json` not committed;
the live exchange was a session start + kill with **no prompt and no completion requested**.

---

## 6. Verdict

`phase-17a.pty` — **PASS** (gate-validator: FAIL on the first pass, both required findings fixed
in-unit and re-validated; spec-auditor: no prohibited drift). The black pane is closed as far as a
machine can check it: a real, governed, supervised, workspace-bound, credential-scrubbed interactive
conductor session runs in pane 1 and renders, counted as exactly one durable I-X3 terminal and handed
back when it ends. Next work unit: **`phase-17a.roundtrip`** — one minimal typed prompt to that live
session and the answer back, in an in-Electron receipt.
