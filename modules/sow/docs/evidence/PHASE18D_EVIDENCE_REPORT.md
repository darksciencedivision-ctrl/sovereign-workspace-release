# PHASE 18D — EVIDENCE REPORT

**Track:** OP-12.1 18D — U227 resolved by successor schema, both OP-12 providers registered as
Sovereign nodes, and the 18C legs that were skipped **on the registration fence** completed.
**High-stakes gate** (gate-validator + spec-auditor mandatory).
**Authorization:** OP-12.1 (operator, 2026-08-01), `AUTONOMOUS_BUILD_DIRECTIVE.md` §17.1.
**Verdict:** **PASSED.** The vocabulary amendment is executed, the registration is WIRED and
measured through the product path, and the live legs whose entry conditions are the operator's stay
**skip-with-record** — the operator's `config/live_operation.json` still cites OP-6 and denies both
providers.

| | |
|---|---|
| Sub-steps | `.amendment` (the successor schema + additive freeze extension + derived vocabulary) → `.close` (this) |
| `.amendment` commits | work `c40c1e3`, remediation `1751384`, evidence/registers `75f7751`; findings in `docs/evidence/PHASE18D_AMENDMENT_CHECKPOINT.md` |
| `.close` work commits | `2a351e7` — *"the vocabulary was open and nothing wrote to it, so now something does"*; `03d78db` (a verdict defect the first in-Electron run found); `cdcd45c` — the review remediation |
| Receipt | `docs/evidence/receipts/PHASE18D_REGISTRATION_SELFCHECK.json` (in-Electron, D-P16-0), `ok:true`, `source.commit cdcd45c` |
| Register rows | U297–U302; decision rows D-P18-11, D-P18-12 |

---

## 1. What OP-12.1 asked for, and what this unit did

§17.1 sequences the work after 18C's skip-with-record as **`phase-18d`**: execute the amendment,
**register both providers as Sovereign nodes**, run every 18C leg previously skipped on the
registration fence (entry conditions unchanged), both mandatory reviewers, the evidence report, and
a successor tag only.

`.amendment` did the first part and deliberately stopped: its own evidence says *"the vocabulary is
open; nothing is wired to write into it."* `.close` is the wiring:

`node_runtime/supervisor/provider_node_registration.py` turns a `GovernedProbeSession` into a
`node@1.1` record — built from the session and from the adapter that would run (capabilities are the
adapters' own constants, never re-declared), validated by the **real jsonschema validator against
the real file on disk**, registered through the **real `NodeRegistry`** onto the **real hash-chained
append-only log** under `.sovereign_store/nodes/`, and **closed** (`spawn` → `transition` → `exit`)
when the session ends. `registrar` is a required keyword of `governed_probe_session` — the third
input, beside `profile_loader` and `operator_terms_confirmed`, whose answer is the caller's and not
the module's — and `node_registered` is now a measurement rather than the hardcoded `False` it was
through 18C. The product call site (`frontier_provider_recon._open_probe_session`) passes the
durable registrar.

**Registration is step 7 and is not a gate.** `node@1.1`'s own description says so and the module
repeats it: a record describes a session the live switch, the operator's terms determination, CLI
presence and the I-X3 lease have *already* permitted. A refused registration **refuses the session**
and the lease comes back — a leased, supervised terminal with no node record is exactly the
naked-but-leased session the chain exists to prevent.

## 2. The measurement — `PHASE18D_REGISTRATION_SELFCHECK.json`, in the packaged shell

`node selfcheck/run.js op18d-registration` on this Windows host: `ok:true`,
`source.commit cdcd45c` (**== HEAD at the time of the run**), `tracked_product_tree_clean:true`,
`unexpected_untracked_product_files: []`.

| Leg | Fact | Measured value |
|---|---|---|
| vocabulary | read from the real `schemas/` directory | `grok_build → node@1.1`, `google_antigravity → node@1.1`, `claude_code → node@1.0`, `kimi_k3 → null` |
| registration | both providers, through the product path | `registered:true`, record `validated_against node@1.1`, admitting version `node@1.1` |
| the log | the record IS the log | `chain_ok:true`, `kinds ["spawn","transition","exit"]`, `path_is_scratch:true`, `lock_released:true` |
| D-LOOP-1 | the record does not outlive the session | `node_state_after: TERMINATED`, `lease_in_use_during 1 → after 0` |
| I-X3 | asserted, not displayed | `allowance: 1` per provider — while the fixture config says `terminals_per_subscription: 2` |
| the fence | still refuses, four ways | unadmitted adapter, unsupervised session, not-spawned-by-supervisor, and a **concurrent log holder** — all `refused:true`, all auditable (2 `registration_refused` rows) |
| the operator's world | unchanged | switch `OP-6`, `op12_authorized: []`, `fail_closed_for_op12:true`, sessions `0 → 0`, both OP-12 subscriptions `0`, ledger file byte-identical, status bar paints `grok 0/1 agy 0/1` |
| credentials | 5 placeholder sentinels under the OP-12 credential NAMES | absent from the shell's durable main-process log and from the receipt (re-scanned immediately before the write) |
| OWED | 6 keys, each naming a leg not performed **and agreeing with a measurement** | see §4 |

## 3. Substitutions and limitations (Directive §6, stated exactly)

**Four inputs are injected in the registration legs, and all four are named — in the producer, in
the receipt, and here.** The first version of that sentence said "exactly one thing", which the
spec-auditor correctly called a MAJOR: it concealed which gates the report had answered for itself.

1. **the live-operation switch** — a FIXTURE config in a scratch directory, read by the REAL loader
   through the same code-pinned scope check. This is the §17/§6 substitution, because the operator's
   own file cites OP-6 and denies both providers, and opening it is theirs alone (invariant 1);
2. **CLI presence and the executable** — a scratch path that is never spawned;
3. **a scratch lease ledger** — so the operator's durable one is never written;
4. **the holder pid** — this process.

**Not injected, and this is what makes the leg mean anything:** the **deployment profile** is the
HOST's, so an `offline_airgapped` host refuses at gate 1 exactly as the product path would
(invariant 20's air-gap half — a self-manufactured `cloud` loader made it structurally unreachable
inside the artifact claiming the gate chain ran, which is U91's shape); and the operator's **R8 §6
terms determination** is the recorded one at directive §17, cited at the call site. **No CLI is
executed and no live model call is made.**

**Still OWED, unchanged from 18C except where noted:** the live probe per provider, the live
in-Electron receipt per provider, `agy`'s offline-unverifiable auth state, `grok`'s (a usable
session is not a live reply), and the operator's own switch. **New and narrower:** no record exists
on the operator's **durable** node log — every record measured here is on a scratch log under the
fixture switch. That leg lands with the live probe, not before it.

**Disclosed cost (D-P18-7/U271/U290):** the receipt's picker read enumerates both OP-12 CLIs — one
`grok --version`/`grok models` pair and one `agy` pair, token-free metadata that leaves this host.
The registration report itself performs **no host calls of any kind**.

## 4. The U296 remedy, completed rather than mitigated

The `.amendment` gate found that the shipped OWED block had no red-able test. This unit's first cut
answered that with keyword rules — and the gate-validator showed that was still only half: a
**reworded** false claim passed every rule, and the report already measured the fact contradicting
it. `owedClaimsAgreeWithMeasurements` now reads the measurement: the durable-record claim is refused
if the report measured the operator's node log as PRESENT, if the report did not measure it at all,
or if the claim is reworded away from the fact it is about. Five tests, one mutation (R13).

## 5. Suites and harnesses — re-measured on the tree that is tagged

| Suite / harness | Result |
|---|---|
| `py -3.12 -m pytest tests/ -q` | `2059 passed, 1 skipped in 385.09s` |
| `apps/desktop` — `npm test` | `tests 751 / pass 751 / fail 0` |
| `terminal` — `node --test test/*.test.js` | `tests 216 / pass 216 / fail 0` |
| `py -3.12 tools/mutation/_op18d_close_mutations.py` | **29 mutations, 29 RED, every restore byte-identical** |
| `npm run test:falsify` / `test:falsify:authority` | ALL CAUGHT / ALL 11 CAUGHT, byte-identical restores |
| `pyflakes` on every changed Python file | clean (the touched files; the repo-wide run has pre-existing unused imports — scoped honestly, per validator MINOR-3) |
| `py -3.12 tools/manifest/compute_manifest.py --check` | `freeze check OK`; `freeze_integrity_sha256` still the Phase-0 `8E604CA3…`, operator signature still `SATISFIED_BY_OPERATOR_RULING` |

`py -3.12` because the bare `python` on this host is 3.14 and cannot collect the suite.

**Two of this unit's own guards were GREEN when first written**, and both are recorded rather than
smoothed over: C2 (deleting the schema validation changed nothing, because every record the tests
build happens to be valid — a record that would NOT validate is now a test) and C10 (the fake result
was missing three fields, so other conjuncts failed the report instead of the one under test).
`main.js`'s falsification baseline was re-pinned after re-reading every mutation against the new
tree; all anchors present, all caught, restore byte-identical.

## 6. Both mandatory reviewers, foreground, in-turn (D-LOOP-2), on `2a351e7`/`03d78db`

**gate-validator: PASS_WITH_RESERVATIONS.** It re-ran every suite and harness and reproduced every
number; added **13 mutations of its own** (11 RED); re-ran the in-Electron check and obtained a
receipt differing only in the scratch directory name and timestamps; drove the **open-switch** path
with a fixture config and confirmed the verdict refuses to let this receipt stand in for the live
legs; and hashed the operator's durable lease ledger before and after the full pytest run, 13
mutation runs, two more full-suite mutation runs and the in-Electron check — **unchanged every
time**, with `.sovereign_store/nodes/` absent throughout.

**spec-auditor: PROHIBITED DRIFT: NONE**, no invariant violated in enforcement terms, with an
explicit statement of the invariants checked and found clean (1, 2/I-C1, 12, 20, 21/I-X3, 27,
§2.2/§13, I-SC1, I-M2/I-07, 16, 30, and the OP-12 directive's §8/§12/§14).

**Every MAJOR and MEDIUM was fixed in-unit, each with a red-able test and a mutation:**

| # | Finding | Disposition |
|---|---|---|
| **SA MAJOR-1** | the report claimed "exactly one substitution / the whole gate chain" while answering three of that chain's inputs itself — including a self-manufactured `cloud` profile, making invariant 20's air-gap half unreachable inside the artifact that claimed the chain ran | **FIXED** — `profile_loader_from_host()`, the operator's terms basis cited at the call site, and a substitution string that names all four injected inputs and the two that are not. Mutation R9; test drives an `offline_airgapped` host to a `ProfileViolation` |
| **GV MEDIUM-1** | `node_record` metadata reached the append-only log unchecked — the validator wrote a non-node document naming `kimi_k3` onto a verified chain through the shipped API | **FIXED** — `NodeRegistry.register` refuses a record that disagrees with the registration carrying it (structural, not schema: the registry must not grow a validator dependency). Mutation R8 |
| **GV MEDIUM-2** | OWED red-ability was keyword-shaped; a reworded false claim passed while the report's own `durable_store` said the opposite | **FIXED** — §4 above. Mutation R13 |
| **GV MEDIUM-3** | `real_switch` silently followed `SOVEREIGN_LIVE_OPERATION_CONFIG` and disclosed no path — the validator produced a receipt reporting `register_row: OP-12` for a file in `%TEMP%` | **FIXED** — path published, override flagged, and the verdict refuses an env-overridden read outright. Mutations R10, R14 |
| **SA MEDIUM-2** | incarnations were counted in memory and `NodeRegistry` never replays its log, so every probe run on the operator's host would append another incarnation-1 `spawn` row | **FIXED** — the log answers it, which is what the comment already claimed. Mutation R3 |
| **SA MEDIUM-3** | `register_session` took any duck-typed object, so a namespace with `supervised=True` could get `spawned_by_supervisor: true` written under the supervisor's name | **FIXED** — `GovernedProbeSession` only, and it must carry the terminal it was counted under. Mutations R1, R2 |
| **SA MEDIUM-4** | every exit was recorded `expected=True, exit_code=None`, so a crashed session read as a clean one | **FIXED** — both measured; the runner records the child's real code. Mutation R6 |
| **SA MEDIUM-5** | no cross-process lock on a hash-chained durable log: two processes appending would break the chain permanently, and a corrupt log cannot be opened, wedging the governed-probe path with no repair append-only semantics permit | **FIXED** — exclusive pid-stamped lock, dead holders reclaimed through `terminal_lease.pid_is_alive` (not a second copy of that question), handed back on every exit path. Mutations R4, R5, R7 |
| **SA MEDIUM-6** | a unit test pinned the deterministic suite to the operator's mutable live switch — it would have gone red the moment they did the very thing §17 waits for | **FIXED** — the pytest layer asserts self-consistency; the opened-switch refusal lives in the verdict, where it is tested |
| GV MINOR-1/2 | two validator mutations stayed GREEN: loosening `is not True`, and hardcoding the provenance | **FIXED** — both pinned. Mutations R16, R17 |
| SA MINOR-7/8/9 | the durable-store rule was conditional; the store was measured by size; the I-X3 allowance was displayed, not asserted | **FIXED** — unconditional, content-hashed, asserted. Mutations R15, R12, R11 |
| GV MINOR-3 | "pyflakes clean" was scoped to the touched files | **CORRECTED** — §5 says so |
| SA MINOR-4 | the selfcheck headline overstated a fixture-switched registration | **FIXED** |
| SA NIT-10/11/12 | `kimi_k3` called a pending decision; a dead `model_ref` lookup; a bare `ImportError` where every other refusal has a gate id | **FIXED** — all three |
| GV NIT-1 | scratch dirs under `%TEMP%` | **DISCLOSED** — `path_is_scratch` is now an asserted conjunct, and the paths are in the receipt |

## 7. Two failures recorded rather than smoothed over

1. **The first in-Electron run FAILED** (`ok:false`), and the world was right: the verdict
   re-implemented the §17 lease check instead of using `op12-acceptance-verdict.leasesAreZero`, and
   read an ABSENT lease bucket as a defect. The ledger only creates a bucket once something is
   counted in it. Fixed in `03d78db` — one rule, one place — with three tests.
2. **The launcher printed `remaining=87292`** on the final receipt run, i.e. one tracked pid outlived
   its sweep. Checked immediately after: the process did not exist, and no process on this host has a
   command line naming this repository apart from this session's own shell tooling. A helper exiting
   between the sweep and the print is not a leak, and saying so is better than trimming the line.

## 8. Scope and prohibitions

No `docs/canonical/`, no frozen schema edited (the amendment is a successor FILE; `--check` proves
the Phase-0 hash and the operator signature are intact), no `mcp_server/`, `tools/loop/run_loop.ps1`
untouched. `config/live_operation.json` is gitignored, was never written by this build, and is read
read-only — the receipt now says WHICH file that was. Registers are append-only. No credential was
created, read, stored or transmitted: the sentinels are placeholder values under real names,
restored in `finally`. `.sovereign_store/` was never written by the suite or the check (measured by
content hash, before and after). No push, no remote, no publication.

## 9. Verdict

`gate/phase-18d` — **PASSED**, on the evidence above, both mandatory reviewers run foreground and
every MAJOR and MEDIUM fixed in-unit. Closed by operator-delegation (ruling 2026-07-16, register
OP-1..OP-3). Phase 18's terminal tag **`product/multi-frontier`** is applied here: 18C deliberately
did not apply it, so per §17.1 no tag is moved and no successor tag is needed.

**Not claimed, in the plainest words available:** no live Grok or Antigravity call has ever been
made by this build; no pane has ever been opened for either provider; no OP-12 terminal has ever
been leased on the operator's durable ledger; and no node record exists on the operator's durable
node log. What IS claimed is that the vocabulary admits both providers, the registration path is
real and exercised end to end through the product modules, the fence still refuses what no schema
version admits, and the only thing standing between this and a live record is the operator's own
switch.
