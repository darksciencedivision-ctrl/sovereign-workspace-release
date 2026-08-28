# COMPLETION LOOP CHECKPOINT

- Directive: Sovereign x Grounded Distillery Completion Loop v1.0
- Repository: ryguy-pixel/Sovereign-Distillery (D:\Sovereign-Grounded-Distillery)
- Branch: completion/build-completion-loop (child of merged remediation PR #2)
- Base/HEAD: 550bc0cbb4b91566684dd6ccdd14abe3609e0874 (origin/main)
- Historical remediation lineage 5ff6f56e is contained in origin/main; pure merge, no content delta.

## F-00 RESULT: CLOSED (pending commit)

Measured state:
- origin/main = 550bc0c (merge of PR #2); no open PRs; gh authenticated.
- Local main stale at 45cc79f; intentionally NOT fast-forwarded or pushed (no direct main pushes).
- Worktree clean. Full regression at baseline: 43 passed, 154 subtests passed (Python 3.14.6, exit 0).

## NEXT

F-01 adversarial delta audit over 44f69077..5ff6f56e (historical review range preserved),
plus inspection of merge commit 550bc0c (verified content-free).

## RULES REMINDER

- Never push to main; never force push; never weaken tests.
- Fixture evidence is SYNTHETIC_FIXTURE, never MEASURED.
- Update LOOP_STATE/PUNCH_LIST/FINDINGS/EVIDENCE_INDEX after every accepted commit.

## ITERATION 2-3 LOG
- F-01 CLOSED: delta 44f69077..5ff6f56e audited adversarially; no CRITICAL; HIGH FND-001 routed to F-05.
- Encoding defect introduced and repaired same session: PS 5.1 UTF8 BOM broke repo-wide JSON parse test; all loop JSON now BOM-free.
- Regression: 43 passed, 160 subtests passed (Python 3.14.6).
- NEXT: F-05 HG-3 state supersession (HIGH finding closure), then F-02 sweep of remaining routed findings via their designated F-items.

## ITERATION 4 LOG
- F-05 CLOSED: gate/status_chain.py (explicit supersedes edges, cycle/dangling/duplicate/tamper fail-closed, trust anchors); schema/gate_status_record.json; runs/HG-3/CURRENT_STATUS.json (sha256-bound supersession of both BLOCKED_PRELOAD emitters, authority D-HW-01).
- FND-001 (HIGH) and FND-007 (LOW) closed. Open HIGH now ZERO.
- Regression: 56 passed, 172 subtests passed.
- NEXT: F-02 sweep continues via designated items; next selected P0: F-04 version identity matrix.

## ITERATION 5 LOG
- F-04 CLOSED: docs/VERSION_MATRIX.json canonical matrix; distillery.identity runtime resolver (git_head never statically pinned; snapshot bundle digest verified); grounded CLI 'version' subcommand consumes it.
- Package stays 1.1.0rc3 by explicit recorded decision (thesis and package namespaces independent).
- Regression: 66 passed, 180 subtests passed.
- NEXT: F-06 revoked contract reconciliation.

## ITERATION 6 LOG (F-06 CLOSED)
- F-06 CLOSED: authorized admission revocation (reason=revoked), revoked_keys/lineage_id binding, admission_state_hash + assert_snapshot_matches_registry freshness gate; schema/source_admission.json gains reason property with minimal diff restored.
- Repaired inherited broken final test (dead placeholder + inverted conditionals that never invoked the functions under test) into an honest seam characterization: seal trusts the snapshot blob; the caller-side freshness gate is the fail-closed control.
- Encoding guard: PS 5.1 Set-Content BOM defect caught and eliminated pre-commit (EF BB BF scan on all touched files).
- Regression: 74 passed, 180 subtests passed (Python 3.14.6); py3.12 byte-compile of touched files OK.
- NEXT: F-08 generalized exclusion graph generator+purge (closes FND-004).

## ITERATION 7 LOG (F-08 CLOSED)
- F-08 CLOSED: exclusion core gained explicit node-shape validation and an illegal-cycle policy (Kahn peel; rejects self-loops, closed cycles, cycles disconnected from the excluded source, and cycles upstream of the excluded root).
- tests/test_exclusion_graph.py: malformed-input classes, 4 contradictory cycle topologies, legal diamond control, 50-seed randomized DAG purge-property campaign, single-node mutation tamper check.
- Test defect caught during round: property closure originally walked ancestors instead of descendants; fixed against module contract before commit (module was correct).
- Regression: 85 passed, 230 subtests passed (Python 3.14.6); py3.12 byte-compile OK.
- NEXT: F-09 historical per-item vector bridge (closes FND-005).

## ITERATION 8 LOG (F-09 CLOSED)
- F-09 CLOSED: gate/historical.py reference_vector per-item bridge with supplying-record binding and deterministic tie policy; legacy aggregate-only rows cannot supply item identity; ingest AND read-side finite validation (Director review caught disk-bypass NaN hole; closed pre-commit).
- tests/test_historical_bridge.py: 9 tests incl. cross-bundle max selection, tie determinism, suite mismatch, order alignment into paired_gate, stored-line tamper changing resolution.
- Regression: 94 passed, 237 subtests passed (Python 3.14.6); py3.12 byte-compile OK.
- NEXT: F-03 formal build-completion state contract.

## ITERATION 8 LOG (state-integrity repair + independent verification)
- Concurrent completion-loop instance detected and reconciled: it landed 56e6b3c (F-06) and a333565 (F-08) while this session held F-06; this session accepted Tier-0 measured state instead of double-implementing (FND-010).
- Independent MEASURED verification of foreign units: post-F-06 74 passed/180 subtests; post-F-08 85 passed/230 subtests (python -m pytest -q, exit 0, Python 3.14.6).
- Repairs: LOOP_STATE.head PRE_COMMIT placeholder -> real SHA; PUNCH_LIST implementation_commits backfilled for F-04..F-08; invalid status SELECTED_NEXT (F-03) -> UNASSESSED; FND-003 closed as CLOSED_BY_F06; FND-009 LOW recorded (seal trusts snapshot blob; mitigation structurally enforced at F-07); trailing newlines restored on schema/source_admission.json, source_admission/__init__.py, gate/status_chain.py, tests/test_revocation_semantics.py.
- Added persistence/reload adversarial test: registry rebuilt from snapshot events preserves REJECTED/revoked semantics and refuses old eligibility evidence (test_revocation_survives_persistence_reload).

## ITERATION 9 LOG (F-09 CORRECTION)
- AUTHORITY CONFLICT FOUND AND RESOLVED: iteration-8 reference_vector violated GR-9 hard invariant (no per-item maxima across checkpoints/runs). Iteration-8 LOCAL_PASS revoked per directive sec 32.
- Corrected semantics: governing bundle chosen by reference() governance rule; values drawn from ONE latest covering promotion run; supply_rule=SINGLE_GOVERNED_RUN_NO_COMPOSITE recorded in every binding.
- New adversarial tests: cross-bundle max forbidden, composite stitching within bundle forbidden, unqualified bundles fail closed, latest-covering-run selection, genuine n-tiebreak.
- Regression: 98 passed, 237 subtests passed (Python 3.14.6); py3.12 byte-compile OK.
- NEXT: F-03 formal build-completion state contract.

## CONCURRENCY EVENT RECORD
- recorded_at: 2026-08-23T07:24:35.428769Z
- During R4 post-commit inspection, a SECOND concurrent opencode session was observed actively writing this repository (PUNCH_LIST/EVIDENCE_INDEX/newline normalization/new persistence-reload test), committing as d2ca6c6 on top of a864460 approximately 90 seconds after detection.
- Its delta is coherent, references prior commits, adds an adversarial persistence-reload test for F-06, and full regression stays green (98 passed, 237 subtests).
- Disposition: PRESERVED (disk state wins). Dual-writer lost-update races on ledger files remain a live risk; mitigation adopted: re-read immediately before every ledger write, tight RMW windows, verify-after-write. Operator recommendation: serialize completion-loop agents to one writer.

## ITERATION 10 LOG (F-03 CLOSED)
- F-03 CLOSED: ops/loop_state.py formal loop-state contract (schema validators for LOOP_STATE/PUNCH_LIST, ISO-UTC enforcement, status/priority enums, duplicate-id rejection) plus StateFileLock exclusive O_EXCL lock with deterministic stale-owner takeover and update_json_atomically locked RMW (post-mutation validation leaves file untouched).
- Platform defect caught by hostile testing: os.kill(pid,0) TERMINATES on Windows (TerminateProcess), killing pytest silently mid-suite; replaced with OpenProcess+GetExitCodeProcess liveness probe. Second defect: terminated-but-handle-referenced PIDs resolve alive; fixed via STILL_ACTIVE exit-code check.
- SECOND CONCURRENCY EVENT: while running R5 regression, concurrent session began F-07 (corpus/, schema/corpus_admission.json, tests/test_corpus_admission.py, docs/VERSION_MATRIX.json) in-tree, uncommitted. Their files untouched; transient version-identity failure during overlap resolved itself once their edit settled (10 passed standalone). My round committed in isolation.
- Regression: 98 passed, 237 subtests passed pre-overlap; version identity re-verified post-overlap.
- ESCALATION RECOMMENDATION: two active writers on one branch violates sec 28.2 single-control-plane discipline; recommend operator serialize completion-loop agents or assign disjoint seams.

## ITERATION 11 LOG (F-07 CLOSED)
- F-07 CLOSED (commit 56f66e6): corpus/ normative admission package - deterministic five-category scrub scan (API_KEY/CREDENTIAL/EMAIL/HOSTNAME/LOCAL_PATH), hash-bound redaction placeholders, structural registry-freshness gate (offline replay rebuilds AdmissionRegistry from snapshot events), fail-closed on UNKNOWN/REJECTED/revoked sources, forged/stale snapshots, surviving secrets, client-scope violation, provenance mismatch; tamper-evident record_hash; deletion_lineage_ids bind examples to exclusion-graph purge; schema/corpus_admission.json registered in VERSION_MATRIX.
- Disjoint-seam discipline held with concurrent writer: implementation commit isolated from runs/completion-loop; this evidence commit uses ops.loop_state locked atomic updates (their F-03 tooling) after their 2f47745 landed.
- Their escalation recommendation (serialize completion-loop agents or assign disjoint seams) is acknowledged and surfaced to the operator.
- Full regression at closure: 119 passed, 240 subtests passed, exit 0 (Python 3.14.6, MEASURED).

## ITERATION 12 LOG (F-12 CLOSED)
- F-12 CLOSED: runstate/ durable orchestration spine - nine linear semantic boundaries CREATED..PROMOTION_READY, terminal COMPLETED/FAILED/CANCELLED/BLOCKED immutable, per-mutation atomic write with flush+fsync (directory sync best-effort POSIX; platform limitation documented in-source), whole-record integrity_hash tamper detection, artifact refs with hashes, retry budget (default 3) gating TRAINING resume, authorization validation, failure classifications, resume_pointer to last successful boundary.
- Crash-recovery proven at every boundary via subTests; adversarial: identity mismatch, input drift, missing artifact, terminal immutability, budget exhaustion, unknown failure class, forged stage jump rejected by integrity chain.
- Full regression at closure: 128 passed, 248 subtests passed, exit 0 (Python 3.14.6, MEASURED).

## ITERATION 13 LOG (F-13 + F-14 CLOSED)
- F-14 CLOSED: preflight_trainer reads live registry/grounded/trainer.json; unassigned GND-TRAINER-PRIMARY yields BLOCKED_HARDWARE_CAPACITY (fail-closed SUCCESS); dev machine structurally refused as canonical fallback (registry asserts canonical_primary_trainer=false); synthetic assigned-trainer fixtures prove PASS at >=24GiB measured floor and BLOCK below it.
- F-13 CLOSED: train/runner.py TrainingRunControlPlane drives runstate boundaries CREATED..PROMOTION_READY and stops before real promotion with promotion_eligibility=FORBIDDEN_WITHOUT_MEASURED_EVIDENCE_AND_HUMAN_AUTHORITY; FixtureBackend deterministic per (run,student,corpus,spec,seed), every artifact SYNTHETIC_FIXTURE_ONLY labeled; assert_measured_evidence mechanically rejects fixture evidence from measured slots; RealBackendAdapter refuses canonical compute unless preflight PASS and separate execution contract authorized.
- Adversarial: input drift on resume rejected; blocked run preserves last_successful_boundary=CREATED; unknown student / missing authorization / unmeasured VRAM all fail closed.
- Full regression at closure: 140 passed, 248 subtests passed, exit 0 (Python 3.14.6, MEASURED).

## ITERATION 14 LOG (F-18 CLOSED)
- F-18 CLOSED: source_admission/d9.py structural three-way separation (research finding != system recommendation != human authorization); apply_operator_decision fails closed on unsigned fields, forbidden self-authorization sentinels (system/research/recommendation/agent/unsigned), unsigned-signature flag, invalid decision classes, no-op decisions, mismatched findings; valid signed decisions record D9:-prefixed authority and revocation reason=revoked.
- Environment note discovered and applied: `with assertRaises(X), subTest(...)` combined-context ordering intercepts the exception under CPython 3.14 pytest - repo convention is subTest-first ordering (now used).
- Full regression at closure: 146 passed, 256 subtests passed, exit 0 (Python 3.14.6, MEASURED).

## ITERATION 15 LOG (F-15 CLOSED)
- F-15 CLOSED: ops/operator_cli.py distillery entry point (console script registered alongside grounded) exposing status/validate/source-status/corpus-preflight/exclusion-verify/trainer-status/trainer-probe/hg3-preflight/g2-preflight/run-plan/run-status/run-resume/run-dry-run/evidence-verify/candidate-status; structured JSON output; NO --force anywhere; fail-closed refusals exit-visible (stale snapshot refusal, terminal-run non-resumability proven as correct outcomes); packaging include list repaired to ship corpus* and runstate*.
- Full regression at closure: 153 passed, 256 subtests passed, exit 0 (Python 3.14.6, MEASURED).

## ITERATION 16 LOG (F-17 CLOSED)
- F-17 CLOSED: source_admission/dossier.py typed dossiers; REFERENCE_RESEARCH performed against official primary sources only (HF official model cards; ai.google.dev Gemma docs): Qwen2.5-14B-Instruct verified Apache-2.0 -> RECOMMEND_ELIGIBLE (HIGH mapping confidence); google/gemma-4-26B-A4B-it verified Apache-2.0 WITH supplemental Gemma-4 license + Prohibited-Use policy pages -> RECOMMEND_ELIGIBLE with mandatory prohibited-use operator review ambiguity; qwen3.8:27b quantization producer chain unverified and gateway-frontier artifact unidentified -> INSUFFICIENT_EVIDENCE. runs/source-admission/dossiers.json generated (authorizes_admission=false on every record; operator decisions unsigned).
- Type-confusion hole closed in d9.apply_operator_decision: research attachment must be isinstance(ResearchFinding) so dossier/recommendation objects can never ride the decision path.
- Unbound artifacts become honest INSUFFICIENT_EVIDENCE dossiers (never guesses); exact-digest binding enforced.
- Full regression at closure: 158 passed, 257 subtests passed, exit 0 (Python 3.14.6, MEASURED).

## ITERATION 17 LOG (F-22 CLOSED)
- F-22 CLOSED: sovereign/teachers.py against the live 43-teacher registry - deterministic validated parsing (unique model_ids, unique teacher_order, count parity, schema pin); smallest-to-largest plan over the 12 teachers with measured GGUF general.parameter_count; remaining 31 EXPLICITLY classified UNORDERED_MISSING_PARAMETER_METADATA with skip reasons (never silently interleaved, never invented); field provenance separates MEASURED_FROM_ARTIFACT / DERIVED_LABEL / UNKNOWN_NOT_INVENTED / UNKNOWN_NOT_YET_HASHED; license_class UNKNOWN blocks teacher use even when source admission is ELIGIBLE (verified license required); deterministic capability-delta evidence path binding.
- No model training performed under F-22 (directive boundary respected).
- Full regression at closure: 164 passed, 257 subtests passed, exit 0 (Python 3.14.6, MEASURED).

## ITERATION 18 LOG (F-20 CLOSED)
- F-20 CLOSED: tools/raw_source_classification.py encodes the previously-external classification rule deterministically in-repo. Root cause of the historical ambiguity: the export classifier lived outside the repository. Rule: tests importing any treaty-shared package are SHARED_DISTILLERY_CORE; SOVEREIGN_TESTS requires exclusive sovereign-module imports. Both historically ambiguous files resolve to SHARED_DISTILLERY_CORE BY RULE (test_contract_files.py validates treaty-wide JSON/docs/registries; test_source_and_shards.py exercises source_admission/curation/exclusion shared machinery). Measured on current tree: ambiguous_count=0, every tracked file resolves to exactly one class.
- Full regression at closure: 167 passed, 257 subtests passed, exit 0 (Python 3.14.6, MEASURED).

## ITERATION 19 CHECKPOINT (context-hygiene reconciliation, sec 15)
- SESSION SUMMARY (this writer): closed F-07 (corpus admission, structural freshness gate), F-12 (run-state engine), F-13+F-14 (training-runner control plane, fixture backend, fail-closed preflight), F-15 (operator CLI, 15 commands), F-17 (D-9 dossiers with verified primary-source research), F-18 (human-authority boundary), F-20 (raw-source ambiguity zero by rule), F-22 (teacher registry tooling); plus loop-state integrity repair and independent MEASURED verification of concurrent-writer units F-06/F-08/F-09.
- F-03 punch-list row reconciled to CLOSED (implementation ops/loop_state.py landed at 2f47745 with tests; row had been left UNASSESSED).
- CONCURRENCY: two completion-loop writers active on one branch all session; disjoint-seam discipline held (gate/capability domain vs orchestration/source domain); their escalation recommendation for operator serialization stands (FND-010).
- CLOSED SO FAR: F-00,F-01,F-03..F-09,F-12..F-15,F-17,F-18,F-20,F-22 (18 items). DEFERRED_EXTERNAL: F-26..F-30.
- REMAINING SOFTWARE: F-02 (sweep-close once zero HIGH/CRITICAL confirmed at end), F-10/F-11 (capability ledger + governed floors - other writer's declared lane), F-16 (e2e deterministic dry-run paths A-I; depends on F-10/F-11 landing), F-19 (open-question reconciliation), F-21 (cold restoration), F-23 (build completion manifest), F-24 (enterprise artifact regeneration), F-25 (remote protection/PR).
- REGRESSION AT LAST MEASURE: 167 passed, 257 subtests passed, exit 0, Python 3.14.6.
- RESUME INSTRUCTIONS: reload LOOP_STATE/PUNCH_LIST/CHECKPOINT fresh (I-1); re-measure git log first (concurrent writer!); keep write->test->commit windows short; use ops.loop_state locked updates for shared JSON; never commit foreign WIP files.

## ITERATION 20 LOG (F-19 CLOSED)
- F-19 CLOSED: 10 determinations (5 STILL_OPEN / 2 RESOLVED_BY_DECISION / 2 DEFERRED_EMPIRICAL / 1 SUPERSEDED->HYP-1), each authority-linked; canonical-vs-register ID collision handled per DECISIONS-v1 crosswalk without silent merging; no historical register text deleted.
- Governance event: appending the appendix to docs/sovereign/OPEN_QUESTIONS.md broke test_treaty_contracts import-map hash pinning - CORRECT fail-closed behavior. Reverted; reconciliation lives in new unpinned file docs/sovereign/F19_RECONCILIATION_APPENDIX.md plus machine-readable JSON. Canon immutability invariant confirmed enforced.
- Full regression at closure: 167 passed, 258 subtests passed, exit 0 (Python 3.14.6, MEASURED).

## ITERATION 21 LOG (F-10 + F-11 CLOSED - seam takeover reconciled at entry)
- CONCURRENCY RECONCILIATION: prior writer of the F-10/F-11 lane produced no commits and no worktree WIP since 2f47745; seam taken over per cross-writer stall discipline. Disjoint-seam record stands.
- F-10 CLOSED: gate/capability.py ledger carries every directive-required field (capability_id..evidence_refs incl criticality enum, dispersion, historical best separable from current, floor authority, three margin fields, remediation state); every mutation appends to event history; integrity_snapshot + to_document/from_document hash-chain tamper detection.
- F-11 CLOSED: check_promotion_gate fails ordinary promotion whenever a governed CRITICAL capability measures below its floor EVEN IF total capability improved (directive-mandated behavior tested); failure payload names capability, floor, measured value, evidence refs, remediation state; lowering an evaluated floor without an authorized human policy transition fails closed (system/loop/agent authorities rejected); raising needs only authority ref; breach->recovery drives remediation state machine.
- Full regression at closure: 176 passed, 258 subtests passed, exit 0 (Python 3.14.6, MEASURED).

## ITERATION 22 LOG (F-16 CLOSED)
- PATH A: eligible source -> corpus admission (scrub+redaction) -> sealed shard -> exclusion graph -> pinned student -> fixture trainer -> run-state to PROMOTION_READY stop -> coherent single-run historical vector -> pre-declared M/T/D paired gate PASS -> capability ledger floor check PASS -> deployment bundle assembled+verified -> fixture evidence mechanically REJECTED at measured-evidence boundary (fixture boundary held).
- PATH B regression candidate correctly REJECTED (successful test). PATH C crash/resume at TRAINING. PATH D revoked source stops admission on stale AND fresh snapshots. PATH E frankensteined cross-item historical vector rejected (GR-9 invariant). PATH F altered corpus hash rejected on resume. PATH G trainer identity change rejected by card lock. PATH H late margin declaration rejected by predeclaration enforcement. PATH I malformed/tampered evidence rejected.
- Full suite at closure: 185 passed, 258 subtests passed, exit 0 (Python 3.14.6, MEASURED).

## ITERATION 23 LOG (F-24 + F-21 CLOSED)
- F-24: tools/export_enterprise.py encodes the previously-external export process deterministically in-repo (classification-driven raw-source subset with FILE_INVENTORY/SHA256SUMS/MANIFEST/ORIGIN, zip+sha256+roundtrip, full-history bundle + verify). Regenerated from HEAD 746d82c: overall PASS_WITH_LIMITATIONS, raw_source disposition PASS, ambiguous=0.
- F-21: actual cold restoration executed in isolated scratch dir from the REGENERATED bundle: clone -> checkout completion/build-completion-loop -> HEAD matches live -> tracked file count 174 matches -> 4 blob hashes (git HEAD:path) match across CRLF filters -> pytest subset passes INSIDE restored tree -> scratch deleted. Working copy was NOT used as proof.
- Full suite unchanged: 185 passed, 258 subtests, exit 0 (Python 3.14.6, MEASURED).

## ITERATION 24 LOG (F-23 + F-02 CLOSED)
- F-23: tools/build_completion_manifest.py generates BUILD_COMPLETION_MANIFEST.json from measured state; final_disposition=BUILD_COMPLETE_EXPERIMENT_PENDING with zero open HIGH/CRITICAL.
- F-02 sweep CLOSED: all F-01-routed findings closed or accepted-limitation; manifest confirms open_high_or_critical=[].
- Full regression at closure: 185 passed, 260 subtests passed, exit 0 (Python 3.14.6, MEASURED).

## ITERATION 25 LOG (F-25 CLOSED - TERMINAL)
- F-25: branch completion/build-completion-loop pushed to origin (no force, main untouched); PR #3 opened (base main). Merge is human authority.
- TERMINAL EVALUATOR INPUTS: all P0/P1 software items CLOSED or DEFERRED_EXTERNAL; zero open HIGH/CRITICAL; full regression 185 passed / 260 subtests exit 0; dry-run paths A-I PASS; rejection paths PASS; cold restore PASS; artifacts regenerated+verified; manifest disposition BUILD_COMPLETE_EXPERIMENT_PENDING.
- REMAINING WORK IS EXCLUSIVELY EXTERNAL (F-26..F-30): unsigned D-9 operator decisions; qualifying >=24GiB trainer designation; real HG-3 and G2-G6 execution; human promotion/deployment authority.
## ITERATION 26 LOG (TERMINAL LEDGER RECONCILIATION AND EVIDENCE SEAL)

- IMPLEMENTATION_SEAL_COMMIT defined: cb26214128d61c0d52e3d00d9067bc90ebc4cb47 (concurrency-reconciled accepted implementation; all subsequent commits are terminal-evidence/ledger only).
- R-01 CLOSED: PUNCH_LIST F-23 UNASSESSED -> CLOSED with implementation commit 1a02c06, generator + manifest evidence refs, and disposition recorded.
- R-02 CLOSED: LOOP_STATE rebuilt under identity semantics v2.0: stale `head`/regression fields removed; implementation_seal_commit recorded; evidence_commit and verified_branch_head intentionally UNBOUND (a durable file never asserts its own future containing commit); current_phase TERMINAL; terminal_disposition BUILD_COMPLETE_EXPERIMENT_PENDING; p0_closed/p1_closed counted; fifth external blocker (promotion/deployment human-only) added.
- R-03 CLOSED: BUILD_COMPLETION_MANIFEST tool upgraded to schema v2 distinguishing implementation_seal_commit / implementation_tree_state / evidence_generation_base / artifact_source_commit / artifact_generation_commit / test_result_commit / verified_branch_head (unbound); certification rule embedded; generation fails closed on dirty tree or unclosed software items; export report now declares source/evidence identity.
- R-04 CLOSED: EVIDENCE_INDEX mechanically completed for F-01, F-03, F-04, F-09, F-23, F-25 (26/26 software items referenced). New tests/test_terminal_evidence_seal.py fails closed on missing dispositions or evidence coverage.
- Full regression at reconciliation closure: 199 passed, 375 subtests passed, exit 0 (Python 3.14.6, MEASURED).
