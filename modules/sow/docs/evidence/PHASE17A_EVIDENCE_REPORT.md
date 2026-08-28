# PHASE 17A — EVIDENCE REPORT (whole-track close)

**Work unit:** `phase-17a.close` (sub-step 4 of 4 — **`.lease` → `.pty` → `.roundtrip` → `.close`**;
this unit closes the whole Phase-17A track).
**Date:** 2026-07-25 · **Iteration:** 74 · **Status:** PASS (**HIGH-STAKES gate** — mandatory
independent `gate-validator` confirmation obtained, foreground, this turn).
**Tag:** `gate/phase-17a` lands with this unit.
**Governing directive:** `AUTONOMOUS_BUILD_DIRECTIVE.md` **§16 track 17A** (OP-11), **§13 (OP-8 — the
conductor is a live conversational pane)**, **§14 (OP-9 — live terms confirmed)**, loop protocol §3,
substitution §6, honesty §10.4, **D-P16-0** (every shell/UI change exercised by an in-Electron
self-check writing a machine-readable receipt), **D-LOOP-1** (live sessions spawned in a unit are torn
down within it), **D-LOOP-2** (print-mode: every suite and review run foreground, in-turn).
Load-bearing invariants: **1** (operator holds final authority — the app never self-authorizes),
**2** (every terminal a Sovereign node — no naked/raw CLI session), **3** (the conductor is a runtime
selection, never a vendor default — a fallback is surfaced, never silent), **7** (no authorization
logic inside `mcp_server/`), **20** (air-gap honesty), **29** (containment at the OS/process layer —
never trust the harness), **30** (minimal necessary control).

---

## 1. What the track delivered, and what `.close` does

**The operator's finding F3 — "conductor pane 1 `awaiting_live_conductor`, admission SHUT, typing gets
no answer" — is closed as far as a machine check can close it.** Typing into pane 1 now produces a live
answer from the model the operator selected.

| Sub-step | Iter | Work | Evidence | What it shipped |
|---|---|---|---|---|
| `.lease` | 71 | `439a43e` | `242409a` | `node_runtime/supervisor/terminal_lease.py` + `tools/live/emit_conductor_launch.py` (`conductor_launch_ticket@1.0`) + `apps/desktop/conductor/launch-source.js`: a **durable, cross-process** I-X3 terminal lease and a governed launch ticket (interactive argv, credential env **names only**, governed identity, an explicit "authorization is NOT containment" disclosure). |
| `.pty` | 72 | `9e8773a` | `b77a0ce` | The shell **executes** that ticket: the real interactive `claude` runs inside pane 1's ConPTY through the **supervised** session path, under the governed node identity, workspace-bound, credential env scrubbed, one durable terminal counted `1/2` in the status bar, released on exit/kill/quit/failure. Auto-launch on start **plus** an explicit pane-1 control; `SOW_CONDUCTOR_AUTOLAUNCH=0` and deleting `config/live_operation.json` are the operator's levers. Closed U75/U76/U77, narrowed U78. |
| `.roundtrip` | 73 | `a77a636` | `a2dfed2` | The live **model probe** (`adapters/frontier/claude_model_probe.py` + `tools/live/probe_conductor_model.py`): `--model fable-5` (the operator's selection *label*) is **rejected** by this host's CLI; `claude-fable-5` is **accepted**. Without it `.pty`'s session was live, supervised, counted and *unable to answer anything*. Plus the in-Electron type→answer receipt. Opened U81–U86. |
| `.close` | **74** | *this unit* | *this report* | **No product code.** Re-ran all three receipts and all three suites fresh in the foreground; obtained the mandatory independent `gate-validator`; re-ran `spec-auditor`; registered every finding; tagged. |

## 2. Exit criteria (directive §16 row 17A) — self-check with real command output

All commands run on this Windows host, foreground, this turn (Electron 31.7.7 / Node 20.18.0 /
Chrome 126 / win32-x64).

| # | Criterion (§16 17A) | Verdict | Evidence |
|---|---|---|---|
| 1 | Governed conductor spawn **RUNS the real interactive `claude`** in pane 1's ConPTY | **PASS** | `conductor-pty` receipt `ok:true`, `session_state:"RUNNING"`, live pid alive, `pane_excerpt` = the real `Claude Code v2.1.220 … Fable 5 · Claude Max` banner |
| 2 | fable-5 selection; unavailable ⇒ **recorded fallback, surfaced never silent** | **PASS (with U89 timing caveat)** | Probe ledger records the real attempts: `fable-5` → `model_unavailable` (the CLI's own wording), `claude-fable-5` → `accepted`. A missing/inconclusive record yields `model_available:None` — "could not probe" can never become "unavailable". Caveat: the *badge* lags one shell start on the first fallback run (**U89**) |
| 3 | FULL live-gate chain: live_operation switch → provider-live → OP-9 terms → I-X3 slot | **PASS** | `conductor-launch` receipt `gates:{live_operation_authorized, operator_terms_confirmed, cli_present, ix3_counted}` all `true`; `lease_durable:true`, `1/2`, `lease_visible_cross_process:true` |
| 4 | Admission opens only through the **verified supervised path** (inv 2, no naked spawn) | **PASS** | `terminal/conpty/session-manager.js` refuses without a `nodeId` and kills the child + throws `SupervisionDenied` unless `admit()` returns `supervised:true`; `main.js` refuses to launch when `!supervisor.ready`. Timing honesty: the child starts *then* is admitted (**U93**) |
| 5 | **Type→answer** proven by an in-Electron receipt, ONE minimal prompt | **PASS** | Builder run: `"…What is fifty-four plus thirty-five?"` → `SUM=89` in **3017 ms**. Validator's independent run, its own draw: `"…ninety-six plus seventy-eight?"` → `SUM=174` in **4028 ms**. `typed_via_renderer:true`, `answer_absent_before_submit:true`, operands spelled in words so an echo cannot satisfy the assertion |
| 6 | **Badge honesty** (inv 3) — `live`/`verified` only where the machinery genuinely yields it | **PASS** | The validator ran the emitter itself: `verified:false`, `is_fallback:false`, `executing.model:null`. `executing_verified` is set **only** from `executing_evidence`, which no interactive ConPTY supplies; the probe's own checkpoint is deliberately **not** promoted. The badge renders `(unverified)` — the honest lesser state |
| 7 | Self-check live sessions **torn down in-unit** (D-LOOP-1); operator's session persists by design | **PASS** | Every receipt: `session_killed:true`, `lease_released:true`, `in_use_after_release:0`. Post-run `tasklist`: **0** `electron.exe`; the `claude.exe` set is the unchanged baseline; the operator's real ledger `.sovereign_store/leases/terminal_leases.json` is untouched (`{"leases": []}`, mtime predates every run) — the checks use **scratch** ledgers |
| 8 | **Mandatory gate-validator** (high-stakes) | **PASS_WITH_RESERVATIONS** | §3 |

**In-Electron receipts (D-P16-0), regenerated fresh this turn:**

```
node selfcheck/run.js conductor-launch    → exit 0 · ok:true · lease-… 1/2 held by the shell pid · in_use_after_release 0
node selfcheck/run.js conductor-pty       → exit 0 · ok:true · claude --model claude-fable-5 live in pane 1 (cwd observed in the child = repo root, 5 credential vars scrubbed and absent, statusbar 1/2)
node selfcheck/run.js conductor-roundtrip → exit 0 · ok:true · typed through the renderer's own path → live answer, session killed, terminal handed back
```

**Test suites (foreground, this host):**

| Suite | Command | Result |
|---|---|---|
| Python control plane | `py -3.12 -m pytest tests/ -q` | **1194 passed / 0 failed** (210.51 s) |
| Electron shell | `node --test "test/*.test.js"` in `apps/desktop` | **199 pass / 0 fail** |
| Terminal layer | `node --test "test/*.test.js"` in `terminal` | **175 pass / 0 fail** |

**Committed receipts are the gate-validator's own regenerations** (`PHASE17A_LAUNCH_TICKET_SELFCHECK.json`
and `PHASE17A_PTY_SELFCHECK.json` started `2026-07-26T03:31Z`; `PHASE17A_ROUNDTRIP_SELFCHECK.json` started
`03:22Z`), per its reservation R0 — the tag lands on the commit carrying the receipts exactly as they
stood when it validated them. Nothing was re-run afterwards.

## 3. Mandatory independent gate-validator (HIGH-STAKES) — **PASS_WITH_RESERVATIONS**

Run in an isolated context, foreground, this turn; it trusted no builder claim.

- **Re-derived every criterion** from directive §16 line 411 and confirmed the whole-track-gate
  convention (`git tag --list "gate/phase-17*"` empty before this close — correct).
- **Re-ran all three self-checks and all three suites itself:** pytest **1194 passed** (210.78 s),
  apps/desktop **199 pass**, terminal **175 pass**; all three receipts exit 0 / `ok:true` with its own
  timestamps and hashes.
- **Reproduced the round trip independently** with its own randomly drawn operands (`SUM=174`,
  4028 ms) — a different draw from the builder's, which is itself proof the answer is a live model's
  and not a canned reply.
- **LOAD-BEARING FALSIFICATION ×2, both restored byte-identically** (`git status` clean; hashes
  recorded): (F1) injecting a headless `-p` into the emitter's argv → the shell's `BANNED_FLAGS` refused
  the ticket, receipt **RED** (`ok:false`, "launch ticket was not sourced from Python"), no spawn;
  (F2) forcing `resolve_launch_model` to ignore the probe ledger → the argv reverted to the bare label
  `claude --model fable-5`, proving the accepted slug is **recorded live data, not a constant**.
- **Honesty + prohibitions audit:** the four canonical SHA-256 prefixes verified by its own hashing
  (`6d3fd03b` / `8c9b7240` / `668089b5` / `cc414372`); `git diff product/usable..HEAD -- docs/canonical
  mcp_server schemas` **empty** (invariant 7 intact); no remotes configured; credential sweep over the
  whole track diff found names only, no values, in tickets, receipts, logs or either ledger;
  `config/live_operation.json` present but untracked; nothing outside the repo root.
- **Its live spend: exactly ONE prompt.**

**Reservations — R0 is a condition (honored), R1–R6 non-blocking and now all registered:**

| # | Reservation | Disposition |
|---|---|---|
| **R0** | The tag may land only on the commit carrying the close report **and** the receipts as they then stood; regenerating a receipt afterwards invalidates the validation | **Honored** — this report + those exact receipts are the gated commits; no receipt was re-run after validation |
| R1 | Neither *named entry point* (auto-launch branch, `> live` control) is receipt-covered — the checks call `launchConductorSession` directly | **U87**, owner `phase-17e` |
| R2 | The recovery banner never refreshes after supervision goes READY (stale "admission SHUT" text; fail-closed direction) | **U88**, owner `phase-17d`/17E |
| R3 | `IpcBusy` / `MAX_BUSY_SKIPS = 3` is a bounded relaxation of the fail-closed heartbeat | Already **U85**; re-affirmed here so the trade is owned, not absorbed (see §4) |
| R4 | The probe puts up to two live one-word calls on an unprobed host's unattended startup path, on `operator_terms_confirmed` — still a code literal | Already **U78(c)**; escalated exposure restated, owner `phase-17d` |
| R5 | The launch receipt's D-LOOP-1 assertion is blind on the ticket-undelivered branch (the product path *does* release) | **U92**, owner `phase-17d`/17E |
| R6 | U79/U81/U86 were owned by "`phase-17a.close`", a unit that adds no product code | Re-owned to `phase-17e` in an append-only correction block in the unresolved register |

Validator's bottom line, verbatim in substance: *the black pane is genuinely gone; typing into pane 1
gets a live answer from `claude --model claude-fable-5`, obtained by its own randomly drawn prompt
through the renderer's own input path, in a supervised, workspace-bound, credential-scrubbed,
I-X3-counted ConPTY session that did not outlive the run — and the evidence is falsifiable, falsified
twice.*

## 4. Independent spec-auditor — **NO PROHIBITED DRIFT** (no MAJOR/blocking findings)

Explicit rulings on the four questions put to it:

- **Invariant 1 — is auto-launch the app self-authorizing? NO.** The instruction is the operator's own,
  recorded verbatim (§16 17A, OP-11); the decision is made **Python-side and only read** by the shell
  (no JS path can produce `authorized:true` — the only JS writes are the fail-closed `false`); and the
  capability is **revocable without a code change and re-checked every launch**
  (`load_live_authorization()` is DENIED-by-absence, so deleting `config/live_operation.json` genuinely
  stops the next launch; `SOW_CONDUCTOR_AUTOLAUNCH=0` is the second lever; the durable I-X3 cap is the
  third bound). The one real invariant-1 surface is `operator_terms_confirmed: bool = True` as a **code
  literal** — it encodes the recorded OP-9 ruling, not a fabrication, but it should become a revocable
  artifact like `live_operation.json` precisely because it now rides an unattended startup path
  (**U78(c)**, owner 17D).
- **Invariant 2 — naked CLI anywhere? NO.** One spawn path; `nodeId` sourced only from the ticket's
  governed identity; the session manager refuses without a nodeId and without admission; renderer-supplied
  `env`/`cwd` are stripped. The one ungoverned throwaway that existed *during* the work
  (`tmp-diag-claude-pty.js`) was deleted and disclosed in `.roundtrip` §1 — confirmed gone.
- **Invariant 7 — authorization logic in `mcp_server/`? NO.** Zero matches; the track is entirely
  supervisor + adapter + tools + shell.
- **Invariant 30 — invented governance layer? NO, for both ledgers.** The lease ledger enforces an
  *existing* invariant (I-X3) whose allowance it is *given*, never chooses, and grants nothing; the
  in-process governor became provably decorative the moment a session outlived its emitter, so this is
  the minimal repair. The probe ledger caches one live observation feeding two **pre-existing**
  parameters of an already-gated spawn.

Also verified clean: no TTS (I-V2/D-VOICE-02 intact), no extra approval layer, no opaque-agent UI (every
refusal reason, node state, badge and lease `n/2` reaches the renderer), credentials as **names only**
throughout, both ledgers under the gitignored `<repo>/.sovereign_store/`, no float in any
allowance/counting logic, and fail-closed behaviour at every branch it enumerated (corrupt ledger refuses
and is never reset; a lock is broken only on a **dead owner pid**, not on age; Win32 `ACCESS_DENIED`
counts as *alive*, the fail-closed direction for a cap; JS timeout / non-zero exit / non-JSON / shape
drift all yield an unavailable ticket with **no spawn**).

Its findings F-1…F-5 are registered as **U89, U90, U91, U94, U93** respectively. Its observation on the
`IpcBusy` relaxation is recorded rather than absorbed: `IpcBusy` is raised **only** after the socket is
confirmed OPEN (never a transport fault reclassified), an in-flight request always settles at the 10 s
timeout, and 3 skips × 5 s strictly dominates it — every other fault remains an immediate supervision
loss.

## 5. Why no finding was fixed in this unit

Both reviews returned non-blocking findings only. Fixing product code here would have required
regenerating the receipts the validator had just validated, voiding its R0 condition and its two
falsifications — the build would have traded a verified gate for an unverified one. Every finding is
therefore **registered with a named owner** (U87–U94 + the ownership-correction block), and the
owners are the tracks that will actually touch those surfaces: 17B (worker/picker + ticket schema),
17D (defect closure + terms artifact + profile gate), 17E (chrome, assembled entry-point coverage).
Nothing was softened and nothing was left unrecorded.

## 6. Substitutions, limitations and OWED (directive §6 / §10.4 — honest)

- **The two named entry points are asserted, not evidenced (U87).** The receipts prove the launch
  *function* through the full gate chain; the auto-launch branch is short-circuited under
  `SHELL_SELFCHECK` and the `> live` button's IPC has no check. 17E's assembled receipt owns this.
- **Badge-fallback timing (U89) — a correction of record.** `.roundtrip` §4 criterion 5 recorded
  fallback surfacing as PASS without noting that the badge lags one shell start on the *first* run that
  records a fallback. Evidence reports are append-only, so the caveat lives here and in U89. On this
  host the verdict is ACCEPTED, so there is no fallback to hide today.
- **Containment is start-then-verify (U93), and OS-level containment remains OWED (U25/U78).** The
  ticket is an *authorization*, not containment — the ticket itself says so. Session registration and
  workspace binding are done; permission-profile binding and heartbeat are still named in the ticket's
  `containment.still_owed`; job objects are U25.
- **Air-gap gate unreachable in the product path (U91).** Both emitters hard-code
  `DeploymentProfile("cloud")` and the probe omits the profile-eligibility gate entirely. Invariant 20
  is honoured by the loader's own code but is not exercised by this track's paths.
- **`verified` is not claimable for an interactive session — by design.** An interactive ConPTY yields
  no machine-readable checkpoint, so the badge shows the honest lesser state rather than promoting the
  probe's checkpoint. That is invariant 3 working, not a gap being papered over.
- **`ruff` is not installed on this host** (`which ruff` → not found; `py -3.12 -m ruff` → no module), so
  the CLAUDE.md ruff-clean bar could not be machine-checked for this track. Recorded, unchanged from
  `.lease`/`.pty`/`.roundtrip`.
- **Not in this track (and not claimed):** live worker legs and picker spawn (U58/U70 → **17B**), voice
  (U74 → **17C**), the approval drawer's demo trio (F2 → **17D**), the assembled fully-live receipt
  (**17E**). 17A closes exactly one thing: the conductor pane is live and answers.
- **Live-budget discipline honored:** one prompt per round-trip run — one by the builder, one by the
  validator. No other live model call was made by this unit.

## 7. Invariants honored

1 (the app never self-authorizes: authorization is a Python decision the shell can only read; three
operator levers; explicit auditor ruling) · 2 (no naked session: single supervised spawn path, governed
identity, admission-or-kill) · 3 (the conductor is a runtime selection: the accepted slug is *recorded
live data*, proven by mutation; fallback recorded; `verified:false` where it cannot be earned) ·
7 (`mcp_server/` untouched — empty diff) · 20 (air-gap: honoured by the loader, unexercised here —
U91) · 21/I-X3 (one durable, cross-process terminal counted `1/2`, released always) · 29 (containment
disclosed exactly as far as it goes: start-then-verify, U93) · 30 (both ledgers are minimal mechanisms
for existing invariants — explicit auditor ruling) · D-LOOP-1 (no session, lease, gateway or Electron
process outlived the unit; the operator's ledger untouched) · D-LOOP-2 (every suite and both reviews run
foreground, in-turn) · §2.2 (credential **names** only, values never read, stored or transmitted).

## 8. Two-commit convention (this sub-step)

- **Work commit** `ea6aa4f` (`.close` adds no product code): the three in-Electron receipts as validated.
- **Evidence commit:** this report + the register rows (U87–U94, ownership corrections, decision-register
  row), carrying the work-commit hash → tag **`gate/phase-17a`**.
- Then the `LOOP_STATE.json` commit (iteration 74, `next_step: phase-17b`).

*End of `phase-17a.close` evidence report — Phase 17A whole-track close.*
