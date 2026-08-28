# PHASE 17A `.lease` — EVIDENCE REPORT

**Work unit:** `phase-17a.lease` (first named sub-step of directive §16 track **17A — live conductor
session in pane 1**, HIGH-STAKES gate). **Not a gate close:** no tag is cut by this unit;
`gate/phase-17a` closes at `.close` after `.pty` and `.roundtrip`, with the mandatory
gate-validator on the whole track.
**Date:** 2026-07-25 · **Loop iteration:** 71 · **Basis:** OP-11 (directive §16), OP-9 (live terms),
OP-6 (I-X3 = 2/subscription).
**Work commit:** see the register commit that carries this report.

---

## 1. Why this sub-step exists (the defect it is prerequisite to)

Operator first-use finding **F3**: conductor pane 1 reads `awaiting_live_conductor` — a black pane;
typing gets no answer. That state was *honest*: `tools/live/emit_conductor_spawn.py` runs the full
live-gate chain but deliberately **defers** the interactive `claude` drive and **tears its I-X3
terminal down before emitting**. The shell therefore had gates but no session.

The blocker underneath is a counting one. `SubscriptionGovernor` is **in-process**: every bounded
emitter in this build constructs one, acquires, and releases at teardown (D-LOOP-1). That was correct
while nothing live outlived an emitter. 17A requires the opposite — a real interactive `claude`
session owned by the long-lived Electron process, authorized by a short-lived Python emitter. With an
in-process-only count the shell could hold two sessions while every emitter reported `0/2`:
**I-X3 would be decorative.** Directive §16 17A explicitly requires the session to persist
("the OPERATOR's session persists by design").

So `.lease` builds the two prerequisites and nothing operator-visible:

1. a **durable, cross-process I-X3 lease ledger**, and
2. a **governed launch ticket** — an authorization the shell can *execute*, carrying a lease it holds.

---

## 2. What was built

| Artifact | Role |
|---|---|
| `node_runtime/supervisor/terminal_lease.py` | Durable file-backed lease ledger (`.sovereign_store/leases/terminal_leases.json`, gitignored). Counts; **grants nothing**. Allowance passed in from the enforced `LiveAuthorization`; OP-6 `MAX_ALLOWANCE=2` re-asserted as defense in depth. Dead-holder reaping, atomic replace, ownership-based lock. |
| `tools/live/emit_conductor_launch.py` | `--emit-conductor-launch --holder-pid <pid>` → `conductor_launch_ticket@1.0`; `--release-lease`; `--emit-lease-status`. Runs the **identical** gate chain 16C gated via `spawn_conductor_pane`, then takes the durable lease for the shell. |
| `apps/desktop/conductor/launch-source.js` | Bounded one-shot JS read-source + strict shape validation + `scrubbedLaunchEnv`. Can only **refuse**, never grant. |
| `apps/desktop/selfcheck/conductor-launch-selfcheck.js` | D-P16-0 in-Electron receipt (wired into `main.js` + `selfcheck/run.js` as kind `conductor-launch`). |
| Tests | `tests/unit/test_terminal_lease.py` (17), `tests/unit/test_emit_conductor_launch.py` (16), `apps/desktop/test/conductor-launch-source.test.js` (13, incl. a real-emitter integration test). |

**Ticket shape (what the shell will execute at `.pty`):** interactive `argv` (`claude --model
fable-5` — never `-p`/`--print`/`--output-format`), `env_scrub_names` (**names only, never values** —
§2.2), the CONDUCTOR `chrome` + honest `selection_record`, the governed `identity`
(`node_id` + `permission_profile_id` + `subscription_ref` — the shell cannot invent one), an explicit
`containment` block stating the ticket is an **authorization, not containment**, and a **held**
durable `lease`.

---

## 3. Exit criteria for this sub-step, with real command output

All commands run on the Windows host in this turn (foreground; D-LOOP-2 print-mode).

| # | Criterion | Result |
|---|---|---|
| 1 | Ticket produced ONLY through the existing gate chain (profile/live-auth, provider-live, R8 §6 terms, `claude` presence, I-X3); no new bypass, no authorization logic in JS | **PASS** — validator-confirmed by code path + real emission |
| 2 | argv INTERACTIVE, no headless flag (OP-8 §13.1) | **PASS** — real ticket `["claude","--model","fable-5"], one_shot:false` |
| 3 | §2.2 — names only, no values, no env map in the ticket | **PASS** — validator read the real ticket: 5 `CLAUDE_CODE_*` names, no `name=value`, no `env` key |
| 4 | Durable lease HELD at emit and visible to a **separate** process; emitter's own in-process count released | **PASS** — in-Electron receipt `lease_in_use:1`, `lease_visible_cross_process:true`, `emitter_governor_released:true` |
| 5 | Fail-closed: over-allowance / unauthorized config / unconfirmed terms / absent CLI / corrupt ledger ⇒ refusal with reason, **no argv, no leaked lease**; corrupt ledger never silently reset | **PASS** — validator corrupted the *real* ledger and ran the *real* CLI: `LeaseLedgerCorrupt` refusal, file byte-identical afterwards |
| 6 | OP-6 hard cap re-asserted (allowance 3 refused) | **PASS** — validator probe: `allowance=2 GRANTED / 3 REFUSED / 99 REFUSED` |
| 7 | Dead-holder lease reaped, deterministically (injected liveness, no wall clock) | **PASS** |
| 8 | D-LOOP-1 — no live terminal left behind; no `claude` process spawned by this unit | **PASS** — ledger `"leases": []` now; validator confirmed the host's two `claude.exe` predate this session by 21 h; the only child this code spawns is `py` |
| 9 | D-P16-0 in-Electron receipt, `ok:true`, load-bearing | **PASS** — `docs/evidence/receipts/PHASE17A_LAUNCH_TICKET_SELFCHECK.json`; validator proved load-bearingness by two independent mutations (`one_shot:true` ⇒ FAIL exit 1; `build_lease_status` returning `{}` ⇒ FAIL exit 1), both reverted |
| 10 | Suites green | **PASS** — `py -3.12 -m pytest tests/ -q` → **1142 passed** (211 s); `apps/desktop` `npm test` → **171 pass / 0 fail**; `node --test terminal/test/*.test.js` → **173 pass / 0 fail** |
| 11 | Anti-overfit | **PASS** with one tautology found and **removed** (see §5, R5/F13) |

**Independent reviews (both run in the foreground this turn, per D-LOOP-2):**
- **gate-validator (isolated context): VERDICT PASS** for `phase-17a.lease`, with 5 reservations (R1–R5). It re-ran the full 1136-test suite in its own sandbox, mutated the code twice to prove the receipt fails when the wiring breaks, corrupted the real ledger end-to-end, and restored the workspace (emitter sha256 identical pre/post).
- **spec-auditor: no PROHIBITED DRIFT**, 18 findings (F1–F18). Explicit ruling on the invariant-30 question: *the durable ledger is **not** an invented governance layer* — it grants nothing, adds no decision step, and enforces an invariant whose in-process enforcement is provably decorative once a session outlives its emitter. It is the minimal mechanism.

---

## 4. Review findings FIXED in this unit (re-verified after the fix)

| Ref | Finding | Fix |
|---|---|---|
| R2 / F5 | `governor_released` computed as "governor empty", but the governor is deliberately **seeded** with other processes' durable leases ⇒ a false leak report, and a false FAIL of the D-P16-0 receipt the moment 17B introduces worker leases | Predicate is now "**our node** is not holding an in-process terminal" (`_governor_holders`). Regression test: `test_governor_released_is_about_OUR_node_not_an_empty_governor` |
| R3 / F3 | Windows `pid_is_alive` treated `OpenProcess`→NULL as dead, conflating **ACCESS_DENIED** (an elevated/other-user process that EXISTS) with "gone" ⇒ fail-**open** reap of a live holder's lease, minting a terminal past the cap. Untested (`pragma: no cover`) on the only platform it runs | Rule extracted to `win_pid_alive(...)` with injected `ctypes` calls and **tested**: `ERROR_ACCESS_DENIED ⇒ alive`, `ERROR_INVALID_PARAMETER ⇒ gone`, handle always closed |
| F2 | The in-Electron check and the JS live test ran against the operator's **real** ledger with the production conductor node id ⇒ could adopt-and-release a lease the operator's own running conductor holds (uncounting a live session), and asserted a globally-empty count (a false FAIL on a legitimately busy host) | `SOW_TERMINAL_LEASE_LEDGER` scratch-ledger override; both the self-check and the live test now use a per-pid scratch file, restore the env, and delete it. Test: `test_ledger_path_honors_the_scratch_override` |
| F8 | Stale-lock break was **age-only**: two writers could each unlink the other's fresh lock and both enter a read-modify-write ⇒ a silently lost acquire (an uncounted terminal). No lock test existed | Break is now **ownership-based** — a lock is stolen only when its recorded owner pid is dead; age is the fallback for an unwritten pid. Tests: `test_a_live_holders_lock_is_never_broken`, `test_a_dead_holders_lock_is_broken` |
| F6 | The ticket carried authorization but no containment, while `chrome.governed:true` could be read as "this session is sandboxed" | Ticket now carries the governed `identity` **and** an explicit `containment` block (`supervisor_bound:false`, `owed_to:"17A .pty"`). The self-check FAILS if that disclosure is missing |
| F9 | A refusal raised by the **later** I-X3 gate emitted `cli_present:false`, misdiagnosing the refusal for the operator | Gates are OBSERVED up front (`_detect_cli()`); duplicated `provider_live` key removed. Test: `test_refusal_reports_the_gate_that_actually_failed` |
| F10 | `_refusal_ticket` **asserted** `governor_released:true` in prose | Now measured after teardown, on both paths |
| F16 | `build_lease_status` could print `allowance:0` beside a non-zero `in_use` with no explanation | Documented as the intended, operator-relevant signal (terminals held under a since-withdrawn authorization); never presented as a grant |
| R5 / F13 | `assert all(is_credential_env_key(n) for n in names)` — asserted with the function that generated the list; and receipt fields recorded source-constants as if verified | Tautological assertion removed; `scope_note` now states which receipt fields are shape assertions, not behavioral proof |
| F15 | Module docstring claimed "each mode prints one JSON line and exits 0" (contradicted by exit 2 / escaping `ValueError`) | Docstring corrected |

---

## 5. Limitations, substitutions and OWED items — recorded, not implied away

**Scope honesty (validator-flagged, restated here so no reader over-reads this report): this unit
delivers NOTHING operator-visible. F3 is NOT addressed.** `apps/desktop/main.js` gained only the
self-check dispatch; no product path requests a ticket, spawns the argv into pane 1's ConPTY, or
releases the lease on quit. Pane 1 still reads `awaiting_live_conductor` in the live shell. The black
pane ends at `.pty` / `.roundtrip`.

**Substitutions (directive §6):** the emitter is a bounded one-shot `py -3.12` read-source, not the
WS-IPC channel — identical to the 16B picker, the 16C feeds and the 16D status bar, and recorded for
the same reason (swapping the shell's gateway surface would displace the supervisor liveness path).
`ruff` is **not installed on this host** (`which ruff` → not found; `py -3.12 -m ruff` → no module), so
the CLAUDE.md ruff-clean bar could not be machine-checked this unit; style was held by hand against
the surrounding modules. Recorded, not claimed.

**OWED to `.pty` (each opened in the unresolved-issue register as U75–U78):**
- **U75 (F1)** — the lease is keyed to `(subscription_ref, node_id)` and the conductor node id is a
  constant, so two real sessions for pane 1 would share **one** counted terminal. `.pty` must key the
  lease to the ConPTY session identity. Latent today (nothing spawns yet); load-bearing the moment
  `.pty` lands.
- **U76 (F4)** — three `subscription_ref` spellings exist for one real subscription (`claude-sub`
  here and in 16C, `sub-claude_code` in the status-bar feed, `sub-anthropic` in the 15D smokes). The
  cap is enforced per ref, and the always-visible status bar will read `0/2` against a genuinely held
  lease until `.pty` sources the bar from this ledger.
- **U77 (R1)** — a ticket whose lease is acquired but whose delivery to the shell then fails (JS
  shape refusal, 25 s timeout) leaves an **orphan lease** consuming 1 of 2 until the holder dies or
  the same node re-acquires it (idempotent re-adoption). Transient, not permanent — but `.pty` must
  release on parse failure or move the acquire behind a shell acknowledgement.
- **U78 (F6/F7/F11/F14)** — containment binding (supervisor session registration, workspace binding,
  job-object/ACL per invariant 29) is not established by a ticket; the §2.2 scrub is name-resolved in
  the emitter and applied in the shell, correct only because the child inherits the env (the ticket
  should also carry the *rule*, not just resolved names); `operator_terms_confirmed=True` is a
  hardcoded literal riding recorded OP-9 with no revocable artifact (unlike live-operation, which is
  fenced by a file the operator can delete); and `--release-lease` performs no ownership check, so
  the durable cap binds cooperating local callers, not a hostile one.
- **F17/F18 (register notes, not defects)** — the ledger keeps current state only, no append-only
  lease-event history; and `terminal_lease_ledger@1.0` is persisted state with no file in `schemas/`
  (consistent with the existing feed emitters, but closer to the CLAUDE.md single-source-of-truth
  rule than a transient feed is).

**Prohibitions honored:** no push/remote/publication; no credential read, stored or transmitted (the
ticket carries env var **names**); no purchase; nothing outside the repo root; `docs/canonical/`
untouched; `config/live_operation.json` not committed; **no live model call was made by this unit**.

---

## 6. Verdict

`phase-17a.lease` — **PASS** (gate-validator confirmed, independently; spec-auditor: no prohibited
drift). Ten review findings fixed in-unit and re-verified; four owed items opened as U75–U78 and
carried explicitly into `.pty`. Next work unit: **`phase-17a.pty`** — the shell executes this ticket
in pane 1's ConPTY through the supervised session path, binds containment, holds the lease for the
session's life and releases it on exit/quit, and ends `awaiting_live_conductor`.
