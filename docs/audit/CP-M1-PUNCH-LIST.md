# CP-M1 remediation punch list

Derived from `docs/audit/SYSTEM-REVIEW-20260827.md` and `docs/audit/AUDIT-01-REPORT.md`.

## Release rule

**Current disposition: NO-GO. Do not promote any current CANDIDATE gate.**

Work should proceed in the order below. A later section does not override an earlier unresolved blocker. Product repair, protected-tree changes, provider launches, Git creation, ledger edits, and PASS promotion require the authority already defined by the governing directives; this punch list grants none of that authority.

## Critical path

1. Record the required operator decisions and freeze the starting state.
2. Eliminate Token Center and SOW source/copy ambiguity.
3. Repair the Token Center security boundary.
4. Repair SOVEREIGN packaging/provenance and SOW freeze/provenance.
5. Reconcile runtime declarations with actual behavior.
6. Make the test suites hermetic and create one installed-artifact release test.
7. Run local, no-provider acceptance.
8. Under explicit authority, run llama.cpp and provider-dependent acceptance.
9. Rebuild frozen evidence and recompute scope controls independently.
10. Have an independent reviewer re-evaluate each gate before any PASS promotion.

---

## P0 — immediate release blockers

### P0-01 — Record the remediation authority and baseline

**Problem:** Several required actions affect protected originals, installed launchers, frozen schemas, or live services. They cannot be inferred from this audit.

**Actions:**

- Record an operator instruction naming the authorized repair scope.
- Explicitly decide:
  - the canonical Token Center installation root;
  - whether the modified `D:\Token Piggy Bank` launchers are restored, retained, or superseded;
  - whether the installed SOW artifact must be fully isolated from `D:\multi model terminal app`;
  - how the new deployment schema is authorized relative to the signed freeze;
  - whether llama.cpp and provider-dependent live tests may run;
  - whether a new Git repository or copied `.git` metadata is forbidden, allowed, or replaced by manifest provenance.
- Capture fresh hashes and process/port state before repair.

**Done when:** A versioned operator instruction identifies exact paths, permitted mutations, launch authority, provider/spend limits, and the expected gate/evidence output.

**Verification:** Independent reader can trace every later mutation to one explicit authorization; nothing relies on chat recollection or builder-authored approval.

### P0-02 — Select one canonical Token Center installation

**Problem:** Port 8765 currently runs `D:\Token Piggy Bank\piggybank.py`, while the shell adapter and hardened code live under `Production Workspace\modules\tokencenter`.

**Actions:**

- Choose exactly one canonical runtime root.
- Inventory every launcher, shortcut, shell adapter, scheduled task, startup entry, and documentation reference that can start Token Center.
- Point all authorized launch paths to the chosen root.
- Make startup verify the exact executable, script path, and working directory—not merely that a Python process mentions `piggybank.py`.
- Refuse to adopt a listener whose resolved script path or expected build hash differs.
- Remove or clearly quarantine superseded launch paths under explicit authority.

**Done when:** Starting Token Center from every supported entry point produces one process whose command line and file hash identify the canonical copy.

**Verification:**

```text
Get-CimInstance Win32_Process -Filter "ProcessId = <listener-pid>"
Get-FileHash -Algorithm SHA256 <resolved-piggybank.py>
GET http://127.0.0.1:8765/healthz -> 200
```

Negative test: a different `piggybank.py` already bound to 8765 must be refused, not adopted.

### P0-03 — Repair the broken relocated Token launcher

**Problem:** `D:\Product Software\Start-SovereignTokenCenter.ps1` resolves `piggybank.py` beside itself, but `D:\Product Software\piggybank.py` does not exist.

**Actions:**

- Either remove the unsupported launcher or make it delegate to the canonical launcher using an explicit, verified absolute path.
- Do not depend on an already-running listener to hide the broken path.
- Add a cold-start test with port 8765 empty.
- Add a wrong-listener test with an unrelated or wrong-copy process on 8765.

**Done when:** Cold start succeeds from the supported launcher, and wrong-process adoption fails with a specific diagnostic.

### P0-04 — Implement a real Token Center CSRF protocol

**Problem:** The hardened server accepts any nonempty nonce and a prefix-matched lookalike Origin, while the shipped browser sends no nonce at all.

**Actions:**

- Generate a cryptographically random nonce once per server process.
- Expose it only through the same-origin page/bootstrap response.
- Have `static/app.js` send the exact nonce in `X-CSRF-Nonce` on `/api/refresh`.
- Compare the received nonce using a constant-time comparison.
- Require exact Host equality for the actual bound loopback address and port.
- Require exact Origin equality for the server origin; do not use `startswith`.
- Refuse missing Origin, missing nonce, wrong nonce, lookalike origin, foreign Host, and wrong method/path before calling `state.refresh()`.
- Cap request body size and reject unexpected bodies/content types.

**Done when:** The real browser Refresh action succeeds, and every negative case is rejected without incrementing a refresh counter.

**Required behavioral tests:**

- page/bootstrap obtains the nonce;
- UI request includes the exact nonce;
- missing nonce -> 403;
- arbitrary nonempty nonce -> 403;
- stale nonce from a previous process -> 403;
- `Origin: http://127.0.0.1.evil.example` -> 403;
- wrong Host -> 403;
- valid exact Host + Origin + nonce -> 200 and exactly one refresh;
- refused request -> zero refresh calls.

Delete or replace the current grep-only test; do not count the presence of security words as security behavior.

### P0-05 — Isolate the installed SOW copy from protected source

**Problem:** `modules/sow/.codex/config.toml` pins the MCP server `cwd` to `D:/multi model terminal app/sovereign-orchestration-workspace`.

**Actions:**

- Make MCP configuration resolve to the installed SOW root deterministically.
- Prefer install-time generation from the verified destination root, with the generated file included in the install manifest.
- Scan all runtime/config files, including hidden directories, for absolute references to protected source roots.
- Test module resolution with the protected source temporarily unavailable or renamed in an isolated fixture.
- Test that all runtime writes remain inside declared installed `runtime_writes` locations.

**Done when:** No production configuration or launch command resolves code from the protected development tree, except a provenance field explicitly marked read-only metadata.

**Verification search:**

```text
rg --hidden -n "D:/multi model terminal app|D:\\multi model terminal app" modules/sow \
  -g '!**/docs/**' -g '!**/tests/**' -g '!**/node_modules/**'
```

Expected result: no runtime/config hit; provenance-only hits must be explicitly classified.

### P0-06 — Restore or formally reconcile the protected Token original

**Problem:** `D:\Token Piggy Bank` differs from its Band-0 manifest: two launchers are modified and two handoff files are untracked.

**Actions:**

- Under explicit protected-tree authority, choose one outcome:
  - restore exact Band-0 bytes;
  - authorize a new protected baseline with a signed explanation; or
  - retire the tree and replace every consumer with the canonical installed copy.
- Preserve the pre-repair hashes and diff.
- Do not silently delete or normalize the handoff files.
- Rehash the full protected tree after the decision.

**Done when:** The protected-tree verdict is truthfully one of `MATCHES_BAND0`, `AUTHORIZED_SUCCESSOR_BASELINE`, or `RETIRED_NO_CONSUMERS`, with no ambiguous launch path remaining.

### P0-07 — Fix SOVEREIGN archive provenance

**Problem:** `modules/sovereign/INSTALL-PROVENANCE.json` names the Sovereign archive but records the Distillery archive hash.

**Actions:**

- Recompute the source archive hash from the actual archive.
- Recompute the extracted-content manifest.
- Establish whether the current installed tree actually derives from that archive plus declared changes.
- Replace provenance only through the append/supersede method required by the evidence rules; preserve the false record for audit history if required.
- Verify every lockfile hash and install command claim.

**Done when:** Archive identity, archive SHA-256, extracted file manifest, installed tree, and declared post-install changes reconcile exactly.

### P0-08 — Make SOVEREIGN's advertised self-test runnable from a clean artifact

**Problem:** `Test-Sovereign.ps1` requires `ui/ui_shell/package.json`, `tests`, and `tests_product`, but the installed tree and production archive omit them.

**Actions:**

- Decide whether these inputs belong in the production artifact or whether the self-test must validate only shipped content.
- Package every required test/build input, or rewrite the self-test contract to use shipped validation assets.
- Ensure the test runs in a clean extraction without relying on files outside the archive.
- Separate read-only verification from build/compile steps that mutate the extraction.
- Run build-producing checks only in a disposable copy.

**Done when:** A clean archive extraction can execute the documented test command successfully and reproducibly, with no missing-path failure.

---

## P1 — product correctness and integration

### P1-01 — Repair Debate pause/resume synchronization

**Problem:** `test_reasoning_filter_and_empty_response_retry` fails reproducibly after immediate pause/resume.

**Actions:**

- Define pause semantics: request accepted, generation interrupted, turn-end emitted, and orchestrator quiescent.
- Add a pause generation/epoch or acknowledgment barrier.
- Do not allow a new `run_turn` to clear an interrupt belonging to the prior turn.
- Associate `turn_start`, token, `turn_end`, and metrics events with a stable turn/generation id.
- Make resume wait for or explicitly supersede the paused generation.
- Drain or discriminate stale WebSocket events in the client contract.

**Done when:** The failing smoke test passes at least 100 repeated runs, including pause during streaming, pause before first token, immediate resume, and repeated pause/resume cycles.

### P1-02 — Make shell npm detection accurate without shell execution

**Problem:** Python `subprocess.run(["npm", "--version"])` returns WinError 2 on this Windows host even though npm is installed.

**Actions:**

- Resolve the absolute Node executable.
- Resolve npm's JavaScript CLI entry point or another non-shell, absolute executable path permitted by policy.
- Launch with an argv array; do not use `shell=True`, `cmd.exe`, `.cmd`, or PowerShell from application code.
- Distinguish `not installed`, `installed but prohibited launch shape`, and `probe failed`.
- Add Windows tests using the actual installation shape and a fixture with spaces in the path.

**Done when:** Shell preflight reports the installed npm version truthfully and the no-shell-launch policy remains satisfied.

### P1-03 — Make shell lifecycle tests hermetic

**Problem:** Three shell tests fail when a valid Distillery already owns its declared port.

**Actions:**

- Give test adapters ephemeral readiness/identity endpoints.
- Mock or inject probe results for pure state-machine tests.
- Add separate explicit tests for `EXTERNAL` adoption.
- Never assume production ports are empty in a unit/component suite.
- Ensure fixtures stop every process they create and verify ports closed.

**Done when:** The full shell suite passes whether ports 5184/8765 are empty or occupied by valid external services.

### P1-04 — Make the canonical registry canonical in use

**Problem:** The registry builder exists, but production selectors still consume hard-coded model lists.

**Actions:**

- Identify every model/provider selector: roster, OpenCode, conductor, worker picker, scheduler, fallback logic, and UI projection.
- Define one immutable registry interface for those consumers.
- Remove independent `_REASONING_MODELS`, `_CODER_MODELS`, and equivalent production lists, or make them inputs owned by the canonical registry.
- Preserve explicit ordering/preference semantics in registry fields rather than hidden tuple order.
- Add a negative test that fails if a production selector names a model/provider not sourced from the registry.
- Add a consumer coverage report generated from imports/calls, not prose.

**Done when:** Every production selector receives its candidates from the canonical registry, and deleting a registry entry removes it from every surface in one test run.

### P1-05 — Implement honest provider discovery

**Problem:** Only Ollama is live-discovered; other registry rows are seeds presented alongside discovered state.

**Actions:**

- Separate `configured`, `installed`, `authenticated`, `enumerated`, and `available` states.
- Implement bounded, non-spending CLI inventory probes for each authorized provider where possible.
- Mark providers with no safe inventory surface as `NOT_MEASURED`, not discovered.
- Record probe timestamp, command identity, exit status, and parser version.
- Prevent seed presence from becoming availability.

**Done when:** Every registry row carries an explicit provenance/state distinction and UI/selector behavior respects it.

### P1-06 — Reconcile llama.cpp capabilities with implementation

**Problem:** `capabilities()` reports streaming, while `generate()` forces non-streaming and no stream method exists.

**Actions:**

- Either implement a bounded streaming API with cancellation and tests, or set `stream: false` everywhere.
- Define the backend protocol so each advertised capability maps to a callable operation.
- Add contract tests that enumerate capabilities and invoke each advertised operation.
- Exercise negative HTTP, timeout, malformed response, cancellation, and server-exit paths.

**Done when:** Capability introspection and executable methods are bijective for Ollama and llama.cpp.

### P1-07 — Establish one eviction authority

**Problem:** Evidence says `--models-max` is set, but the manifest omits it; planner and router authority are unresolved.

**Actions:**

- Decide whether the planner or llama.cpp router owns model eviction.
- If planner-owned, configure router capacity so it cannot independently evict within the planner's admitted concurrency.
- If router-owned, remove planner eviction and consume router state authoritatively.
- Correct the manifest, tests, and evidence to one consistent policy.
- Add concurrency tests at and above the admitted bound.

**Done when:** Exactly one component can initiate eviction, and a behavioral test proves no unrequested transition under concurrent load.

### P1-08 — Stabilize VRAM admission

**Problem:** Picker availability changes with a 12,288 MB stand-in budget and transient resident-model state; the test was not marked host-coupled.

**Actions:**

- Obtain a real, auditable host VRAM budget or require an explicit operator value.
- Record the provenance and freshness of the budget.
- Treat resident usage separately from total capacity.
- Mark host-sensitive tests `host_coupled` and isolate them from deterministic suites.
- Add cases for unknown capacity, overcommitted resident state, model unload between reads, and concurrent load.

**Done when:** Picker state is stable for a fixed measured snapshot, and host changes produce explicit state transitions rather than flaky suite results.

### P1-09 — Wire resource accounting into real surfaces

**Problem:** Metrics exist in isolated backend code but no existing product surface consumes the required model/artifact/load/context/KV/resource state.

**Actions:**

- Add metrics to the shared backend protocol.
- Implement equivalent honest metrics for Ollama and llama.cpp, using `NOT_MEASURED` where unavailable.
- Project metrics through the shell/control-plane API.
- Render them in the existing Token Center or shell status surfaces.
- Include timestamp, source, staleness, and measurement status.
- Never convert missing measurements into zero.

**Done when:** A live local backend request updates the existing UI with independently verifiable model, runtime, load, and resource fields.

### P1-10 — Repair per-combination context measurement

**Problem:** G102 has one blanket NOT_MEASURED paragraph rather than per model/context records.

**Actions:**

- Define a row schema for each backend/model/context combination.
- Record requested context, initialized context, processed prompt tokens, KV/cache measurement, outcome, and reason for any `NOT_MEASURED` field.
- Execute supported combinations under the authorized local runtime.
- Keep unsupported combinations explicit and separate.

**Done when:** Every required combination has a complete row, and each value is measured or individually marked NOT_MEASURED with a reason.

### P1-11 — Upgrade Electron to a supported line

**Problem:** Electron 31.7.7 is end-of-support.

**Actions:**

- Select a currently supported Electron major compatible with Node, node-pty, xterm, and the host OS.
- Update lockfiles through the authorized install process.
- Verify downloaded Electron artifacts against official hashes.
- Rerun the full 1,108-test Node suite.
- Rerun real Electron startup, self-check, ConPTY, IPC, teardown, and renderer security tests.
- Review Electron breaking changes and security configuration.

**Done when:** The packaged desktop reports a supported Electron version and all component plus in-Electron checks pass.

### P1-12 — Add consistent local HTTP security headers

**Problem:** Distillery and Token Center omit CSP, `X-Content-Type-Options`, and Referrer-Policy.

**Actions:**

- Add a restrictive CSP appropriate to each static page.
- Add `X-Content-Type-Options: nosniff`.
- Add `Referrer-Policy: no-referrer`.
- Use `Cache-Control: no-store` for state/health JSON and sensitive bootstrap data.
- Confirm no CORS allowance is introduced.

**Done when:** Header tests validate every route and browser functionality remains intact.

---

## P1 — packaging, freeze, and provenance

### P1-13 — Resolve deployment-schema freeze drift

**Problem:** `deployment-manifest.schema.json` matches the frozen schema glob but is absent from the signed manifest.

**Actions:**

- Classify it as one of:
  - part of a newly authorized frozen baseline;
  - an authorized post-freeze amendment with a naming pattern excluded from the original glob; or
  - an unauthorized addition to be removed under authority.
- Do not rename or regenerate merely to make tests green; preserve the operator decision chain.
- Update the manifest generator, amendment authorization map, tests, and signed status coherently.
- Run `compute_manifest.py --check` from both the source repository and a clean packaged artifact.

**Done when:** Freeze membership is disjoint and intentional, the recorded integrity hash recomputes exactly, and the signature status truthfully reflects the change.

### P1-14 — Separate source-repository tests from installed-artifact tests

**Problem:** Installation excludes `.git`, while several tests require `git ls-files` and tracked blobs.

**Actions:**

- Define a source test profile that may require the real source `.git` metadata.
- Define an installed-artifact profile that verifies a signed content manifest and never calls Git.
- Remove Git-dependent tests from the installed profile.
- Do not `git init` the installed copy to manufacture provenance.
- Make CI/release output identify which profile ran.

**Done when:** Both profiles pass in their intended environments, and a clean installed artifact can be validated without a repository.

### P1-15 — Build one reproducible release-validation command

**Problem:** Current validation is fragmented across suites and some tests generate evidence/build outputs in place.

**Actions:**

- Provide one documented command that runs against a clean extraction or disposable copy.
- Disable provider calls by default.
- Send caches, temporary files, receipts, screenshots, and generated evidence to a disposable directory.
- Run static parsing, manifests, component tests, security contracts, launch/stop smoke tests, and orphan/port checks.
- Emit one machine-readable result containing exact command versions, counts, skips, and artifact hashes.
- Fail if required content is missing or any test is silently deselected.

**Done when:** Two consecutive runs from the same artifact produce equivalent results and leave the artifact byte-identical.

---

## P2 — test and acceptance completion

### P2-01 — Re-run all deterministic component suites

**Required suites after repair:**

```text
shell: full suite in an isolated evidence/temp root
modules/distillery: full pytest suite
modules/tokencenter: full pytest suite plus new browser/server CSRF tests
modules/debate: full pytest suite plus repeated pause/resume stress
modules/sow/apps/desktop: full npm test
modules/sow: all non-live, non-host-coupled Python tests
modules/sovereign: repaired clean-artifact self-test
```

**Done when:** Zero failures, every skip is enumerated with a valid authority/environment reason, and no test changes product or protected-tree bytes.

### P2-02 — Run shell cold-start and external-adoption acceptance

**Scenarios:**

- all modules stopped;
- valid Distillery/Token externally running;
- wrong identity on a declared port;
- module start, readiness, identity, open, stop, restart;
- SOW startup-test path with required environment and fresh receipt;
- abrupt child/grandchild termination and Job Object cleanup;
- shell crash/exit leaves no shell-owned child;
- second shell instance and occupied shell port refusal.

**Done when:** UI state, API state, process ownership, and port state agree throughout every scenario.

### P2-03 — Run llama.cpp Band tests under explicit launch authority

**Required demonstrations:**

- version/pin and exact binary hash;
- CPU path if contractually required;
- CUDA path and offload state;
- server readiness and identity at 5183;
- OpenAI-compatible generate request;
- initial, load, unload, cancel, shutdown, and negative paths;
- LRU/concurrency/eviction behavior;
- shell-only launch ownership;
- post-test zero orphan processes and closed 5183.

**Done when:** G70–G72 and G75–G79 are behaviorally demonstrated, 9a/9b prerequisites are satisfied, and G73 remains independently true. A description or NOT_RUN file is not a passing result.

### P2-04 — Run local end-to-end Band-10 acceptance

**Required one-session chain:**

- start shell from clean state;
- exercise SOVEREIGN;
- exercise Debate;
- open Distillery without compute;
- exercise Token refresh securely;
- start SOW through the governed shell path;
- establish Conductor readiness;
- execute a local Ollama or authorized llama.cpp worker turn;
- verify logs, metrics, lifecycle, and cleanup;
- stop everything the run owns.

**Done when:** Every step is observed in the product, correlated by session/run id, and captured as immutable evidence. No step may pass because a named file exists.

### P2-05 — Run provider-dependent acceptance only under explicit authority

**Actions:**

- Name authorized providers, models, maximum turns, and spend ceiling.
- Capture pre-run subscription/billing state if accessible.
- Run only the minimum required live legs.
- Record whether bytes were typed, submitted, delivered, and billed as separate facts.
- Stop on any unexpected provider or spend condition.

**Done when:** Each provider goal has real behavioral evidence or remains explicitly NOT_RUN. Zero-spend must be reconciled against both workspace records and provider/account evidence where available.

### P2-06 — Complete rollback and protected-tree watch demonstrations

**Actions:**

- Close the authorized fs-watch window with a valid replacement artifact.
- Demonstrate rollback from a deliberately induced, bounded failure in a disposable copy.
- Verify five protected roots against their correct baselines/handover allowances.
- Verify zero new/removed/changed files outside authorized scope.

**Done when:** G117/G118 are behaviorally established and protected-tree integrity is independently rehashed.

---

## P2 — evidence, oracle, and ledger repair

### P2-07 — Replace weak goal predicates

**Problem:** 58 TRUEs rest on trivial or self-referential predicates; structural predicates also overclaim behavior.

**Actions:**

- For every goal, declare its type: behavioral, static contract, evidence integrity, authority, or environment observation.
- Replace file-existence and keyword predicates when the goal demands behavior.
- Make live-demonstration goals consume machine-observed results from the actual product.
- Make security predicates execute positive and negative cases.
- Make claims about tests invoke or cryptographically bind the actual test output, not a sentence saying tests passed.
- Add mutation/falsification tests proving each predicate goes red when the required behavior is broken.
- Independently review the new oracle before using it to score the build.

**Done when:** A TRUE has a documented uniform meaning within its goal type, and no predicate can be satisfied by authoring the words it searches for.

### P2-08 — Reconcile RUN-LOG, oracle, report, and ledger

**Problem:** G3/G64 are logged TRUE but oracle-FALSE; G34/G35 are logged NOT_RUN but oracle-TRUE; G73 contradicts the “G70–G80” shorthand.

**Actions:**

- Produce one reconciliation table for G1–G124 with current behavior, evidence, oracle result, run-log state, and gate dependency.
- Correct the reporting layer without rewriting historical evidence.
- Mark superseded claims explicitly.
- Remove range shorthand that hides exceptions.

**Done when:** Every goal has one current status and historical disagreements remain auditable.

### P2-09 — Correct backfill assurance

**Problem:** Fifty-eight goals were backfilled in one operation; only nine used substantive predicates.

**Actions:**

- Re-evaluate every backfilled goal under the repaired predicate.
- Prioritize the 38 trivial/self-referential backfills.
- Record the actual execution timestamp separately from the backfill timestamp.
- Do not treat artifact mtime or backfill time as proof of historical execution.

**Done when:** Each retained TRUE has independent evidence of the required behavior or is downgraded.

### P2-10 — Freeze gate evidence correctly

**Problem:** 7a/7b have ten hash drifts and later candidates cite mutable live paths despite E-7c.

**Actions:**

- Copy every gate artifact into a gate-local immutable evidence directory after final write.
- Hash the frozen copy, never the mutable source path.
- Record source path, source hash, frozen path, frozen hash, copy time, and producer.
- Reject a gate containing mutable evidence references.
- Recompute all hashes independently before submission.

**Done when:** Every candidate rehashes cleanly and remains clean after subsequent product/evidence activity.

### P2-11 — Fix line-count accounting

**Problem:** The counter assigns zero to new files when an area has no configured baseline. Package A/B totals were materially understated, and `llamacpp.json` is 53/45.

**Actions:**

- Treat a missing baseline file as zero lines, so all new-file lines count as additions.
- Compare removed files as full deletions.
- Keep Package A and B baselines/budgets separate.
- Add fixtures for new, removed, renamed, binary, generated, and excluded files.
- Recompute both packages independently.
- Resolve the `llamacpp.json` cap breach by reducing authorized product change or obtaining an explicit waiver; do not alter counting rules to hide it.

**Done when:** Independent and builder tools agree per file and per area, with Package B honestly within authority or explicitly waived.

### P2-12 — Replace G120 diff classification

**Problem:** `UNEXPECTED: 0` omitted at least ten known product changes.

**Actions:**

- Compute the complete diff from authoritative before-A/before-B/provenance baselines.
- Include new, removed, modified, renamed, generated, and runtime-state files.
- Classify each exact path once with package, area, authority, and expected/unexpected status.
- Fail on any unclassified path.
- Cross-check counts against the line-count tool and protected manifests.

**Done when:** Independent re-computation yields the same complete path set and `UNEXPECTED: 0` only if the set truly is empty.

### P2-13 — Correct the 9-series ledger/report

**Problem:** The report says 9a through 9j, but 9a, 9b, and 9i are absent.

**Actions:**

- Correct the narrative claim immediately through an append/supersede record.
- Do not create placeholder gates merely to fill numbering.
- Submit 9a/9b only after llama prerequisites are behaviorally satisfied.
- Determine whether 9i is required, intentionally omitted, or a reporting error; document the governing mapping.

**Done when:** Report, ledger keys, goal dependencies, and evidence directories agree exactly.

### P2-14 — Re-evaluate all gate candidates independently

**Actions:**

- Rehash all evidence.
- Confirm whole-object snapshot witnesses.
- Confirm no candidate depends on mutable paths, false line counts, missing goals, or circular oracle claims.
- Re-run the repaired behavioral goals.
- Produce an independent gate-by-gate verdict with explicit blockers.

**Done when:** A reviewer—not the builder/oracle author—can promote only gates whose full acceptance conditions are satisfied. No bulk promotion.

---

## P3 — maintenance and hardening

### P3-01 — Run an authorized dependency/security scan

**Actions:**

- Scan locked Python and npm dependencies without silently upgrading them.
- Record scanner version, advisory database timestamp, package/version, severity, reachability, and disposition.
- Prioritize Electron/Chromium, websocket, FastAPI/uvicorn, Flask, jsonschema, and native node-pty dependencies.
- Rebuild and retest after authorized upgrades.

**Done when:** No unreviewed critical/high advisory remains, or each has a signed risk acceptance and compensating control.

### P3-02 — Remove deprecated jsonschema resolver use

**Problem:** SOW tests emit 61 warnings, including `jsonschema.RefResolver` deprecation.

**Actions:**

- Migrate to the `referencing` API.
- Pin compatible dependency versions.
- Add schema resolution tests for local refs, missing refs, and malicious/remote refs.

**Done when:** Full SOW suite emits no resolver deprecation and schema behavior is unchanged.

### P3-03 — Add version/build identity to every service

**Actions:**

- Expose build id, artifact hash, and schema version in health responses.
- Have the shell identity probe validate expected build identity, not only generic JSON keys or HTML markers.
- Display source/install mismatch explicitly.

**Done when:** The shell refuses a healthy-but-wrong build on a declared port.

### P3-04 — Add staleness semantics to Token metrics

**Actions:**

- Define collector freshness thresholds.
- Display collected-at age and stale/partial/unknown state.
- Distinguish configured provider, observed provider, and currently available provider.
- Test clock skew and collector failure.

**Done when:** Old telemetry can never appear current or available merely because its last numeric value exists.

### P3-05 — Make logging/metrics contracts uniform

**Actions:**

- Define shared required log fields, redaction, rotation, size bounds, and timestamps.
- Define shared backend metrics fields.
- Add negative tests with credentials, paths, binary data, oversized values, and malformed provider output.
- Verify every displayed/logged surface uses the same redaction boundary.

**Done when:** Ollama, llama.cpp, shell, Debate, Distillery, and Token Center meet one measurable logging/metrics contract.

---

## Final exit checklist

All boxes must be satisfied before recommending promotion:

- [ ] Canonical Token runtime chosen; all launch paths and process identity agree.
- [ ] Token UI refresh succeeds with a real nonce; all CSRF negative cases fail closed.
- [ ] No installed SOW runtime/config path reaches protected source.
- [ ] Protected Token tree reconciled under explicit authority.
- [ ] Sovereign archive provenance is correct.
- [ ] SOVEREIGN clean-artifact self-test is runnable and green.
- [ ] SOW freeze check is green with valid authority provenance.
- [ ] Installed-artifact tests do not require fabricated Git metadata.
- [ ] Debate pause/resume stress is green.
- [ ] Shell npm preflight is truthful.
- [ ] Shell tests are independent of operator-owned port state.
- [ ] Canonical registry feeds every production selector.
- [ ] llama.cpp capability, streaming, and eviction contracts are coherent.
- [ ] Resource/context metrics are wired to existing surfaces.
- [ ] Electron is on a supported release line.
- [ ] All deterministic suites are green with enumerated skips.
- [ ] Local one-session Band-10 acceptance is complete.
- [ ] Authorized llama.cpp/provider legs are complete or truthfully remain NOT_RUN.
- [ ] Rollback and protected-tree watch demonstrations are complete.
- [ ] Goal oracle predicates have independent behavioral meaning.
- [ ] RUN-LOG, oracle, report, and ledger reconcile for all 124 goals.
- [ ] Backfilled goals are independently re-evaluated.
- [ ] Every gate hashes immutable gate-local evidence.
- [ ] Line counts and diff classification recompute independently.
- [ ] 9a/9b/9i reporting is resolved without placeholder gates.
- [ ] Zero-spend claim is bounded to evidence actually available.
- [ ] Independent reviewer issues individual gate verdicts.

## Recommended execution batches

### Batch 1 — safety and canonical paths

P0-01 through P0-06. Do not start live acceptance before this batch is closed.

### Batch 2 — packaging and deterministic correctness

P0-07, P0-08, P1-01 through P1-15. End with the reproducible release-validation command.

### Batch 3 — local behavioral acceptance

P2-01, P2-02, P2-04, and the local/non-spending parts of P2-03.

### Batch 4 — authorized live acceptance

Remaining P2-03, P2-05, and P2-06 under explicit launch/provider authority.

### Batch 5 — evidence and gate reconstruction

P2-07 through P2-14. Evidence is rebuilt after behavior is correct, not before.

### Batch 6 — maintenance closeout

P3-01 through P3-05, final exit checklist, independent review, and only then gate promotion.

