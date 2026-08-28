# Phase 18E `.live.electron.wiring` — checkpoint (NOT a gate)

**Sub-step:** `phase-18e.live.electron.wiring` · **Date:** 2026-08-02 · **Status:** DONE
**`gate/phase-18e` does not exist and this unit did not create it.** `product/multi-frontier-v2`
is not applied. This document is a sub-step checkpoint in the shape the 18E `.hardening` and
`.live.shape` checkpoints established; the phase evidence report lands at `.close`.

**Authorization:** OP-12.2 (operator, 2026-08-02), directive §17.2(1) — the live acceptance leg
requires "a supervised ConPTY pane **as a registered Sovereign node**". This unit builds that
registration. It makes **no live provider call**, and none was possible in it.

---

## 1. What the unit is, and why it was owed

18D wired an OP-12 provider session into a Sovereign node record for the one-shot
`GovernedProbeSession` and for nothing else. A picker selection that opens a real `grok` or `agy`
worker **pane** on the operator's host took a durable I-X3 terminal, minted a Python-side node
identity, and rendered a governed badge — and wrote no node record at all.

Invariant 2 says every terminal is a Sovereign node. The pane path was the terminal with no node,
and directive §17.2(1) asks the live acceptance leg to evidence exactly the thing that did not
exist. So the leg could not be run honestly until this was built.

## 2. The design: three facts, written when each becomes true

| Moment | Who writes it | What the record says | Why not earlier or later |
|---|---|---|---|
| **ticket** (`build_worker_launch_ticket`) | the Python emitter, after the gate chain passes and the durable terminal is acquired | `node@1.1`, `state: SPAWNING` | Authorized, not yet born. At this moment no process exists, so any stronger state would assert something nobody had seen. |
| **spawn** (`--record-pane-spawned`) | the shell, immediately after its supervised ConPTY spawn returns a pid | `transition → READY`, `pid` a structured field on the log | Only the shell can know the process exists. The pid IS the attestation, so it is checked (positive **and** live), not merely recorded. |
| **release** (`--release-session`) | the shell, when the session ends or on quit | `transition → TERMINATED` + `exit` | D-LOOP-1 in the one place an auditor would look. Deliberately NOT conditional on the lease half — a lease already reaped by dead-holder reaping would otherwise leave the node reading `SPAWNING` forever. |

Steps 2 and 3 run in **different processes** from step 1 (each emitter invocation is its own
`py -3.12`), so `NodeRegistry.rehydrate` restores one record from the durable log into the live
view, writing nothing. The module always said "the log is the record, the dict is a cache of it";
nothing could act on it until now.

**Scope, code-pinned and stated in every payload:** `grok_build` and `google_antigravity` only,
derived from the module that can actually build a record (`REGISTRABLE_PROVIDERS`, from the facts
table — never re-spelled). `claude_code` / `openai_codex_cli` panes are reported
`registered:false` with the reason and **U313**, because registering them would change behaviour
OP-12's own supersession list names as untouchable. `registrar` is a REQUIRED keyword — whether a
session becomes a Sovereign node is the caller's fact, exactly as the profile and the operator's
terms determination are (U283/U292(a)); `None` means exactly no record, reported with its reason.

## 3. Fences, each with a test and a mutation row

| Fence | Refuses | Mutation |
|---|---|---|
| type check on the authorization | a duck-typed object asserting the supervisor's I-C1 attestation | M8 |
| I-X3 evidence | a pane session with no lease / not subscription-governed | (test) |
| governance claim | chrome that does not claim `governed` | (test) |
| provider scope | any adapter this module has no record facts for — **before the log is opened** | M9 / (test) |
| record shape | a record that cannot be traced to its session, workspace or permission profile — **before the log is opened** (validator MINOR-5) | (test) |
| **session binding** | a post-ticket act on a record that is not this session's | M14, M15 |
| **pid liveness** | a fabricated or dead pid recorded as `READY` | M7, M13 |
| **spawn-row fence** | `rehydrate` of a record the log does not carry | M16 |
| vocabulary | `rehydrate` of an adapter no node schema version admits | M5 |
| duplicate | `rehydrate` over a live key | M6 |
| **stale incarnation** | a prior incarnation under a LIVE pid (and reaps one under a dead pid) | M17, M18 |
| refusal ⇒ session refused | a registrar refusal hands the durable terminal back | M2 |
| refusal ⇒ record closed | a governance refusal AFTER the record was written closes it and reports it | M20 |
| lock lifetime | the node log's cross-process lock released on every ticket exit path | M3 |
| arg parsing | a flag-shaped value on **every** mode that takes one | M21 |
| shell: never fatal | a failed attestation never tears down a live governed session | M11 |
| shell: right node | attests with the PYTHON-minted node id + the session key | M12 |
| shell: right pane | attests ONLY when the ticket says a record exists | M22 |

## 4. What the reviewers found, and what changed

Both mandatory reviewers ran **foreground, in-turn, concurrently** (D-LOOP-2) on work commit
`af8daba`. The gate-validator returned **PASS_WITH_RESERVATIONS** after reproducing all four suite
numbers itself; the spec-auditor returned **PROHIBITED DRIFT: NONE, no invariant violated**.

**They converged independently on the same MAJOR** (validator MAJOR-1 / auditor MAJOR-2), and it
was real: `attest_spawned` and `close_session_record` took only the node KEY and acted on "the
latest record for this pane". Pane ids are reused across sessions, so a record left open by a
crashed shell could be attested `READY` with an unrelated process's pid, and a late release for
session A could write `TERMINATED` against session B's still-live record — permanently, on an
append-only log. The binding already existed (the record's uuid is derived from
`node_key#session_id`) and was simply never compared. It is a check now (**U315**).

The auditor's other MAJOR: the pid was checked for `> 0` while the docstring claimed to "refuse to
record READY for a process nobody observed" — the stronger claim with the weaker fence. Liveness is
checked now, through the repo's one implementation of that question; what liveness still cannot
establish is recorded as **U314** rather than implied away.

Every other finding is fixed or recorded, none dropped:

| Finding | Disposition |
|---|---|
| validator MEDIUM-1 — `node_registration` produced and never consumed | FIXED: the shell now branches on it, which is also what closes the MAJOR |
| validator MEDIUM-2 — a failed close is never retried or reaped | PARTIALLY FIXED (dead-incarnation reap on the next registration) + **U316** for the rest |
| validator MEDIUM-3 / auditor MEDIUM-6 — lock contention refuses a legitimate pane | FIXED: bounded ~2 s wait before refusing, and the refusal now names the remedy |
| auditor MEDIUM-3 — `SOW_NODE_EVENT_LOG` repeats the 18D `real_switch` shape | FIXED: the ticket, the attestation and the release ALL name the log path in force (M19) |
| auditor MEDIUM-4 — no stale-record reconciliation across a crash | FIXED for the pane's next launch (M17/M18); the window is **U316** |
| validator MINOR-1 / auditor MEDIUM-5 — a test named for the local branch exercised the frontier one | FIXED: a real `ollama_local` ticket test; the local branch's own reason is now covered |
| validator MINOR-2 — the flag-shaped-value fix landed in one mode, not its siblings | FIXED: one `_value_after` used by every mode (M21) |
| validator MINOR-3 / auditor MINOR-7 — `_refusal()` asserted "no record exists" | FIXED: passed in and measured; a record written before a later refusal is CLOSED (M20) |
| validator MINOR-5 — a malformed authorization created an empty log | FIXED: the shape check runs before the log is opened |
| auditor MINOR-8 — `rehydrate`'s provenance was a claim about callers | FIXED: the log must carry a `spawn` row (M16) |
| auditor MINOR-9 — `adopt_from_log` skipped what it could not read | FIXED: unparseable line or unknown state ⇒ `None`, fail closed |
| auditor MINOR-10 — `close()` on an injected log could produce a second writer | FIXED: a closed registrar refuses to reopen |
| auditor MINOR-11 — a 90 s blocking await after the pane is already live | FIXED: its own 20 s bound |
| auditor NIT-13 / validator NIT-1 — `transition(**data)` widened the log's write surface | FIXED: `pid: int \| None` and nothing else |
| validator NIT-3 — a mechanical edit artefact in two test call sites | FIXED |
| validator MINOR-4 — `U313` was a dangling citation at HEAD | FIXED: the row exists (this commit) |
| validator MINOR-6 — `docs/loop/logs/gate18c_authority.py` is an unmigrated caller | RECORDED, not changed: an archival gate-18C log script under `docs/loop/logs/`, run by nothing, and rewriting a historical artifact to keep it importable is not a repair |
| auditor NIT-12 — record `class` is adapter-derived, `permission_profile_id` role-derived | RECORDED: consistent only because frontier coding panes are refused today; noted for whenever that deferral lifts |

## 5. Verification (all foreground, in this turn)

| Check | Result |
|---|---|
| `py -3.12 -m pytest tests/ -q` | **2208 passed / 1 skipped** (389 s) |
| `apps/desktop` `npm test` | **758 pass / 0 fail** |
| `terminal/test` `node --test *.test.js` | **216 pass** |
| `py -3.12 tools/mutation/_op18e_electron_wiring_mutations.py` | **22/22 RED, byte-identical restores** |
| `py -3.12 -m pyflakes` (touched files) | clean |
| operator's durable node log | **byte-unchanged**: 15 rows, all `probe-*` from the operator's own live probes, no `worker-pane-*`, no lock file left behind |
| live provider calls | **zero**, and none possible in this unit |

Two mutation rows went GREEN on the first remediation run and that was informative rather than
inconvenient: the new fences caught M5 and M7 before the fences those rows target could, so both
tests were narrowed to assert the SPECIFIC refusal. A row that passes because a different guard
fired is a row that has stopped measuring its own guard.

## 6. Not established, and not claimed

* **No live Grok or Antigravity call has been made by this build**, no pane has been opened for
  either provider, no OP-12 terminal has been leased on the operator's durable ledger, and **no
  pane node record exists on the operator's durable node log**. Every record measured here is on a
  `tmp_path` log. That leg is the next unit's — §17.2(1)'s in-Electron acceptance.
* **No in-Electron receipt exists for this wiring.** D-P16-0 binds every shell change to a check
  that runs inside the packaged Electron runtime; this unit's shell change (the attestation call
  site) is covered by headless tests and mutations only. The in-Electron evidence lands with the
  acceptance leg, which is the run that will exercise it for real.
* The OP-6 providers' panes still have no node record (**U313**); parentage is not established by
  any attestation (**U314**); a failed close is not retried (**U316**).
* Two live exchanges remain the directive's budget for the next unit — **one per provider**,
  unchanged, and the U312 overrun stays the operator's to rule on.

## 7. Next

`phase-18e.live.electron` — §17.2(1)'s per-provider LIVE in-Electron acceptance leg: real picker
selection → supervised ConPTY pane as a registered Sovereign node (this wiring, now exercised on
the operator's durable log) → verified exact provider+model → ONE harmless prompt → live response →
teardown → lease 0 → credential-sentinel scan of every sink that now exists (PTY transcript and
child env included) → durable-ledger and node-ledger consistency. Then `.close`.

**Standing warning carried forward from `.live.shape`:** Grok's headless `-p` run exits zero having
said nothing (`stopReason: cancelled`, U310). An interactive ConPTY pane is a genuinely different
channel and may not share the defect — attempt it on its own evidence, and never report the same
cancellation wearing different clothes as a provider success.
