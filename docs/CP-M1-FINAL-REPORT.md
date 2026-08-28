# utc: 2026-08-26T07:29:00.3097135Z
# producer: ox-alpha master-run-order-20260826 final-report

# CP-M1 FINAL REPORT - MASTER RUN ORDER 2026-08-26 - ALL FOUR PHASES

Session window: authorization received utc 2026-08-26T06:18:59.6147603Z (verbatim receipt +
corrective entry in evidence/OPERATOR-INSTRUCTIONS.log); report written 2026-08-26T07:29:00.3097135Z. Single writer throughout;
no second session, no delegation, no concurrent phases.

## 0. PHASE 0 - TREE RESOLUTION - DONE

Both candidate trees hold a Phase-19 runner pair. MASTER-RUN-ORDER s1 case 3 applied exactly as pre-decided:
SPA/MT operate on D:\multi model terminal app\sovereign-orchestration-workspace (HEAD e6fcb89984ba50f296a1f4debb6669bfef12f996);
CP-M1 stays in Production Workspace; disjoint. Artifact: evidence/cpm1/phase0-tree-resolution.md (sha256
5842ac6345d396eb1af8911d071cd3ffcfc63fc6274e425a68b978844089cd10). AMBIGUITY FLAGGED LOUDLY as ordered: both trees
keep gate runners; a future consolidation should remove or canonicalize one (operator decision).

## 1. PHASE 1 - SPA DISCOVERY (READ-ONLY) - DONE

Artifact: docs/evidence/spa/SPA_DISCOVERY_REPORT.md (sha256 d5e679ce69bd35076683e7f2619a2aaee7854e09e051382e5cddfa0843ee713a).
- S-1: P2 sovereign-production.skill v2.0 **ABSENT** (sweeps enumerated in the artifact across four roots; expected
  sha prefix 3fffc06408a665af / 96,889 B / 23 files). NOT reconstructed - forbidden action. P6 NOT_RUN(HARBOR_EXCLUDED).
  P7 F-LEAK re-derivation: len(text) 610,707 vs expected 610,545 (**+162**), len(notes) **158 == 158 exact**,
  regex r"Phase" = **90 == 90 exact**, second expected count 382 NOT reproduced among 35+ swept candidates (the
  defining directive text is absent from disk - see finding F-SPA-2).
- S-2 reviewer-packet inventoried BY READING (no spawn): gate-validator.md + spec-auditor.md effort cues vs builder
  context separated; what still needs live invocation recorded.
- S-3 preservation matrix against LIVE tree with citations; every claimed component present with its character;
  RegisteredNode.benchmark_score **still defaults to the 0.5 placeholder** (registry.py:22,31); vendor-blind resolver
  intact; LOUD FINDING: live_debate.py lives at control_plane/orchestration/, not debate_service/.
- S-4 seam: modules/sovereign/INSTALL-PROVENANCE.json carries archive/install integrity provenance and NO bundle or
  review lineage fields.
- S-5 Track A readiness table written; all four units gated by P2.

## 2. PHASE 2 - SPA TRACK A - NOT_RUN(BUNDLE_ABSENT) IN ITS ENTIRETY

Per the Phase 1->2 boundary. Skip propagates: A-U1, A-U5, B1, A-U6, s7 remainder (A-U2/A-U3/A-U4/A-U7),
gate/phase-19 earning, and everything downstream all NOT_RUN(DEPENDENCY_UNMET: BUNDLE_ABSENT). No unit was attempted
against prose, mock, or substitute. The CLAUDE.md edit additionally remains NOT_RUN(Q8_UNRULED).

## 3. PHASE 3 - MT-P1 - EXECUTED IN THE MMT TREE

### MT-05 - DONE
The complete live-leg set DERIVED from suite source (register row U543):
1. tests/integration/test_assembled_roster.py::test_item7_ollama_smoke_runs_live (:123)
2. tests/integration/test_assembled_run.py::test_assembled_run_live_ollama_leg_or_skip_with_record (:151)
3. tests/integration/test_multi_model_adapters.py::test_live_ollama_backend_smoke (:93-94)
4. tests/integration/test_opencode_candidate_live.py::test_live_drive_then_governed_candidate_and_merge (:75)
5. tests/integration/test_opencode_worktree_live.py::test_live_opencode_drives_local_model_in_isolated_worktree (:81)
Provider determination BY SOURCE READ, unsoftened: the fifth leg makes **NO provider call** - model pinned ollama/*
(:115), every event cost asserted exactly Decimal(0) (:123-125), local credential-free opencode spawn. CONSTRAINT 9
WAS NOT BREACHED. Recorded anyway: every run reporting "four live legs deselected" executed a fifth leg (U538
durations 712.34/581.78/106.37s) - list-completeness failure, no historical count estimated. Credential-free metadata
probes (codex --version/login status/exec --help; opencode --version) are non-billable under tests/live_call_guard.py:58-63.
STANDING RULE (verbatim, register row U543): **THE LIVE-LEG SET IS DERIVED, NEVER ENUMERATED. A DESELECTION THAT DOES
NOT NAME A DERIVED SET IS NOT A DESELECTION.**

### MT-06 - DONE
Coverage quirk RETIRED (row U544): U528 cluster(4) superseded by U537 finding 3 (STALE PIN 216 vs measured 222,
standalone control 222/222) and discharged by N4b at fc0b63e; pin lagged since the W-63/W-64 era per in-source
provenance (tests/unit/test_terminal_suite_coverage.py:52-57). U445 boundary stated explicitly: U437-U444 are
prior-phase material and WERE NOT EXAMINED - a stated limit, not an assurance.

### MT-07 - DONE (enumeration only; nothing adjudicated)
Four unseen operator-queue items (row U545): Q1 __pycache__ purge (51 trees, never purged; recommend one attended
hygiene window; mechanism itself already closed at 2a34e33) . Q2 CU-A1 invalidation residual (unlink-OSError swallowed;
recommend folding into the existing U461/U469 hygiene family with fail-closed grading) . Q3 U446 _op18d_amendment
guard debt (fingerprint observed five of five; recommend an authorized instrument-repair window that first rules what
R3 SHOULD assert) . Q4 two host-unverified legs W-22/W-23 (recommend attended off-host window or explicit permanent PARK-OP).

### MT-08 - PARTIAL; remainder NOT_RUN(TIME_BUDGET)
Artifact evidence/cpm1/mt/MT08-FINAL-SWEEP.md (sha256 ed025dd329bed1cda86419bdfbb145717c7184bcd677f6d411d7eb3056ee173e).
DONE: pre-run tree checks (HEAD+porcelain captured); freeze check git-level (docs/canonical + schemas EMPTY); text
integrity; stale-lock audit (no live locks); stray audit OBSERVE-ONLY (zero strays started, none killed); baseline
reconciliation (porcelain == D-4 baseline + this session's accounted register row); register SHA-256 re-derived with
ARRIVAL BYTE-PREFIX PROVEN (prefix hash == arrival hash; match=True). SUITE RUN 1 OF 3 DONE detached (C-8(b)): argv
carried ALL FIVE --deselect of the DERIVED set; result verbatim ``1 failed, 2851 passed, 2 skipped, 5 deselected in
768.22s``; deselected==declared set (the corrected practice demonstrated). Runs 2-3 NOT_RUN(TIME_BUDGET). ALL EIGHTEEN
HARNESSSES: NEVER INVOKED AT FINAL HEAD - NOT_RUN(TIME_BUDGET) plus a stated ABORT-SEMANTICS BOUNDARY (self-mutating
instruments require an execution window whose kill semantics guarantee restore; protected-tree restore tooling is
outside builder authority). Four-state tally tonight: 18 NEVER INVOKED / 0 others. Last-known harness states remain
U540 at fc0b63e - a different head, explicitly not current coverage. Summary word: PARTIAL, PRECISELY RECORDED - never CLEAN.

## 4. PHASE 3 -> 4 SCOPE HANDOVER - DONE

evidence/cpm1/scope-handover.md (sha256 38c9d1fd8d67b43ba74b4ee4c0ed3d7cd39c38da91579bbd36fe140fcb8726bc):
exactly ONE source file changed in the mmt root (UNRESOLVED_ISSUE_REGISTER.md, before 9e1b31c6...8a79 -> after
9efd08a5...1658, append-only PREFIX PROOF TRUE) plus two pytest runtime-cache files (named); protected-root manifest
re-captured methodologically identical (9,727 entries, same pinned tool, same excludes) superseding
manifest-cp01-before-multi-model-terminal-app.txt by name; Gate 8j note obligation recorded and carried inside the
8d note text.

## 5. PHASE 4 - CP-M1 - BAND 4 CLOSED; LADDER STOPPED AT G28

- E-7c/E-7b corrective sweep (LOOP-LEDGER i=42): the 26->23 oracle regression causes NAMED per E-8 - G2 stale oracle
  predicate vs the twice-amended spend envelope; G12/G19/G24 builder CANDIDATE gates citing append-only/evolving files
  by live hash. FIXES: prefix-reconstructed frozen copies (LOOP-LEDGER prefix 18,581 B == cited 74b95273... EXACTLY;
  linecount-a prefix 862 B == cited 28df9251... EXACTLY) created under 8a/8b/8c/frozen/ and citations path-re-pointed
  (hashes unchanged) with source_path + repointed_e7c_utc markers; BUILD-MANIFEST re-points scoped INSIDE 8b/8c only.
  DISCLOSED WITHOUT SOFTENING: the first BUILD-MANIFEST re-point mis-targeted occurrence #2 of nine and landed inside
  reviewer-owned gate 5; it was reverted by exact inverse replacement within minutes and the oracle GUARD (full-entry,
  E-2) verified OK immediately after; the five intended insertions were then audited gate-by-gate before proceeding.
- G-oracle repair: goalcheck.py g2 want-set re-pointed to [openai_codex_cli, claude_code, grok_build] citing ADD-04 s6
  (record 0c7d177b...) and ADD-05 v1.1 s5/D5-11 (live_operation.json 09377c9d...); new oracle sha256
  59d391e3db26e6ac4f70530e0f5aa17306cd0a45d144c8088ca642f5530598df re-pointed in gate 8a citation per E-7b.
- GATE 8d SUBMITTED CANDIDATE (ledger key 8d, i=43): ledger after write 86,167 bytes sha256
  7e0a55b9d67b54ee76e9f539126842ef8bb9e9bfcf82817a270064c6f9b2e2e4; GUARD OK; nine E-7c frozen copies under
  evidence/cpm1/8d/frozen/. G25 TRUE. G26 recorded NOT_RUN(CONDUCTOR_LAUNCH_PROCESS_DEATH) carrying the FOUR findings:
  (1) quoting drift found/fixed/pinned (T-1/T-2/T-3/T-6 earned; real string pinned conductor-write.js:112-113);
  (2) voice_turn_boundary claude_code-only by design - no codex conductor session can satisfy the guard (codex hooks
  are host-global config.toml; adapter refuses the bypass at codex.py:398-401) => R-04 unprovable on openai_codex_cli
  without new feature work; (3) in-app supervised-spawn process death NEW AND OWED (attempt #3 died mid-call; H1/H2/H3
  refuted by isolation chain; env exonerated; suspects in-app only); (4) ZERO SPEND. Limitation stated: round-trip
  unproven; rediagnosis OPTION A adopted (live R-04 proof deferred to Band 10 stepD); OPTION B refused; OPTION C moot.
- Post-closure oracle (goalcheck-61): GUARD OK; **28/124 TRUE**; G24 TRUE again; G27 TRUE.
- LADDER STOP POINT: first unresolved actionable goal is **G28 (Band 5)** - requires >= 2 live workers through the
  in-app supervised spawn surface, the exact subsystem of finding (3) and D5-5 (closed; do not reopen). Starting it
  late in an unattended session risked reproducing an owed crash with no budget left to diagnose it safely. Recorded
  honestly rather than forced: G28 onward remain FALSE/not-reached in the oracle, NOT_RUN(LIVE_WORKERS_PRECONDITION)
  recorded here and in RUN-LOG. Bands 5-20 untouched; Package B not begun.

## 6. CHANGED-LINE TOTALS VS BOTH CAPS

Package A: linecount-a.txt TOTAL-A | 371 | 1850 baseline plus the Band-4 handler repair row ->
TOTAL-A-after-G26-fix | **430 / 1850** (per-area sow-desktop 258+59 within its 700; test files excluded). No product
lines were changed THIS session in either package (Band-4 closure was evidence/ledger work only; the 430 figure is
the standing state inherited from the prior turn). Package B: **0 / 1625**, before-b/ not captured, unchanged.
mmt-tree changes this session: 1 source file (append-only register), fully handed over per section 4.

## 7. SPEND BY PROVIDER

THIS SESSION: zero attempts, zero deliveries, zero spend. PRIOR CONTEXT carried in spend-log.txt: openai_codex_cli
attempted turns 2 of <=10 sub-cap (both delivered=False submitted=False); three claude_code/fable-5 launch attempts
all refused pre-turn or died pre-turn (fable-5 selection predates the master run order's never-fable-5 rule and is
recorded as prior-session fact); grok_build/Qwen/DeepSeek 0; total against the 25-attempt ceiling: 2.

## 8. FINDINGS (FIRST-CLASS)

F-SPA-1 bundle absent after exhaustive named sweeps; F-SPA-2 SPA_EXECUTION_DIRECTIVE_20260821_v1.3 absent from disk
(P3-P5/P8-P9 unstated; regex-B undefined); F-SPA-3 F-LEAK length +162 at fixed notes-count, leak-relevance undetermined;
F-SPA-4 live_debat.py path split vs SPA shorthand; F-SPA-5 benchmark_score 0.5 placeholder persists (Track E/R10 debt);
F-SPA-6 INSTALL-PROVENANCE.json carries no skill/review lineage; F-MT-A job-host timing instrument warm-sensitive
(product reaping PROVEN by rc=124 + stderr line); F-MT-B scratch/u04f_run_suite.py gone from disk; F-MT-C LOOP_STATE
narrative vs register recency divergence; F-CPM-1 gate-flap class root-caused to evolving-file citations; frozen-prefix
technique closes it; F-CPM-2 the gate-5 mis-target/revert incident (disclosed above, guard-verified).

## 9. JUDGMENT CALLS FOR OPERATOR REVIEW

J-1 case-3 tree choice (mmt) for SPA/MT; J-2 Phase 2 wholly skipped on bundle absence (no prose-based units);
J-3 standing rule recorded as register row U543 (durable, append-only); J-4 eighteen-harness refusal grounded on
abort-semantics/protected-source rather than partial coverage; J-5 frozen-prefix reconstruction used to satisfy E-7c
for historically-cited hashes; J-6 G-oracle G2 predicate updated to the amended envelope rather than flagging the
amended config; J-7 rediagnosis OPTION A adopted into the 8d note; J-8 ladder halted at G28 instead of launching the
crash-prone surface unattended near the session's end.

## 10. GATE LEDGER SNAPSHOT AT CLOSE

PASS: 0,1,2,3,4,4b,4c,5,5b,6 (reviewer/operator-owned, byte-identical all session - GUARD OK at every check).
CANDIDATE: 7a,7b,8a,8b,8c,8d. Oracle: 28/124 TRUE (goalcheck-61). First failing: G26 disposition NOT_RUN (by order);
first actionable: G28. LOOP-LEDGER through i=43. fs-watch: operator-owned per C-4/A-7; gap-table duty unchanged.

## 11. WHERE THE NIGHT ENDED

RUN-LOG final position line appended below. Next session resumes at G28 without re-deriving anything: read this
report, evidence/cpm1/RUN-LOG.md, register rows U543-U545, ledger key 8d, and the Phase-0/handover artifacts.

BUILDER CLAIM: Gate 8d is a CANDIDATE for reviewer evaluation. No PASS status is asserted by the builder.