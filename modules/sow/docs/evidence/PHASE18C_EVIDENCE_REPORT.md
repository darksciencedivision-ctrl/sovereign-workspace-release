# PHASE 18C — EVIDENCE REPORT

**Track:** OP-12 18C — live acceptance for `grok_build` (Grok Build) and `google_antigravity`
(Gemini · Antigravity). **High-stakes gate** (gate-validator + spec-auditor mandatory).
**Authorization:** OP-12 (operator, 2026-07-31), `AUTONOMOUS_BUILD_DIRECTIVE.md` §17 +
`docs/operator/OP12_PROVIDER_DIRECTIVE_GROK_ANTIGRAVITY.md` §17.
**Verdict:** **PASSED as SKIP-WITH-RECORD** — the live legs' entry conditions are the operator's and
are unmet; §17 states that an unmet entry condition is *skip-with-record, not failure*. Everything
this loop owns is built, and the fail-closed world is measured rather than asserted.

| | |
|---|---|
| Sub-steps | `.probe-path` (U234, the governed supervised session the live probe runs inside) → `.close` (this) |
| `.probe-path` commits | work `fa85909`, remediation `893764d`, evidence/registers `2ffdfdc`; round-1 findings in `docs/evidence/PHASE18C_PROBE_PATH_CHECKPOINT.md` |
| `.close` work commit | `2561c19` — *"the switch is the only thing refusing, and now it is measured"* |
| `.close` remediation | `93dcba0` (both reviewers' BLOCKING/MAJOR/MEDIUM) and `5ece698` (a SyntaxError that shipped past a green suite — see §7) |
| Receipts | `docs/evidence/receipts/PHASE18C_ACCEPTANCE_SELFCHECK.json` (in-Electron, D-P16-0), `docs/evidence/receipts/PHASE18C_PROBE_ENGINE_REPORT.json` (the §17 probe engine, exit 3) |
| Register rows | U237 (closure), U238 (re-owned), U289–U292; decision rows D-P18-9, D-P18-10 |

---

## 1. What §17 asks for, and what was and was not done

Directive §17 defines 18C acceptance as, per provider: **one harmless live probe**
(`GROK_PROVIDER_OK` / `GEMINI_PROVIDER_OK`, exit-code + structured-output + repo-status-unchanged
acceptance) and **one in-Electron receipt** (picker → supervised pane → exact provider+model verified
→ harmless prompt → live response → teardown → lease 0 → no credential material in any log → tree
clean).

Its **entry conditions are the operator's**: each CLI's own login, and the operator's own edit to
`config/live_operation.json` naming both providers. On this host that file cites
`register_row: "OP-6"` with `providers: ["claude_code", "openai_codex_cli"]`. Both OP-12 providers
are therefore **DENIED** — the fail-closed switch working exactly as designed.

**Neither live leg was performed for either provider. No live model call has ever been made to Grok
or Antigravity by this build.** That is stated here, in the receipt's `scope_note`, in the receipt's
`OWED` block, and in the register.

## 2. What IS evidenced — the fail-closed world, measured

`apps/desktop/selfcheck/op12-acceptance-selfcheck.js`, run inside the packaged Electron shell
(`node selfcheck/run.js op12-acceptance`), receipt `PHASE18C_ACCEPTANCE_SELFCHECK.json`:
`ok: true`, `source.commit 5ece698` (**== HEAD at the time of the run**),
`tracked_product_tree_clean: true`, `unexpected_untracked_product_files: []`.

| Leg | Fact | Measured value |
|---|---|---|
| world | the operator's switch, read from the real enumeration | `fail_closed: true`, `register_row OP-6`, `op12_authorized: []` |
| enumeration | both CLIs publish their own listings | grok 1 option, agy 11 options; **0 available** in each, each greyed with the live-authorization reason |
| operator's CLICK | refused by the shell's front-line guard, naming the provider | `recorded:false`, `launched:false`, reason carried |
| **the AUTHORITY** | the host's own greyed option — not a forgery — through `launchWorkerPane` into the Python emitter | `refused_by: "live_operation"` (gate ID, both producers agreeing) |
| the gates BEFORE the switch | every one PASSED | `selection_offered: true`, `cli_present: true`, `live_operation_authorized: false`, `ix3_counted: false` |
| nothing born | live session count across every attempt | `sessions_before 0 → sessions_after 0`; ticket `lease:null`, `launch:null`, `subscription_governed:false`, `governor_released:true`; launcher record `state "refused"`, `leaseId null`, `argv null` |
| §17 lease line, durable | the real `TerminalLeaseLedger` | `grok_build_subscription: 0`, `google_antigravity_subscription: 0`; operator's ledger file **byte-identical** before/after |
| §17 lease line, VISIBLE (inv 27) | the running status bar's model AND painted text | `grok 0/1`, `agy 0/1`; painted `subscriptions claude 0/2 codex 0/2 grok 0/1 agy 0/1` |
| §17 credential line | 5 placeholder sentinels planted under the OP-12 credential NAMES | absent from the shell's durable main-process log and from the receipt payload (re-scanned immediately before the write) |
| D-LOOP-1 | the one emitter session key this check chose itself | both released, `released:false count:0` — nothing was ever held |
| OWED | every acceptance leg not performed, each with a reference | 7 keys, all present and all citing a lookupable id |

**The single sentence this gate rests on:** every gate before the operator's switch passed, and the
switch is what refused. The CLIs are installed and answering, the options are the CLIs' own, the
governed path is wired end to end — and `config/live_operation.json` says no.

The §17 probe engine leg is `PHASE18C_PROBE_ENGINE_REPORT.json` (`--action probe --provider all`,
**exit 3**): both providers `executed:false`, `accepted:false`, `gate.allowed:false`, "probe refused
before spending anything". Nothing was spawned.

## 3. `.probe-path` (U234), summarised — full findings in the checkpoint file

The 18A live probe existed and refused to execute, because its child would have been a bare
`subprocess.run` with no node identity, no I-X3 lease and no teardown accounting.
`node_runtime/supervisor/provider_probe_session.py` runs the interactive pane's gate chain, in the
same order, for a headless child, holds ONE durable lease for exactly the child's lifetime, runs it
inside the repository's job-object boundary with the credential-bearing environment removed by NAME,
and releases on every exit path with the release **measured**. Round 1 found the module's headline
claim false about the two gates whose input comes from outside it (a manufactured `cloud` profile,
so invariant 20's air-gap half could never fire; and `operator_terms_confirmed` defaulting to the
operator's determination) — both are required keywords now, and the claim itself is a drift detector.

**The gate-validator re-verified this by execution, not argument.** With a fixture config naming
`grok_build` and PATH shims standing in for the CLIs, `--action probe` proceeded through the whole
chain — minted `probe-grok`, took `lease-86b9566db3fd` on `grok_build_subscription`
(`allowance 1, in_use 1`), resolved the binary, scrubbed the env, ran the child, and returned
`teardown: {lease_released: true, governor_released: true, in_use_after: 0, process_tree_clean: true,
measured: true}` with `node_registered: false`. Under `SOVEREIGN_DEPLOYMENT_PROFILE=offline_airgapped`
the same open switch yields `gate.allowed: true` but `executed: false` —
`ProfileViolation … excluded from the offline/air-gapped profile`. The invariant-20 fix is real.

## 4. Substitutions and limitations (Directive §6, stated explicitly)

1. **The live acceptance legs are SUBSTITUTED by the fail-closed receipt.** This is the §17
   skip-with-record path, not an approximation of a live result. The receipt's verdict module
   **refuses to let this receipt stand in for the live legs if the operator opens the switch**:
   `worldIsFailClosed` returns false, the run throws, and the receipt is written with `ok:false` and
   the reason. It can never be reused as evidence of acceptance.
2. **U227 is NOT resolved and this gate does NOT close on it.** No Sovereign node RECORD exists for
   either provider: `schemas/node.schema.json`'s adapter enum is frozen and has no member for them,
   and `NodeRegistry.register` refuses both with an append-only `registration_refused` event
   (verified by the validator against the schema file itself, unchanged). Operator-reserved.
3. **`agy` auth is UNVERIFIABLE offline** (18A, U233) — that CLI exposes no offline auth surface.
   `grok models` answered with the CLI's own listing, which is as far as an offline surface can go;
   it is evidence of a usable session, not of a live reply.
4. **U238's two probe-acceptance holes are NOT fixed here** and are re-owned to the operator's live
   acceptance run. They cannot fire in a world where no probe executes.
5. **Disclosed network cost (D-P18-7/U271/U290).** The acceptance check performs three host
   enumerations per provider (the picker read, which probes both, plus the launcher ask and the
   ticket read for that provider's own selection) — i.e. three `grok --version`/`grok models` pairs
   and three `agy` pairs, all token-free metadata, no prompt, no completion, no credential read.

## 5. Suites and harnesses — re-measured on the tree that is tagged

| Suite / harness | Result |
|---|---|
| `py -3.12 -m pytest tests/ -q` | `1947 passed, 1 skipped in 378.74s` |
| `apps/desktop` — `npm test` | `tests 692 / pass 692 / fail 0` |
| `terminal` — `node --test test/*.test.js` | `tests 216 / pass 216 / fail 0` |
| `py -3.12 tools/mutation/_op18c_close_mutations.py` | **17 mutations, all `RED (guarded)`, `restore_byte_identical=True`, `unguarded-or-broken: 0`** |
| `py -3.12 tools/mutation/_op18c_probe_path_mutations.py` | 15/15 RED (validator's own re-run) |
| `npm run test:falsify` / `test:falsify:authority` | ALL CAUGHT / ALL 11 CAUGHT, byte-identical restores |
| `pyflakes` on every changed Python file | clean |
| `py -3.12 tools/manifest/compute_manifest.py --check` | `freeze check OK: no drift in FROZEN set` |

`py -3.12` because the bare `python` on this host is 3.14 and cannot collect the suite.

**The `.close` work commit's message says "desktop 686"; the tree yields 692.** The gate-validator
caught the first miscount (686 vs 688) and the number moved again with the two later commits. Commit
messages are immutable; **the numbers in the table above are the measured ones** and are what this
gate rests on. This is the second consecutive sub-step to miscount a suite in its commit message
(`.probe-path` MINOR-5: 1919 vs 1920) — recorded, not smoothed over.

**The mutation harness's own scoring was proved, not asserted:** a Node selector that collects
nothing scores `SETUP-FAIL` (never RED), a passing one scores `GREEN`, and a missing pytest file
scores `SETUP-FAIL`. Two of the 17 mutations were **GREEN when first written** — `refused_by !==
LIVE_GATE_ID` and `gates.selection_offered !== true` were each caught only incidentally by another
rule's test — and are the reason two isolation tests exist.

## 6. Both mandatory reviewers, foreground, in-turn (D-LOOP-2), on `2561c19`

**gate-validator: PASS_WITH_RESERVATIONS.** It re-ran every suite and harness, added **25 mutations
of its own** covering every remaining decision in the verdict module (all RED), re-ran the
in-Electron check itself and obtained a byte-equivalent receipt, and independently drove the Python
authority to reproduce the gate map. Its negative control is the strongest single piece of evidence
here: with fail-fast PATH shims in front of `grok`/`agy`, the enumeration returns **zero options** and
the check **throws** — so the receipt's 1 + 11 real model slugs could not have been produced without
the real CLIs answering. A PATH tripwire in front of the whole 1944-test suite logged **zero** `grok`
and `agy` executions.

**spec-auditor: PROHIBITED DRIFT: NONE**, no invariant violated, with an explicit statement of the
invariants checked and found clean (1, 2/I-C1, 3/27, 12, 13, 19/20, 21/I-X3, §2.2/§13, U227,
I-SC1, 16, and §17's skip-with-record reading).

**Every BLOCKING, MAJOR and MEDIUM was fixed in-unit**, each with a red-able test:

| # | Finding | Disposition |
|---|---|---|
| GV BLOCKING-1/2 | no evidence report; receipts untracked | **FIXED** — this file, and both receipts committed here |
| **SA MAJOR-1** | the cost disclosure was wrong by 5×, and the "scoped per selection" property was not implemented: an OP-12 selection probed **both** CLIs, so verifying an Antigravity selection emitted a grok.com call under the operator's SuperGrok session | **FIXED** — `only_op12_probe()` scopes an OP-12 selection to its own CLI (U290); the disclosure now COUNTS |
| GV MAJOR-3 / SA MINOR-8 | `U289` cited in shipped code with no register row | **FIXED** — U289 appended |
| GV MEDIUM-4 / SA MEDIUM-3 | `receipt.ok` did not require a clean committed product tree, though §17 names it and both sibling receipts gate on it | **FIXED** — both facts are conjuncts of `ok` |
| GV MEDIUM-5 | commit's suite number wrong (686 vs 688) | **CORRECTED** — §5 re-measured |
| SA MEDIUM-2 | `scope_note` said "no live Grok call was made" beside a note saying metadata calls left the host | **FIXED** — "no live MODEL call … no prompt, no completion", pointing at the counted disclosure |
| SA MEDIUM-4 | a dirty `M apps/desktop/main.js` at the audited HEAD | **EXPLAINED** — U279: `git diff --exit-code` is empty, the worktree blob is byte-identical to index and HEAD, zero CR bytes. A stale index stat, not a change. The auditor is read-only with no git tool and correctly refused to assume. |
| SA MEDIUM-5 | `_how_to_open` under-warned when the loader denied for a reason other than provider scope (absent file, master flag off) | **FIXED** — those branches carry the loader's own reason and point at the example file; two tests |
| SA MEDIUM-6 | U238, whose register owner is **18C**, was named nowhere | **FIXED** — an OWED key plus an appended re-ownership row |
| GV MINOR-6 | no statement about `grok`'s auth state, only `agy`'s | **FIXED** — `OWED.grok_auth_state` |
| GV MINOR-7 / SA NIT-16 | `entry_conditions_met` / `live_legs_performed` were literal `false` | **FIXED** — both derived |
| GV MINOR-8 / SA MINOR-10 | `_how_to_open` claimed 18B provenance for the OP-6 pair and said "that row" with two listed | **FIXED** — provenance only for the OP-12 pair; "one of register rows …"; a test |
| GV MINOR-9 / SA MINOR-18 | the credential scan's two sinks over-described as "nowhere the run wrote" | **FIXED** — the comment and a `scope_note_credential_scan` say exactly which two and why |
| GV MINOR-10 / SA NIT-19 | `gates.operator_terms_confirmed` is a Python parameter default, published as a passed gate | **DISCLOSED** — `scope_note_gate_map`; the verdict deliberately does not rest on it. The underlying fail-open on the worker emitter is **carried** (U292) |
| GV MINOR-11 | the re-pin note claimed all three `main.js` edits were inside the `SHELL_SELFCHECK` block; the `require` is top-level | **FIXED** |
| SA MINOR-7 | "REFUSES to write this receipt at all" — it writes it, with `ok:false` | **FIXED** |
| SA MINOR-9 | U237's row still says OPEN/code-owed while the shipped text says "closing U237" | **FIXED** — appended closure row |
| SA MINOR-11 | the direct ticket ask had no release counterpart | **FIXED** — released unconditionally in `finally`; the receipt records it |
| SA MINOR-12 | the §14 rule matched the enumerated scope list as prose, and was not applied to the CLICK refusal | **FIXED** — brackets stripped; the rule now covers the text the operator reads; two tests, two mutations |
| SA MINOR-13 | the Python mutation harness lacked the lock/signal/restore contract its JS sibling documents | **FIXED** for this harness; `_op18c_probe_path_mutations.py` carried (U292) |
| SA MINOR-14 | fields written after the credential scan were unscanned | **FIXED** — the final payload is re-scanned and the write is refused on a hit |
| SA MINOR-15, NIT-17, NIT-20 | probe report self-labels `phase 18A`; `lease_status` conflates absent-bucket with measured-0; harness coverage gaps | **CARRIED** — U292 |

## 7. One failure recorded rather than smoothed over

The remediation commit `93dcba0` shipped a **SyntaxError** — two `catch` clauses on one `try` — in
`op12-acceptance-selfcheck.js`. Every suite was green. It was found only when the packaged Electron
run hard-timed-out at 600 s with no receipt written. Nothing headless loads these modules: they are
required by `main.js`, which cannot be required in a test, so the entire `selfcheck/` directory sat
outside every syntax check this repo runs — **D-P16-0's own lesson, reproduced inside the files that
exist to prevent it.** `5ece698` fixes the clause and, more to the point, makes
`selfcheck-guards.test.js` parse every file in the directory (`vm.Script`, no execution) and load
every module-shaped one. Reverting the fix turns the ordinary suite red. **U291.**

## 8. Scope and prohibitions

No `docs/canonical/`, no frozen schema, no `mcp_server/`, `tools/loop/run_loop.ps1` untouched.
`config/live_operation.json` is gitignored and was never written by this build (only the tracked
`.example` describes the shape). Registers are append-only. No credential was created, read, stored
or transmitted: the sentinels are placeholder values under real names, restored in `finally`, and
every provider-CLI child is spawned through `scrub_provider_env()`, which removes all five names by
exact match and by prefix. No push, no remote, no publication.

## 9. Operator ruling received DURING this unit — OP-12.1

While this unit ran, the operator appended **§17.1 (OP-12.1)** to `AUTONOMOUS_BUILD_DIRECTIVE.md`:
U227 is to be resolved by a **successor schema `node@1.1`** beside the frozen `@1.0`, and — since
18C closes here with skip-with-record — the work continues as **`phase-18d`**: the amendment, real
node registration for both providers, and completion of every leg 18C skipped on the registration
fence. That directive text is committed here verbatim as the operator wrote it. **This unit did not
act on it**: it is the next work unit, and its `OP-12.1` decision row is by the operator's own
instruction the first bookkeeping act of the unit that executes it. `gate/phase-18c` is therefore
tagged on what 18C actually established, and 18C's skipped legs remain skipped-with-record until
18D.

## 10. Verdict

`gate/phase-18c` — **PASSED (skip-with-record on the operator's entry conditions)**, on the evidence
above, both mandatory reviewers run foreground and every BLOCKING/MAJOR/MEDIUM finding fixed in-unit.
Closed by operator-delegation (ruling 2026-07-16, register OP-1..OP-3).

**Not claimed, in the plainest words available:** no live Grok or Antigravity call has ever been made
by this build; no pane has ever been opened for either provider; no OP-12 terminal has ever been
leased; and no Sovereign node record exists for either. `product/multi-frontier` is **not** applied —
Phase 18's terminal tag waits for 18D per the operator's OP-12.1 sequencing.
