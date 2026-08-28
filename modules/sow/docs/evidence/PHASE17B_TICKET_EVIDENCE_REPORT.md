# PHASE 17B — sub-step `.ticket` — EVIDENCE REPORT

**Track:** 17B "live workers: picker spawn (U70) + live legs (U58)" — `AUTONOMOUS_BUILD_DIRECTIVE.md` §16
(OP-11). **Sub-step:** `.ticket` (the first of `.ticket` → `.spawn` → `.legs` → `.close`).
**Date:** 2026-07-26. **Iteration:** 75. **Work commit:** e4d2911. **Gate:** NONE — `gate/phase-17b` closes at `.close`, with the
whole-track evidence and the mandatory reviews, exactly as 17A closed.

**Status of this report: WORK-IN-PROGRESS CHECKPOINT.** The unit is implemented, self-checked and fully
tested, and every finding from three independent validation passes has been fixed in-unit — but **the
final state has not yet been confirmed by an independent pass** (§9 below). That re-validation is the
first act of the next work unit. Nothing here is claimed as validated that was not.

---

## 1. What this sub-step claims — and what it does NOT

**Claims:** a per-pane picker selection can now obtain a **governed, executable, interactive launch
authorization** (`worker_launch_ticket@1.0`) — or a fail-closed refusal — for both localities, through the
same gate chain the conductor pane runs, with the counting fact that matches the locality (a durable I-X3
lease for frontier; a ResidencyPlanner decision for local).

**Explicitly does NOT claim** (each is a later sub-step, and nothing in the code, receipt or naming says
otherwise):
- no session is spawned — no worker pane is live; the ConPTY launch is `.spawn`;
- **U70 is not closed** — the picker→spawn wiring in `apps/desktop/main.js` is untouched
  (`pane:spawnFromSelection` still records-and-previews as it did at 16B);
- **U58 is not closed** — no live worker publishes a CANDIDATE; that is `.legs`;
- operator first-use finding **F3 is not discharged**;
- no live model call is made anywhere in this unit.

## 2. Exit-criteria self-check (real command output)

| # | Criterion | Evidence |
|---|---|---|
| 1 | One picker selection → a governed interactive launch spec, or a fail-closed refusal | `tools/live/emit_worker_launch.py` (`worker_launch_ticket@1.0`), `node_runtime/supervisor/worker_pane_spawn.authorize_worker_pane`; 71 new Python tests |
| 2 | The FULL live chain for a frontier pane (roster/air-gap → provider-live → R8 §6 terms → CLI presence → I-X3) | `_authorize_frontier`; receipt `gates: {live_operation_authorized:true, operator_terms_confirmed:true, cli_present:true, ix3_counted:true}` |
| 3 | The terminal is DURABLE and cross-process visible, then handed back (D-LOOP-1) | receipt `frontier_lease_durable:true`, `frontier_lease_held_by_this_process:true`, `frontier_lease_visible_cross_process:true`, `terminals_released:true`, `in_use_after_release:0` |
| 4 | A LOCAL pane is NOT subscription-governed but IS residency-governed (inv 19/22) | receipt `local_subscription_governed:false`, `local_lease:"none"`, `local_residency` + `local_residency_budget` present |
| 5 | The slug the CLI actually accepts reaches argv (the 17A `.roundtrip` lesson) | receipt `frontier_argv: [claude.EXE, --model, claude-fable-5]`, `frontier_model_probe.source: "probe-ledger"` (the picker offered the label slug `fable-5`, which this host rejects) |
| 6 | §2.2 — credential env NAMES only, never values | receipt `frontier_env_scrub_name_count:5`, `frontier_env_values_absent:true`; `"env" not in launch` |
| 7 | The governed identity is minted Python-side (inv 2/29) | receipt `frontier_identity.node_id: "worker-selfcheck-pane-frontier"`, `permission_profile_id: "pp-worker-reasoning"` |
| 8 | Fail-closed refusals exercised IN-RUNTIME, each naming its own gate | receipt `forged_option_refused:true` (host-enumeration gate, reason asserted), `local_budget_refused:true` (VRAM gate, reason asserted), `conductor_role_refused:true` |
| 9 | D-P16-0: an automated check inside the packaged Electron runtime | `docs/evidence/receipts/PHASE17B_TICKET_SELFCHECK.json`, `ok:true`, Electron 31.7.7 / Node 20.18.0 / win32-x64 |

**Suites, fresh foreground (D-LOOP-2), after the final fix:**
```
py -3.12 -m pytest tests/ -q          -> 1265 passed, 61 warnings in 223.63s
cd apps/desktop && node --test        -> tests 218 / pass 218 / fail 0
cd terminal      && node --test       -> tests 175 / pass 175 / fail 0
cd apps/desktop && node selfcheck/run.js worker-launch -> shell exited code=0, receipt ok:true
```
(Baseline at the start of the unit: 1194 / 199 / 175.)

## 3. What was built

| File | Role |
|---|---|
| `node_runtime/supervisor/worker_pane_spawn.py` (new) | The ONE place an interactive WORKER pane is authorized. Frontier: the conductor pane's gate chain verbatim + I-X3 acquire + interactive argv. Local: no subscription gate, `ollama run <tag>`, ResidencyPlanner admission with a no-displacement rule. Mints the governed identity; refuses coding roles it has no worktree for (U95). |
| `node_runtime/supervisor/pane_node_spawn.py` | The selection guard extracted to `assert_selection_spawnable` and SHARED, so the headless dispatcher and the pane authorization cannot drift on greyed/mode/role/naked refusals. |
| `tools/live/emit_worker_launch.py` (new) | The ticket emitter: selection JSON on **stdin**, durable lease for frontier only, offline model-probe read, release modes, fail-closed refusal tickets. Verifies the caller's option against the HOST enumeration. |
| `apps/desktop/picker/launch-source.js` (new) | The fail-closed shell read-source + the ticket shape contract (see §5). |
| `apps/desktop/conductor/launch-source.js` | `runEmitter` gained `opts.input` (stdin) and `opts.env`. |
| `adapters/local/ollama_session.py` (new), `adapters/frontier/codex.py`, `adapters/detect.py` | Interactive argv builders for the two providers that had none, plus resolved-binary detection. |
| `tools/live/enumerate_pane_picker.py` | `host_residency_planner()` now returns the planner AND its budget provenance; the VRAM budget rule fixed (§4). |
| `apps/desktop/selfcheck/worker-launch-selfcheck.js` (new) + `run.js`/`main.js` | The in-Electron D-P16-0 receipt. |

## 4. The two blocking defects found by independent validation, and their fixes

**B1 — the VRAM budget was inverted, and the receipt depended on daemon timing.** The pre-existing
heuristic set the planner's TOTAL budget to the sum of *currently running* models, which were then
registered resident — so free VRAM was structurally 0 whenever the daemon had anything loaded. Harmless
while it only tinted a display chip (16B); this unit promoted it into an authorization gate, so it landed
here. The validator reproduced both directions on this host: `ok:false` with a model resident, `ok:true`
fifteen minutes later. Fixed: `SOW_VRAM_BUDGET_MB` when supplied, else a stand-in FLOOR (`max(running,
12288)`), always `estimate:true` with a `budget_source` string carried into the ticket; a
no-displacement rule decided from a read-only snapshot BEFORE any planner mutation; and the self-check
pins the budget and records that it pinned it. Honest remainder: **U96**.

**B2 — the shell's shape guard could be talked out of requiring an I-X3 count.** It read the ticket's own
`subscription_governed`, then (after the first fix) its own `chrome.locality`, then (after the second) a
denylist "is the binary named claude/codex?" — each defeated by a one-field lie or a wrapper
(`cmd /c claude …`, `node …/claude/cli.js`, `run-claude.bat`, a renamed binary, 8.3 names, trailing dots).
Fixed by inverting it to an **allowlist**: `chrome.adapter` must be one of the three this build
authorizes, the normalised basename of BOTH `launch.executable` and `argv[0]` must be exactly that
adapter's binary, locality/`subscription_ref`/`subscription_governed` must all agree with it, the
subscription must be that adapter's own, and a LOCAL argv may not name a frontier CLI anywhere.

## 5. The shell-side contract (what a ticket must prove before the shell will ever execute it)

Interactive argv (no banned flag, including its `=value` form; no `codex exec` anywhere; no `ollama run`
with a prompt positional), a resolved executable that matches the declared adapter, the governed cwd, the
Python-minted identity, matching session and pane, `chrome.governed`, and — by locality — either a HELD
durable lease whose subscription matches the identity's with `in_use <= allowance`, or no lease at all
plus a residency decision. Anything else is refused fail-closed to the un-launched pane.

## 6. Honesty / prohibitions

- **No live model call** in this unit; the model slug is an OFFLINE read of the 17A probe ledger.
- **No credential** read, stored or transmitted: names only (§2.2), verified in-runtime by the receipt.
- **Providers unchanged:** `claude_code` + `openai_codex_cli` (OP-6 scope) + local `ollama`. No new
  provider; an unknown adapter is refused fail-closed.
- **Nothing outside the repo**; `docs/canonical/` and `mcp_server/` untouched (inv 7); freeze manifest
  verified by the validator (`freeze check OK: no drift in FROZEN set`, four canonical hashes intact).
- **No remotes / no push**; `config/live_operation.json` remains untracked.
- **D-LOOP-1:** the real lease ledger `.sovereign_store/leases/terminal_leases.json` is `"leases": []`
  after every run; scratch ledgers removed; no orphan process.

## 7. Substitutions (directive §6)

The shell obtains its authorization through a bounded one-shot `py -3.12` emitter rather than the WS-IPC
channel — the same recorded §6 substitution the picker, status-bar and conductor feeds use, for the same
reason (the shell's gateway is the diagnostic echo surface; U25 gates the IPC write op).

## 8. Registers opened by this unit

**U95** (coding panes refused — no worktree to give), **U96** (VRAM admission vs proven fit; stand-in
budget; non-durable reservation), **U97** (codex `-m` id unprobed), **U98** (operator-terms gate has no
product input — extends U78(c)), **U99** (`worker_launch_ticket@1.0` has no file in `schemas/` — same gap
as U90). All are cited by the shipped code and now exist in the register (validator FINDING 6).

## 9. Review status — INCOMPLETE, stated plainly

| Pass | Verdict | Outcome |
|---|---|---|
| gate-validator #1 | **FAIL** | B1 (VRAM budget + non-deterministic receipt), B2 (uncounted frontier launch could pass the shape guard), 8 reservations |
| spec-auditor #1 | FINDINGS (3 MAJOR, 10 MINOR, 8 NIT), **no prohibited drift**, no invariant violation it could prove | MAJOR-1 (a reasoning pane has the CLI's full tool surface — inherited from 17A, recorded), MAJOR-2 (the caller's option was never verified against the host), MAJOR-3 (invariant 22 over-claimed) |
| gate-validator #2 | **FAIL** | B1 confirmed FIXED (proven with a model resident on the host); B2 still open via a `chrome.locality` lie; 7 further findings |
| gate-validator #3 | **FAIL** | the no-phantom-mutation fix confirmed genuinely fixed; B2 still open via wrapper/rename binaries; a forged `verified:true` reached the badge; two receipt legs proven vacuous |
| **after pass #3** | **not yet independently re-validated** | every blocking finding fixed in-unit (§4, §10); verified by my own 17-case attack matrix, 4 new JS tests, 3 new Python tests and a regenerated receipt — **not** by an independent pass |

**This is why the report is a checkpoint.** The directive's rule is "validator FAIL → fix in this or the
next iteration; never soften, never skip". The fixes are made; the independent confirmation is owed and is
the next unit's first act. `gate/phase-17b` cannot close until it is obtained.

## 10. Findings fixed in-unit (from all three passes)

1. VRAM budget inversion + stand-in floor + provenance carried into the ticket (B1/R2).
2. No-displacement rule, decided before any planner mutation (B1 / MAJOR-3 / FINDING 3).
3. Receipt determinism: the local leg's budget is pinned and the pin is recorded (B1).
4. Locality/adapter/binary allowlist in the shape guard (B2 / FINDING 1) + subscription-ref consistency,
   `in_use <= allowance`, no smuggled residency, `=value` banned flags, `exec` anywhere, `ollama run`
   after a flag.
5. The HOST's option — not the caller's — supplies `verified`/`label`/`roles` (FINDING 3 / MAJOR-2).
6. The caller's option is verified against the host enumeration; an unenumerable host refuses (MAJOR-2).
7. Durable lease released when a refusal is raised after `acquire`; `governor_released` measured on both
   branches (R1 / MINOR-1).
8. `ValueError` from an argv guard is a governed refusal ticket, not a traceback (MINOR-8).
9. Codex tickets state `model_probe.source: "unprobed-codex"` (MINOR-7 → U97).
10. Pane ids bounded to `[A-Za-z0-9._-]{1,64}` — `#` excluded because it is the lease-key delimiter
    (MINOR-10 / FINDING 7).
11. Receipt legs assert the REASON, and the forged-option leg forges the escalating direction (FINDING 2/4).
12. Docstring over-claims corrected ("both refuse identically", "chrome verbatim", "proven to fit").

## 11. Accepted with record (not fixed here)

- **MAJOR-1** — a frontier *reasoning* pane runs the vendor CLI with its full interactive tool surface and
  the project workspace as cwd, restrained by the CLI's own approval flow (invariant 29 says not to trust
  the harness). Inherited from the 17A conductor pane, not introduced here; the codex branch already pins
  `--sandbox read-only --cd`. Owner: the U25 OS-containment work.
- **Validator FINDING 8 residue** and the stand-in floor's over-admission risk on a small GPU — recorded
  in U96.
- **No product consumer yet** — by design; `.spawn` wires it.

---

# APPEND-ONLY CORRECTION BLOCK — `phase-17b.ticket-revalidate` (2026-07-26)

Evidence reports are append-only. Everything above is left exactly as written; this block records what
the independent re-validation of that state found and what changed. **The report above describes the
committed `.ticket` state (work `e4d2911`, evidence `8e0f773`), which a fourth gate-validator pass
FAILED.** Read the two together, this block last.

## 1. Why there was a fourth pass

The `.ticket` report §9 lists three validator passes, all FAIL, each followed by fixes. Those fixes were
verified by the builder's own runs and never independently. `docs/loop/LOOP_STATE.json` recorded that
explicitly and set `next_step = phase-17b.ticket-revalidate` so the next unit's first act would be a
fresh, foreground, independent pass on the committed state. This block is that unit's result.

## 2. What the fourth pass found (verdict: FAIL)

- **BLOCKING-1a — the VRAM budget inversion was NOT fixed, only moved.** The report above (§4, §10 item 1)
  records the fix as `max(running, 12288)`. Above the floor that still lets the running set define the
  budget, and those same models are then registered resident, so free VRAM is again structurally 0. The
  validator reproduced it: a 24 GB card serving 16 GB refuses every local pane with 8 GB genuinely free.
  **§2 criterion 8's "VRAM gate" claim and §4/§10's "Fixed" are corrected by this block.**
- **BLOCKING-1b — the same fix introduced a crash.** `SOW_VRAM_BUDGET_MB` smaller than a resident model
  let `ResidencyError` escape `_host_residency` → `build_host_picker` → `main`, so the operator lost the
  WHOLE picker, frontier options included. Reproduced at exit 1 with zero stdout.
- **BLOCKING-1c — the receipt's VRAM leg did not prove the gate it named.** The leg regex-matched
  `/VRAM|residency|displacing/i` over the refusal prose; the BLOCKING-1b crash message contains "VRAM",
  so the leg passed on an ENUMERATION fault while `ok:true` was still reported. **§2 criterion 8 ("VRAM
  gate, reason asserted") and the self-check's own claim that "each refusal leg names the gate it
  exercises" are corrected by this block: they were true of the forged leg only.**
- **MAJOR-1 — the shape contract's two binary checks had no independent coverage.** Deleting either the
  `launch.executable` or the `argv[0]` basename check alone left the JS suite 19/19 green, and with the
  `executable` line gone a ticket declaring `ollama_local` while pointing `executable` at `claude.EXE`
  was ACCEPTED — an uncounted frontier terminal, on the field the shell actually spawns.
- MINORs: the over-budget refusal blamed a resident model even when nothing was resident; the
  `conductor_role_refused` leg asserted no reason; a model in `/api/ps` but absent from `/api/tags`
  raised the budget without occupying it; `["ollama","run","x && claude"]` passed the frontier-token
  boundary; and a lease taken before an emitter timeout is left counted (now U100).

## 3. What this unit changed

| Area | Change |
|---|---|
| `tools/live/enumerate_pane_picker.py` | The budget is a CONSTANT (`SOW_VRAM_BUDGET_MB` else the stand-in), fixed BEFORE residency is read — never derived from the resident set. A budget the host's own residency FALSIFIES (more resident than it claims exists) yields no planner, `established:false`, and a `budget_source` naming the contradiction and the one-line fix. `ResidencyError` during seeding degrades the local list instead of escaping. A model in `/api/ps` but absent from `/api/tags` now occupies VRAM. Provenance rows are staged so a caller can never read a healthy budget for a planner that does not exist. |
| `…/enumerate_pane_picker.py` + `control_plane/nodes/pane_picker.py` + `scheduler/residency_planner/residency_planner.py` | **A new defect the fix itself introduced, found by both reviewers and fixed in-unit:** the degraded branch returned an EMPTY residency map, and the picker defaults an absent model to `not_loaded` — telling the operator a model the daemon is actively serving is not in VRAM. `None` (no view) is now distinct from an empty map, and renders the new `UNKNOWN` state. |
| `node_runtime/supervisor/worker_pane_spawn.py` | Refusals carry a machine-readable `gate` id. The local gate refuses on `established is not True` as well as on a missing planner (an authorization is never granted against a budget nobody vouched for — spec-audit MAJOR-1). Over-budget messages state the cause the snapshot shows. A selection with no `model_slug` is a `selection_guard` refusal, not a VRAM one. |
| `node_runtime/supervisor/pane_node_spawn.py` | `SpawnRefused` carries a gate id (default `selection_guard`); the dispatcher's "proven to fit" over-claim corrected to ADMISSION against an unverified budget. |
| `tools/live/emit_worker_launch.py` | The ticket reports `refused_by` — the gate that refused — with the host-enumeration check on its own id, deliberately distinct from the selection guard. |
| `apps/desktop/picker/launch-source.js` | Shell metacharacters refused in any argv element or the executable; frontier-token boundary widened; a governed refusal that does not NAME its gate is malformed; the unavailable shape carries `refused_by: null` so the two producers agree; a dead normalisation line removed. |
| `apps/desktop/selfcheck/worker-launch-selfcheck.js` | All three fail-closed legs assert the ticket's `refused_by` GATE ID (`host_enumeration` / `vram_admission` / `worker_role`), the conductor leg pairs it with its own reason, and the local leg now requires an ESTABLISHED budget rather than merely a present one. |

## 4. Evidence produced by this unit

- **Suites, fresh and foreground:** `py -3.12 -m pytest tests/ -q` → **1303 passed** (255.88 s);
  `node --test` in `apps/desktop` → **222/222**; in `terminal/` → **175/175**. (1303 rather than the
  1307 measured mid-unit: four tests that asserted the old fail-open behaviour were replaced by
  refusal tests, and one tautological test became a driven one.)
- **In-Electron D-P16-0 receipt** `docs/evidence/receipts/PHASE17B_TICKET_SELFCHECK.json`, regenerated
  from the shipped code after every mutation was restored: `ok:true`, Electron 31.7.7, both localities
  authorized, `forged_refused_by:"host_enumeration"`, `local_budget_refused_by:"vram_admission"`,
  `conductor_refused_by:"worker_role"`, `in_use_after_release: 0`.
- **Mutation proofs run by the builder** (each file restored byte-identically, SHA-256 verified):
  (a) each of the four guard lines in `frontierClaim` deleted in turn → the JS suite goes red on its
  own dedicated assertion, four for four; (b) `_gate_id` forced to report `WorkerPaneRefused` under
  `host_enumeration` — i.e. the exact BLOCKING-1c scenario — turns the receipt **RED** on the VRAM and
  conductor legs (`ok:false`, `local_budget_refused_by: "host_enumeration"`) while the forged leg stays
  green, proving the legs now discriminate between gates.
- **Independent confirmation: NOT YET OBTAINED for this state.** The gate-validator pass that produced
  the findings above ran against the pre-fix committed state. The fixes in §3 — including the
  residency-display defect the reviewers found in the fix itself — were verified by the builder's own
  runs only. That is why this sub-step remains a WORK-IN-PROGRESS checkpoint and `LOOP_STATE.next_step`
  is `phase-17b.ticket-revalidate2`, not `.spawn`.

## 5. Findings recorded rather than fixed

U100 (a terminal counted for a ticket the shell never receives), U101 (`refused_by` added under an
unchanged `@1.0` pin — the defect U90 named, in the track U90 named), U102 (the disclosed
`running_vram_mb` is not the number the gate enforced), U103 (the metacharacter/frontier-token rules can
refuse a legitimate host opaquely). Plus append-only corrections to U96 (its description of the budget
rule was stale in four ways) and to the residency-display family. Also standing and unchanged: the
frontier reasoning pane inherits the vendor CLI's full tool surface (accepted-with-record, U25).

## 6. Scope honesty, unchanged from the report above

Nothing in this unit spawns a session. U70's spawn half and U58's live legs are OPEN; the picker click is
still not wired to a ticket; operator finding F3 is not discharged. No live model call, no credential
(env NAMES only), no new provider. `docs/canonical/`, `mcp_server/` and `schemas/` untouched. D-LOOP-1:
no session, lease, gateway or Electron process outlived the unit; the operator's real lease ledger is
untouched and the scratch ledgers are removed. `ruff` remains unavailable on this host, so the
ruff-clean bar could not be machine-checked.

---

# APPEND-ONLY BLOCK 2 — `phase-17b.ticket-revalidate2` (2026-07-26)

Evidence reports are append-only, so everything above stands as written. This block records the OWED
independent confirmation, what it found, and what changed. It supersedes the "Independent
confirmation: NOT YET OBTAINED" note in the previous block.

## A. The owed pass ran and PASSED — then a spec-audit of the same state did not

The unit's first act (directive §3.4) was a fresh FOREGROUND gate-validator on the committed state
(work `879292a`, evidence `f9d2771`). **VERDICT: PASS**, with 7 MINOR reservations, re-derived from
its own commands: it reproduced the previously-failing 24GB-card/16GB-resident scenario and confirmed
a local pane is authorized with free VRAM; ran `SOW_VRAM_BUDGET_MB=1` against the real daemon and got
exit 0 with a usable picker; confirmed `None` vs `{}` reaches the renderer as `unknown`;
mutation-broke the receipt's gate-id legs two ways (dropping the exception's gate ⇒
`forged_refused_by:"unclassified"`, exit 1; every refusal reporting `host_enumeration` ⇒ exactly the
id-asserting legs red while the forged leg stayed green); and defeated nothing in the binary allowlist
across ~30 wrapper/rename/Win32/UNC/ADS forms. Suites confirmed at 1303 / 222 / 175.

A spec-audit of the same state returned **0 BLOCKING, 2 MAJOR, 13 MINOR, PROHIBITED DRIFT: NONE**.
Neither MAJOR was a fail-open; both were honesty defects and one was created by the fix commit itself.
Per §3.4 they were fixed in-unit rather than softened, and the reviews were RE-RUN against the fixed
tree. **Three review rounds ran inside this one unit; each found real defects in the previous round's
fix, and each round's severity fell.**

## B. Round 1 (committed state) — two MAJORs, fixed

1. **`vram_admission` conflated three structurally different refusals**, and the receipt leg named
   "a local pane that does not fit VRAM was refused" fired on the *budget-provenance* branch: the
   busy-host `SOW_VRAM_BUDGET_MB=1` squeeze FALSIFIED the budget, so nothing was measured and nothing
   about fit was proven. Cross-family id borrowing was closed at `.ticket`; intra-family was not.
   FIXED: `vram_budget_unestablished` split out; and the self-check's VRAM budgets are now COMPUTED
   from the host's own residency snapshot (new `--emit-residency` contract) so the FIT gate is what
   fires on any host — `squeezed = used + footprint − 1` stands above what is resident and falls short
   of what the target needs. The receipt now carries the real arithmetic
   (`free VRAM 4982MB of 9510MB, 4528MB in use`).
2. **A local option was `available:true` where no local pane could be authorized.** `pane_picker`
   hard-coded it — correct at 16B when residency was a display chip, false once 17B made the planner
   an authorization gate. FIXED: `local_admission_reason()` greys every local option with the reason.

## C. Round 2 (the fixed tree) — VERDICT: FAIL, four MAJORs, fixed

- **MAJOR-A — the greying was NARROWER than the gate.** `_authorize_local` also refuses every local
  pane when the `ollama` BINARY is absent (`runtime_absent`), reachable because the model list comes
  from the daemon over HTTP while the launch needs the CLI — a divergence `worker_pane_spawn`'s own
  refusal text already documented. The validator reproduced it. FIXED: both host-wide conditions are
  covered and each names itself; `test_the_greying_condition_matches_the_gate_in_both_directions`
  drives three host states through the picker AND the real `authorize_worker_pane` and requires
  agreement, so a rule that is too WIDE fails too.
- **MAJOR-B — the greying leg was a coin flip on daemon state** (falsifying a budget needs something
  resident, so on an idle host the leg silently did not run while `ok:true` was still emitted), and
  its fallback note cited the wrong test file. FIXED: the leg now forces the RUNTIME-ABSENT condition
  by removing only the resolved `ollama` binary's directory from PATH for its own children — the
  daemon stays reachable so the models are still enumerated — and is unconditional. The first attempt
  scrubbed the whole PATH, which also took `py` and yielded zero options; the guard
  `scrubbedPath.PATH === process.env.PATH` now makes a failed scrub loud.
- **spec-audit MAJOR-2 — the newly-split `vram_budget_unestablished` was itself reused** for the
  budget-vs-planner disclosure mismatch, a branch where the budget WAS established. FIXED: its own
  `vram_budget_mismatch`; and the undecidable-fit branch split out as `vram_footprint_unknown`.
- **spec-audit MAJOR-1 — `host_residency@1.0` was pinned in code with no `schemas/` file, no register
  row, and a consumer predicate that validated only the schema string** while the self-check did
  load-bearing arithmetic on unvalidated fields. FIXED where it matters: `isWellFormedResidency` now
  validates `budget.established`, `snapshot.used_vram_mb`, `snapshot.total_vram_mb` and every
  `models[]` entry. The missing FILE is **U104**, deferred to `phase-17d` with U90/U99/U101 — one unit
  should write all three schemas, not add a fourth code-side pin.

## D. Round 3 (the fixed tree again) — VERDICT: FAIL, three defects the fixes introduced, fixed

Round 3 confirmed all four round-2 MAJORs genuinely fixed and mutation-verified in both directions,
then found three defects introduced by those fixes:

- **The receipt's flagship field still named the OLD condition.**
  `local_greyed_when_budget_unestablished` read `true` in a run where the budget WAS established — a
  field asserting a condition the leg did not exercise, i.e. the MAJOR-B class recurring inside the
  MAJOR-B fix. FIXED: renamed `local_greyed_when_no_pane_can_be_authorized`, named for the PROPERTY
  rather than one of its two conditions.
- **The new conductor shell-metacharacter guard had NO test** — deleting either line left 230/230
  green, the exact class the same commit's new worker tests were written to close. FIXED: added and
  MUTATION-PROVEN (each line deleted individually ⇒ RED).
- **Two unused imports** (`QUEUED`, `ResidencyError`), orphaned by the de-duplication and the
  broadened `except`, violating the ruff-clean bar. FIXED; `pyflakes` is clean on every file this unit
  touched (`ruff` itself is still unavailable on this host — the substitution is recorded). The
  pre-existing unused `OLLAMA_LOCAL_ADAPTER` in `emit_worker_launch.py` was removed with them.
- Its MINORs are fixed too: `local_admission_reason`'s completeness claim now NAMES what it excludes
  and why (per-model fit, `role_deferred`, the structurally-unreachable mismatch); `pane_picker`'s
  docstrings describe both conditions; the U102 cross-reference is corrected; "one child" → "its own
  children".

## E. Other findings from rounds 1–3, fixed in this unit

`exe = resolved or "claude"` — a fail-OPEN under the module's own claim that the shell spawns exactly
what was gated — replaced by `_resolved_binary`, gate `binary_unresolved`. Frontier
`chrome.node_state:"ready"` on an authorization that has spawned nothing → `launch_authorized`
(invariant 3/27), and the stale fixture asserting `"ready"` corrected. `governor_released` was
documented "measured, never asserted" while the refusal branch compared a sentinel that can never be a
holder — now read from the MINTED identity, and a real post-acquire leak reports `false`. An ambiguous
option match silently bound the first candidate → refused. `_RESIDENCY_NODE_STATE` de-duplicated.
`except ResidencyError` widened to `except Exception` plus an `isinstance(tags, dict)` guard, after a
daemon answering `/api/tags` with a JSON ARRAY was shown to take the WHOLE picker down via
`AttributeError` — the BLOCKING-1b failure shape one exception class over. The shell-metacharacter
rule moved into the conductor source (ONE definition, re-exported) and APPLIED to the conductor
ticket, which had no such check at all; `>`/`<` added. A `refused_by` of `""` no longer passes as a
named gate. The `host_enumeration` refusal prose no longer tells the operator they could not have been
shown an option they were shown greyed. Comments implying `estimate:false` is reachable are corrected
— it is not; an env-supplied budget is a stated figure, not a GPU query. The self-check's determinism
and "one megabyte short" claims are scoped to what they deliver. `runEnumerator` gained per-child
`env`, so the check no longer mutates the shell's own environment to enumerate under different host
conditions.

## F. Evidence for this state

- Suites, fresh and foreground: **pytest 1326** (was 1303), **apps/desktop 231** (was 222),
  **terminal 175**. The round-3 validator independently reproduced 1326 / 230 / 175 at its boundary
  (231 includes the conductor metacharacter test added after it ran).
- D-P16-0 receipt `docs/evidence/receipts/PHASE17B_TICKET_SELFCHECK.json`, regenerated from the
  shipped code after every mutation was restored byte-identically: `ok:true`, four distinct gate ids
  across the fail-closed legs (`host_enumeration` forged, `vram_admission` fit, `worker_role`
  conductor, `host_enumeration` greyed selection), `in_use_after_release: 0`.
- Mutation proof that the receipt's green is EARNED, run in-Electron: reverting the greying rule ⇒
  `ok:false`, "the picker still offered local options as available (43 local …)"; making the fit gate
  report the budget gate's id ⇒ `ok:false`, `refused_by=vram_budget_unestablished` on exactly that
  leg. The round-3 validator independently reproduced both and added a third (breaking the PATH-scrub
  target ⇒ the guard fires).
- 18 further mutations across the Python and JS suites were run by the round-2/round-3 validators
  against the new guards; **every one went RED**, including both directions of the greying rule.

## G. Independent confirmation for THIS state — OWED, and why the unit closes as WIP

The round-3 FAIL's three findings were fixed AFTER that pass ran. They are mechanically verified here
— the conductor guard mutation-proven red on both lines, `pyflakes` clean, the renamed field present
and the old name absent in a regenerated `ok:true` receipt, full suites green — but NOT independently
reviewed. Three rounds have each found something in the previous round's fix, so declaring this closed
on the builder's own word is exactly the softening §3.4 forbids. `LOOP_STATE.next_step` is
`phase-17b.ticket-revalidate3`; the next unit's FIRST act is a fresh foreground gate-validator on this
committed state, and only on PASS does `.spawn` begin.

## H. Scope honesty, unchanged

Nothing in this unit spawns a session. U70's spawn half and U58's live legs are OPEN; the picker click
is still not wired to a ticket; operator finding F3 is not discharged. No live model call, no
credential (env NAMES only), no new provider. `docs/canonical/`, `mcp_server/` and `schemas/` are
untouched. D-LOOP-1: no session, lease, gateway or Electron process outlived the unit. A lease leaked
into the operator's real ledger by an early draft of `test_one_matching_option_still_binds` (which used
the default ledger) was found by the round-3 validator; the test now uses a temp ledger, the ledger was
cleared, and re-running the relevant suites leaves it empty.

---

# APPEND-ONLY BLOCK 3 — `phase-17b.ticket-revalidate3` (2026-07-26)

*The report above is never edited. This block records the OWED independent pass on the committed
state, its verdict, and what was fixed in response.*

## A. The owed pass ran. Gate-validator: PASS_WITH_RESERVATIONS. Spec-audit: 1 MAJOR.

Block 2 §G left one thing owed: the three round-3 findings were fixed after that round ran and had
never been independently reviewed. This unit's FIRST act, as §3.4 requires, was a fresh foreground
gate-validator on the committed state (HEAD `09f0fda`), with a concurrent spec-audit of the same tree.

**Gate-validator — PASS_WITH_RESERVATIONS.** It re-derived everything itself: suites reproduced at
1326 / 231 / 175; the receipt regenerated in-Electron with only run-identity fields differing from the
committed one (every gate, budget figure, argv, gate id and the flagship boolean byte-identical); and
all three round-3 fixes mutation-proven —

- **F2** (the conductor metacharacter guard): each of the two guard lines deleted individually took
  the JS suite to 230/1 on the same test. Independently covered.
- **F1** (the renamed flagship field): three separate attacks, receipt re-run in Electron each time —
  bogus scrub target ⇒ exit 1 with `local_greyed_leg: "not attempted"`; whole PATH scrubbed (so the
  picker returns nothing) ⇒ exit 1; and the decisive one, `local_admission_reason` forced to `None`
  ⇒ exit 1, "still offered local options as available (43 local, reason=null, ticket
  refused_by=runtime_absent)". The leg tests picker↔gate AGREEMENT, not merely the PATH scrub, and
  cannot pass vacuously in any of the three directions attacked.
- **F3**: `ruff` confirmed genuinely absent (no module, not on PATH); `pyflakes` clean over all 16
  Python files the unit touched — a wider set than the brief listed.

It also drove 41 forged tickets through the real shape contract with two positive controls, and
confirmed the freeze (0 drift over all 23 frozen entries), no remotes, names-only credentials, an
empty real lease ledger and no surviving Electron/gateway process.

**Spec-audit — PROHIBITED DRIFT: NONE; 0 BLOCKING, 1 MAJOR, 5 MINOR, 1 NIT.** §3.4 says fix, never
soften, so everything below was fixed in this unit.

## B. The MAJOR: a local authorization reported a node that had not been born as `ready`

`worker_pane_spawn` built the local ticket's `chrome.node_state` from the ResidencyPlanner decision.
When the selected model is already VRAM-resident the decision is `RESIDENT`, which the shared table
maps to **`ready`** — in the same ticket that carries `containment.supervisor_bound: false` and no
process at all (invariant 3/27). This is the identical defect fixed on the frontier branch as
spec-audit MINOR-1 in the previous unit.

It is reachable on the operator's own host, not theoretical: `enumerate_pane_picker` seeds every
`/api/ps` model as RESIDENT, so re-selecting a model the daemon is already serving is the normal case,
and the receipt for this very unit shows `running_vram_mb: 4528`.

**Why it survived three review rounds:** three artifacts asserted the local branch was already
honest — the constant's own comment, the test docstring `"The local branch was already honest and
must stay derived, not literal"`, and block 2 §E. Deriving is not the same as being true: what it
derived from is a fact about a MODEL. The scheduled-load case reads `loading`, which is harmless
enough to hide the resident case. And the receipt recorded `local_residency` but never `chrome`, so
its green could not see the field at all.

**Fixed:** both localities now report `launch_authorized`; `chrome.residency` keeps the residency
fact, where it is true. `_RESIDENCY_NODE_STATE` is no longer imported by `worker_pane_spawn`. Pinned
by two tests including the reachable resident case, mutation-proven RED on the pre-fix behaviour. The
blind spot the auditor named is closed too: the in-Electron receipt now records **and asserts**
`local_node_state` and `frontier_node_state`, each mutation-proven — reintroducing the defect on
either branch turns the receipt RED (exit 1) on exactly that leg, naming the state and the invariant.

## C. The other findings, all fixed

- **Validator MINOR-2 — the basename normalisation run in REVERSE.** `executableBasename` strips an
  NTFS alternate-data-stream suffix and trailing space/dot padding so a disguised `claude` is caught;
  the validator showed the same stripping laundered the inverse: `…/ollama.exe:claude.exe` normalised
  to `ollama` and was ACCEPTED as a lease-free, I-X3-UNCOUNTED local ticket, while Win32 executes the
  STREAM. `FRONTIER_TOKENS` never saw it — that rule only scans argv, and `:` is not one of its
  boundary characters. Fixed: streams and padding are now refused OUTRIGHT on `launch.executable`
  (the field that decides what runs) rather than normalised away; stripping stays for COMPARISON,
  where catching a disguise is the point. Each half of the rule is mutation-proven independently RED,
  and the rule is stated as the VALID shape and negated — written as a positive `…:` match the
  optional drive group backtracks out of the way and `C:/bin/ollama.exe` refuses itself, which is
  exactly what the first attempt did and what its test caught. Deliberately NOT refused: a directory
  component named `claude` on a path whose basename must still be `ollama` cannot make a frontier CLI
  run, so refusing it would buy nothing and cost an honest host an opaque refusal (the U103 class).
- **Spec-audit MINOR-1 — a bare-binary fallback in the local argv builder.**
  `adapters/local/ollama_session` did `exe = executable.strip() or "ollama"` — the
  `resolved or "claude"` shape the `binary_unresolved` gate exists to refuse. A blank executable
  became a bare name the shell PATH-searches at spawn, so what runs would be decided AFTER the gate
  ran, and `ollama` is precisely the basename the shell's allowlist accepts. Unreachable today only
  because its one caller resolves first; a fail-open defended solely by its caller is the coupling
  that gate refuses. Now raises. The parameter default stays a stated choice; a blank passed in is a
  producer fault.
- **Spec-audit NIT — two fields of one ticket disagreeing.** `containment.requires` asked the shell
  for `residency_release_on_session_exit (U96)`, a release that by this build's own design cannot
  happen (the reservation lives in the emitter's in-process planner and dies with it, as U96 item 3
  and the enumerator's HONEST LIMITS both say). The local branch now lists nothing to release and
  states the lifetime explicitly instead.
- **Spec-audit MINOR-4 — the receipt's `scope_note` claimed more determinism than it delivers.**
  "if the resident set changes mid-run, every leg throws and the receipt is RED — never a false
  green" is not true of every leg: the authorized leg's generous budget can stay green if the
  resident set SHRINKS. Replaced with what is actually established and sufficient — no leg can go
  green on a gate other than its own, because each asserts its gate id and the fit leg asserts the
  gate's own arithmetic.

## D. Recorded, not fixed — U105–U108

- **U105** (spec-audit MINOR-2): the credential scrub list is measured in the PYTHON EMITTER's
  environment and applied to the ELECTRON SHELL's. Sound only while the two hold the same variables —
  and 17B itself made divergence reachable by adding per-child `opts.env`. Fail-open direction; no
  product path exercises it today. Owner `.spawn`, where the shell does the spawn and the scrub set
  should become the union of both sides' measurements. §2.2 is not violated: only NAMES ever cross.
- **U106** (MINOR-5): `ADAPTER_EXECUTABLE` is a second source of truth for each adapter's binary
  name, owned Python-side. Deliberately not fixed by letting the ticket declare its own expected
  binary — disbelieving the ticket about itself is the whole point of the contract. Travels with the
  U104 schema unit.
- **U107** (MINOR-3): the headless dispatcher still calls `request_load` unguarded and can act on a
  displacement the worker path refuses. Latent (no product caller). Carries an append-only correction
  to U96, whose "this build refuses to displace ANYTHING" is true only of `worker_pane_spawn`, and
  records that the two paths now deliberately differ on `node_state` as well.
- **U108** (validator MINOR-3): `CLAUDE.md` documents `python -m pytest tests/ -q`, which on this
  host fails with 71 collection errors (default `python` is 3.14.6; only `py -3.12` runs the suite),
  and `terminal/` has no `package.json` so `npm test` there is ENOENT — that suite is `node --test`.
  Not fixed by editing `CLAUDE.md`: this loop does not rewrite the operator's instruction file to
  match the machine. Flagged for the final report as a one-line operator correction.

## E. Correction to block 2 §F (append-only, per the validator's MINOR-1)

Block 2 §F says the receipt shows *"four distinct gate ids across the fail-closed legs
(`host_enumeration` forged, `vram_admission` fit, `worker_role` conductor, `host_enumeration` greyed
selection)"*. There are four **legs** but only **three distinct ids** — the parenthetical contradicts
the sentence it explains, since the forged leg and the greyed-selection leg share `host_enumeration`.
Read it as "four fail-closed legs across three distinct gate ids". The consequence is real: a defect
making every refusal report `host_enumeration` would leave two of the four legs green, so those two
legs do not discriminate between each other. This is the same over-claim class the unit spent three
rounds removing from the code, surviving in the prose. The same sentence was copied into
`LOOP_STATE.notes` for iteration 77 and is corrected in this iteration's note.

## F. Evidence for this state

- Suites, fresh foreground: **pytest 1328** (was 1326: +2 honesty tests replacing 1, +1 argv-builder
  test), **apps/desktop 232** (was 231), **terminal 175**.
- `pyflakes` clean on every file this unit touched. `ruff` remains unavailable on this host — the
  substitution is recorded and was independently confirmed genuine by the validator.
- D-P16-0 receipt regenerated from the shipped code after every mutation was restored: `ok:true`,
  `local_node_state` and `frontier_node_state` both `launch_authorized`, `in_use_after_release: 0`.
- Mutations run this unit, every one RED and every one restored: local `node_state` → `ready` (2 tests
  + receipt exit 1); frontier `node_state` → `ready` (receipt exit 1); the executable guard removed;
  the stream half alone removed; the padding half alone removed.

## G. Why `.ticket` closes here and `.spawn` is next

The owed independent pass ran and PASSED. The fixes in §B–§C were made after it, and are verified by
this unit's own mutations — the same position block 2 §G refused to close on. The difference is that
`.ticket` is a WIP checkpoint inside 17B, not a gate: `gate/phase-17b` closes at `.close`, with a
mandatory gate-validator over the whole track, and these fixes are inside its scope. Continuing to
spend whole units re-reviewing a checkpoint that has now passed its owed pass, while U70's spawn half
and U58's live legs stay untouched, would be its own kind of dishonesty about where the risk is.
`next_step` is `phase-17b.spawn`; its first act carries these five fixes into its review.

## H. Scope honesty, unchanged

Nothing in this unit spawns a session. U70's spawn half and U58's live legs are OPEN; the picker click
is still not wired to a ticket; operator finding F3 is not discharged. No live model call, no
credential (env NAMES only), no new provider. `docs/canonical/`, `mcp_server/` and `schemas/` are
untouched. D-LOOP-1: no session, lease, gateway or Electron process outlived the unit.
