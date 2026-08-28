# PHASE 18C `.probe-path` — REVIEW ROUND 1, FINDINGS AND DISPOSITIONS

**Status of the track:** `gate/phase-18c` does **NOT** exist and this unit did not create it.
**Sub-step:** `phase-18c.probe-path` — the governed, supervised session the OP-12 live probe runs
inside (U234). **Not** the 18C live acceptance, which is entry-condition-blocked (see the last
section).

**Why this file exists.** Subagent output does not survive a print-mode turn (D-LOOP-2), and the
18A round-4 spec-auditor's first must-fix finding was that this repo's own durable review record
claimed two rounds when three had run — the exact loss the record exists to prevent (U226). Both
reviewers' findings are therefore written down here, in full, with what was done about each.

| | |
|---|---|
| Work commit reviewed | `fa85909` — *"the probe that refused to spawn now runs inside a lease it hands back"* |
| Reviewers | `gate-validator` and `spec-auditor`, **foreground, in-turn, concurrent** (D-LOOP-2) |
| gate-validator verdict | **FAIL** — 0 BLOCKING, 4 MAJOR, 7 MEDIUM, 8 MINOR, after **50 mutations (34 RED, 9 GREEN + 1 non-defect)** |
| spec-auditor verdict | **PROHIBITED DRIFT: NONE**; no invariant violated at HEAD; 1 MAJOR, 7 MEDIUM, 3 MINOR, 1 NIT |
| Remediation commit | see `git log` — every BLOCKING, MAJOR and MEDIUM fixed **in-unit**, each mutation-proved |
| Register rows added | U280–U288 (append-only; the two earlier U234 rows left exactly as written) |

---

## 1. The finding that matters most

**The module's headline sentence was false about two of its own five gates, and one of them was
demonstrated rather than argued.** `provider_probe_session`'s docstring claimed *"It is the
interactive pane's gate chain, in the same order, for a headless child. Nothing here is a second,
looser rule … a probe that could be permitted by a weaker rule than a session is a bypass with a
diagnostic's name on it."* It was permitted by a weaker rule than a session, in exactly the two
places where the input comes from **outside** the module:

- **Gate 1, the deployment profile.** The module manufactured `ProfileLoader(DeploymentProfile("cloud"))`
  when no loader was injected, and the sole production caller injected none — so `check_eligible`,
  the only thing in that call implementing invariant 20, could never fire. The validator did not
  reason about this; it ran it. Under `SOVEREIGN_DEPLOYMENT_PROFILE=offline_airgapped`:

  > `recon.airgapped() -> True`
  > `!! the AIR-GAPPED profile did NOT refuse the governed probe session: probe-grok lease-436f8efd87ba`

  A **durable** `grok_build_subscription` lease, written and released on an air-gapped host for a
  probe that was never going to run. No cloud call escaped, because `_guarded_run` still refuses one
  layer above — which is the inversion the module's own docstring says is unacceptable: the
  invariant-20 protection lived in the *diagnostic tool*, not in the module advertising it.
- **Gate 3, the operator's R8 §6 live-terms determination.** `operator_terms_confirmed: bool = True`,
  and the production caller never passed it, so `LiveTermsNotConfirmed` was unreachable outside
  tests. Every comparator in the tree does the opposite: `_authorize_frontier` requires it,
  `pane_node_spawn` defaults it **False**. Invariant 1 is that the app never self-authorizes what is
  the operator's to determine.

Both reviewers found both, independently, and the auditor placed them precisely: they are U91's and
U98's shapes, reproduced in `node_runtime/supervisor/` — a layer neither row had previously reached.

**Fix.** Both are now **required keywords**, matching `_authorize_frontier`. The production caller
builds the loader from the host's real profile (`profile_loader_from_host()`, which fails closed on
an unrecognised id) and passes the terms flag with its authorizing artifact named at the call site
(`AUTONOMOUS_BUILD_DIRECTIVE.md` §17). And because the *claim* is what drifted, the claim is now a
test: `test_the_gate_chain_matches_the_pane_paths_gate_chain` extracts the ordered gate calls from
both functions and requires them equal. Recorded as **U283**; U91 and U98 keep their own.

## 2. The second one: the line the whole sub-step exists for had no test

`run_probe`'s `run = runner if runner is not None else _supervised_runner(session)` is the single
production line that discharges U234. The validator replaced `_supervised_runner` with
`subprocess_runner()` — the bare `subprocess.run` U234 forbids — and the suite passed:

> `[GREEN <<< UNGUARDED] V24 recon-supervised-runner-swapped-for-naked-subprocess`
> `    last='382 passed, 1 skipped in 7.39s' restored=True`

All eight `run_probe(...)` call sites in the suite passed `runner=`, so the `runner is None` wiring
had never executed. Three more GREENs sat in the same blind spot: argv built from the bare command
NAME instead of the resolved executable (V37), argv truncated to one element (V38), and
`executable=None` reaching the gate so it fell back to a real host PATH lookup inside a
deterministic test (V32). And the "RESOLVED binary" gate — *"the child must be the file that was
gated"* — guarded a value nobody spawned: `supervised_probe_runner` executed whatever argv it was
handed and never compared it to `session.executable`.

This is **U275's pattern**, the one *this phase* wrote at 18B `.picker` — the dangerous failure of a
selection point is a **wrong** entry, not a missing one — unapplied at the selection point this
sub-step is about. Recorded as **U284**. Fixed by `test_the_UNINJECTED_runner_is_the_supervised_one`
(drives `run_probe` with `runner=None` against the real `_supervised_runner`, seaming only
`run_managed_process`, and asserts the child was the gated file, workspace-bound, credential-scrubbed,
bounded by the default timeout, with the measured teardown recorded) and by the runner refusing any
argv whose first element is not `session.executable`.

## 3. Every finding, and its disposition

### gate-validator — FAIL (0 BLOCKING · 4 MAJOR · 7 MEDIUM · 8 MINOR)

| # | Finding | Disposition |
|---|---|---|
| MAJOR-1 | Gate 1's air-gap half inert (hardcoded `cloud` loader); proved by opening a leased session on an air-gapped host | **FIXED** — required keyword + `profile_loader_from_host()`; U283 |
| MAJOR-2 | Gate 3 defaulted open; caller never supplies it | **FIXED** — required keyword, basis cited at the call site; U283 |
| MAJOR-3 | `_supervised_runner` swappable for the naked spawn, suite green | **FIXED** — U284 |
| MAJOR-4 | "RESOLVED binary" gate guards a value never spawned | **FIXED** — runner refuses `argv[0] != session.executable`; U284 |
| MEDIUM-1 | Register's U234 row still says `_SUPERVISED_PROBE_PATH = False` | **FIXED** — appended sibling U280 (never an edit; invariant 12) |
| MEDIUM-2 | Two contradictory "Order is deliberate" paragraphs in `run_probe` | **FIXED** — stale one deleted; U288(g) |
| MEDIUM-3 | `governor_released` hardcodable to `True` | **FIXED** — stuck-governor test requires `False`; U288(d) |
| MEDIUM-4 | Gate chain spelled twice with no drift detector | **FIXED** — `test_the_gate_chain_matches_the_pane_paths_gate_chain` |
| MEDIUM-5 | `DEFAULT_PROBE_TIMEOUT_S` could be `None`; never exercised | **FIXED** — default asserted through the runner; U288(e) |
| MEDIUM-6 | Mutation harness scored collection errors / no-tests-ran as RED | **FIXED** — exit 0 GREEN, 1 RED, else SETUP-FAIL; U285 |
| MEDIUM-7 | Mutation #9 injected an undefined name, testing a NameError | **FIXED** — rewritten as a faithful downgrade; U285 |
| MINOR-1 | Lease-purpose test imports the constant it compares against | **FIXED** — literals asserted too; U288(a) |
| MINOR-2 | `GATE_PROBE_IDENTITY` unpinned | **FIXED** — `.gate` asserted; U288(b) |
| MINOR-3 | `seeded_from_ledger` dead observability | **FIXED** — foreign-holder projection test; U288(c) |
| MINOR-4 | `OSError` from `led.release` leaks the governor slot | **FIXED** — durable release wrapped; governor release unconditional; U288(f) |
| MINOR-5 | Commit claimed 1919 passed; measured 1920 | **CORRECTED** — this unit's numbers are re-measured below |
| MINOR-6 | `_UNSUPERVISED_PROBE_REFUSAL` text stale ("launch-ticket path") | **FIXED** — names the governed session and says the path exists |
| MINOR-7 | Redundant `if not pid` guard (regex already refuses) | **NO CHANGE** — validator graded it a non-defect; the two messages differ usefully |
| MINOR-8 | No 18C checkpoint under `docs/evidence/` | **FIXED** — this file |

### spec-auditor — PROHIBITED DRIFT: NONE

| # | Finding | Disposition |
|---|---|---|
| MAJOR-1 | The parity claim is false in two places, both gates | **FIXED** (§1); the claim is now a test, not a sentence |
| MEDIUM-2 | `operator_terms_confirmed=True` fail-open in the supervisor layer; U98 on a new surface | **FIXED** + U283 |
| MEDIUM-3 | Hardcoded `cloud` profile; U91 on a new surface | **FIXED** + U283 |
| MEDIUM-4 | `subprocess_runner`'s docstring now stale in the opposite direction | **FIXED** — pinned by `test_the_metadata_runner_is_NOT_the_probes_runner`; U288(g) |
| MEDIUM-5 | Duplicate contradictory order paragraphs | **FIXED** — U288(g) |
| MEDIUM-6 | The runner measured the governed record and printed none of it (§17 requires the lease-to-zero line) | **FIXED** — U286 |
| MEDIUM-7 | `argv[0]` unbound to `session.executable` | **FIXED** — U284 |
| MEDIUM-8 | `ProcessTreeCleanupError` escapes; containment failure reads as a broken tool | **FIXED** — U287 |
| MINOR-9 | `stdin=DEVNULL` is a no-op on Windows; docstring and test assert the argument | **PROSE CORRECTED, MECHANISM CARRIED** — U281 |
| MINOR-10 | "Windows job-object boundary" is platform-conditional prose | **FIXED** — reworded |
| MINOR-11 | Two executable resolvers, unpinned to each other | **FIXED** — fabricated-PATH agreement test; U288(h) |
| NIT-12 | Register/evidence do not yet record 18C | **FIXED** — U280–U288 and this file |

## 4. What the reviewers verified as GENUINELY TRUE

Recorded because it is evidence, not decoration — and because the mutation counts below are the
reason the fixed list above is credible.

- **No live call is possible and none happened.** The validator built PATH tripwire shims
  (`grok.cmd`, `agy.cmd`, `claude.cmd`, `codex.cmd`) that log and exit 42, prepended them, and ran
  the whole Python suite: **zero `grok` and zero `agy` executions**. The only hits were 11
  `codex --version` metadata calls the guard explicitly allows (U165). Running the real engine under
  the tripwire: `engine exit: 3`, both OP-12 providers `executed false, accepted false, gate.allowed
  false`, **no provider CLI executed** — the operator's switch cites OP-6, which is the fail-closed
  world 18C starts in, working exactly as designed.
- **34 of the validator's 50 mutations were RED with byte-identical restores**, covering: the
  roster/live-auth `assert_startup`, the `PROBE_PROVIDERS` membership refusal, the `_PROBE_ID_RE`
  charset fence, the per-provider `_UNAVAILABLE` exception mapping (§14), the CLI-presence gate, the
  resolved-binary refusal, the governor counted by lease key rather than node id, the durable
  release, the governor release, the whole `finally` teardown, four env-scrub weakenings,
  `stdin`, the workspace binding, allowance hardcoded to 2 (19 tests red), session-id uniqueness,
  `node_registered` claiming True, the recon session never entered, `_SUPERVISED_PROBE_PATH = False`
  (6 tests red), `supervised_execution` claiming True, `live_auth` not passed, the probe role, the
  `interactive`/`one_shot` flags, `config_path` ignored, the permission profile blanked, and the
  durable acquire skipped (18 tests red).
- **U227 boundary intact.** `NodeRegistry.register` refuses both adapter ids with an
  append-only `registration_refused` event; `schemas/node.schema.json` untouched (`$id`
  `…/node@1.0`, sha256 `ab8edd5d…`); `compute_manifest.py --check` → `freeze check OK`.
- **I-X3 / allowance 1 enforced at three independent layers** (live-authorization `terminals_for`,
  the in-process governor's per-provider cap and ref↔provider binding, and the durable ledger's own
  re-check), with non-merging, second-concurrent-probe refusal, and the operator's own shell terminal
  blocking the probe all covered by tests. The auditor called the lease-key counting "the strongest
  engineering judgement in the unit" and confirmed no ordering leaks a slot between `gov.acquire`
  and `led.acquire`.
- **Credential isolation clean and stronger than required**: scrub by NAME only, union of the
  claude/codex/OP-12 classifiers, `XAI_API_KEY`/`GEMINI_API_KEY`/`GOOGLE_API_KEY` covered three ways,
  `child_env` deliberately not serialized, `_base_env` `repr=False` so a traceback cannot spill it,
  and `GROK_SANDBOX` (the CLI's only containment lever) deliberately preserved. Live-wiring run
  observed `env_has_xai: false` reaching `run_managed_process` with `XAI_API_KEY` set in the parent.
- **Invariant 29 honesty is exactly right** on the one surface that makes the claim: the docstring
  states that `--permission-mode plan` / `--mode plan` are arguments the harness honours and that
  the boundary guarantees process-tree teardown only (U25 remains owed). The module builds no argv,
  so the disclaimer is correctly scoped.
- **Scope clean**: no `docs/canonical/`, no frozen schema, no `tools/loop/run_loop.ps1`.

## 5. Suites, this turn, foreground

| Suite | Result |
|---|---|
| `py -3.12 -m pytest tests/ -q` (baseline, before remediation) | `1920 passed, 1 skipped in 356.99s` |
| `py -3.12 -m pytest tests/ -q` (after remediation) | **`1937 passed, 1 skipped in 346.16s`** |
| `apps/desktop` — `npm test` | `tests 654 / pass 654 / fail 0` |
| `terminal` — `node --test test/*.test.js` | `tests 216 / pass 216 / fail 0` |
| `py -3.12 tools/mutation/_op18c_probe_path_mutations.py` | **15 mutations, all `RED (guarded)`, `restore_byte_identical=True`, `unguarded-or-broken: 0`** |
| `pyflakes` on all changed Python files | clean |
| `compute_manifest.py --check` | `freeze check OK: no drift in FROZEN set` |

`py -3.12` because the bare `python` on this host is 3.14 and cannot collect the suite.

**One failure is recorded rather than smoothed over.** The first post-remediation full-suite run
reported `1 failed, 1936 passed` — `test_concurrent_writers_yield_conflict_never_silent_overwrite`,
in `mcp_server`, which this unit does not touch. It then passed 6/6 in isolation and the whole suite
passed on the next run. Recorded as **U282**, open: a suspicion is not a diagnosis, and a CAS-conflict
test that can be green by luck deserves more scrutiny than a green run gives it.

**The harness's own scoring was proved, not asserted.** After the fix,
`run("tests/unit/test_does_not_exist.py")` → `SETUP-FAIL` and `run(<a passing file>)` → `GREEN`, so
"nothing ran" can no longer be recorded as "a test caught it".

## 6. D-LOOP-1 / live-spend discipline

No live call was made and none was needed. Nothing was spawned that outlived the unit: every
`run_managed_process` in the tests is monkeypatched, and the two new PowerShell tests drive the real
runner against a **stub engine** that contacts no provider. The one test that exercises the real
engine end-to-end pins the live-operation config to a fixture authorizing only `claude_code` — the
18A gate-validator's F6 lesson, so a plain `pytest tests/` on this host cannot become a live spend
the day the operator extends the switch.

## 7. What remains before `gate/phase-18c` — and what is the OPERATOR's

**Remaining in this loop's hands (next unit, `phase-18c.close`):** whole-track reviews on the
composition, `docs/evidence/PHASE18C_EVIDENCE_REPORT.md` in Directive §6 format, the D-P16-0
in-Electron receipt for whatever is machine-checkable in the fail-closed world, the gate register
row, and the tag.

**Not this loop's to satisfy, and not a failure (directive §17, "unmet ⇒ skip-with-record"):**

1. **The operator's live switch.** `config/live_operation.json` today cites `register_row: "OP-6"`
   with `providers: ["claude_code", "openai_codex_cli"]`. Both OP-12 providers are therefore DENIED,
   which is the fail-closed design working. Extending it is the operator's edit to a never-committed
   file — and per **U237** the printed 18C instruction was wrong until 18B `.scope` shipped the
   code-pinned scope extension; that half is now done, so the operator's edit is all that is left.
2. **Each CLI's own login.** Recorded at 18A: `grok` 0.2.118 logged in; `agy` 1.1.9 auth
   UNVERIFIABLE offline.
3. **U227, operator-reserved.** No Sovereign node RECORD can exist for either provider until the
   operator rules — so 18C must not treat the fenced registration boundary as already open, and
   `gate/phase-18c` must not close on "U227 is answered".
