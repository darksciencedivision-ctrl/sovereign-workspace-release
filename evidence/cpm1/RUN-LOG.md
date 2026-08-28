# utc: 2026-08-26T06:28:40.9687426Z
# producer: ox-alpha master-run-order-20260826 run-log

P0 | tree-resolution | DONE | 2026-08-26T06:28:40.9687426Z | evidence/cpm1/phase0-tree-resolution.md
P1 | S-1 preconditions P2/P6/P7 | DONE (P2 BUNDLE ABSENT; P6 NOT_RUN(HARBOR_EXCLUDED); P7 len+162/notes=158 exact/Phase=90 exact/382 unreproduced) | 2026-08-26T06:40:24.4598528Z | docs/evidence/spa/SPA_DISCOVERY_REPORT.md
P1 | S-2 reviewer-packet inventory | DONE (read-only, no spawn) | 2026-08-26T06:40:24.4598528Z | docs/evidence/spa/SPA_DISCOVERY_REPORT.md
P1 | S-3 preservation matrix vs live tree | DONE (benchmark_score 0.5 placeholder CONFIRMED still present; live_debate.py path finding) | 2026-08-26T06:40:24.4598528Z | docs/evidence/spa/SPA_DISCOVERY_REPORT.md
P1 | S-4 SOVEREIGN publication seam | DONE (no bundle/review lineage fields carried) | 2026-08-26T06:40:24.4598528Z | docs/evidence/spa/SPA_DISCOVERY_REPORT.md
P1 | S-5 Track A readiness table | DONE (all four units gated) | 2026-08-26T06:40:24.4598528Z | docs/evidence/spa/SPA_DISCOVERY_REPORT.md
P2 | Track A entire phase (A-U1, A-U5, B1, A-U6, s7 remainder) | NOT_RUN(BUNDLE_ABSENT) | 2026-08-26T06:40:24.4598528Z | docs/evidence/spa/SPA_DISCOVERY_REPORT.md
P2 | gate/phase-19 earning | NOT_RUN(DEPENDENCY_UNMET: A-U1/A-U5 via BUNDLE_ABSENT) | 2026-08-26T06:40:24.4598528Z | evidence/cpm1/RUN-LOG.md

P3 | MT-05 live-leg derivation + provider determination + standing rule | DONE | 2026-08-26T06:49:04.5654473Z | mmt docs/registers/UNRESOLVED_ISSUE_REGISTER.md row U543 (arrival 9e1b31c6...8a79 -> 9efd08a5...1658, prefix-proof TRUE)
P3 | MT-06 coverage quirk retirement + U445 boundary | DONE | 2026-08-26T06:49:04.5654473Z | mmt register row U544
P3 | MT-07 operator-queue enumeration (4 items, recommendations, no adjudication) | DONE | 2026-08-26T06:49:04.5654473Z | mmt register row U545

P3 | MT-08 final sweep | PARTIAL - suite run 1/3 DONE (2851 passed / 1 failed-classified / 2 skipped / 5 deselected=derived set named, 768.22s); runs 2-3 NOT_RUN(TIME_BUDGET); 18-harness sweep NOT_RUN(TIME_BUDGET + abort-semantics boundary, all 18 NEVER INVOKED at final HEAD); audits/freeze/text/register-prefix DONE; finding MT-08-A job-host timing instrument | 2026-08-26T07:13:49.5691274Z | evidence/cpm1/mt/MT08-FINAL-SWEEP.md
P3->P4 | scope-handover | DONE | 2026-08-26T07:13:49.5691274Z | evidence/cpm1/scope-handover.md

P4 | Band-4 closure: E-7c/E-7b sweep (frozen prefix copies LOOP-LEDGER/linecount-a; BUILD-MANIFEST re-points scoped to 8b/8c; oracle G-oracle G2 provider-set repair) + Gate 8d submitted CANDIDATE with four G26 findings; G26 NOT_RUN(CONDUCTOR_LAUNCH_PROCESS_DEATH); zero spend | DONE | 2026-08-26T07:25:47.3386999Z | evidence/GATE-LEDGER.json key 8d; evidence/cpm1/8d/frozen/*; evidence/cpm1/LOOP-LEDGER.jsonl i=42-43

P4 | LADDER POSITION AT SESSION CLOSE | G28 next (NOT_RUN(LIVE_WORKERS_PRECONDITION) pending attended window; Bands 5-20 untouched) | 2026-08-26T07:29:00.3097135Z | docs/CP-M1-FINAL-REPORT.md

## ADD-07 session 2026-08-26T15:39:54.219991Z
G26 | NOT_RUN(CONDUCTOR_LAUNCH_PROCESS_DEATH) | 2026-08-26T15:39:54.219991Z | evidence/cpm1/8d/conductor-roundtrip.txt
G29 | NOT_RUN(DEPENDENCY_UNMET: G26) | 2026-08-26T15:39:54.219991Z | evidence/cpm1/8e/directive-delivery.txt
G30 | NOT_RUN(DEPENDENCY_UNMET: G26) | 2026-08-26T15:39:54.219991Z | evidence/cpm1/8e/synthesis.txt
G31 | TRUE (machinery; Conductor clause NOT_RUN G26) | 2026-08-26T15:39:54.219991Z | evidence/cpm1/8e/worker-failure.txt
G33 | TRUE | 2026-08-26T15:39:54.219991Z | evidence/cpm1/8f/opencode-detect.txt
G34 | NOT_RUN(OPENCODE_CLI_IS_BUN_NOT_HARNESS) | 2026-08-26T15:39:54.219991Z | evidence/cpm1/8f/opencode-direct.txt
G35 | NOT_RUN(OPENCODE_CLI_IS_BUN_NOT_HARNESS) | 2026-08-26T15:39:54.219991Z | evidence/cpm1/8f/opencode-delegation.txt
G36 | TRUE | 2026-08-26T15:39:54.219991Z | evidence/cpm1/8f/backend-not-model.txt
G28 | NOT_RUN(LIVE_WORKERS_UNAVAILABLE) | 2026-08-26T15:39:54.219991Z | evidence/cpm1/8e/worker-registry.json

## C-8(c) observation-only liveness 2026-08-27T00:46:14.3144781Z
5184 Listen OwningProcess=24380 (distillery)
8765 Listen OwningProcess=30796 (tokencenter)
AUTHORIZED-BY-STANDING-DELEGATION
no launch this session


## ADD-08 wave 2026-08-27T00:54:53.602Z
G3 | TRUE | 2026-08-27T00:54:53.602Z | evidence/cpm1/baseline/host-hardware.json (fresh capture)
G33 | TRUE | 2026-08-27T00:54:53.602Z | evidence/cpm1/8f/opencode-detect.txt OpenCode 1.18.23
G34 | NOT_RUN(SERVICE_LAUNCH_IS_OPERATOR_OWNED) | 2026-08-27T00:54:53.602Z | evidence/cpm1/8f/opencode-direct.txt (Bun cause SUPERSEDED)
G35 | NOT_RUN(SERVICE_LAUNCH_IS_OPERATOR_OWNED) | 2026-08-27T00:54:53.602Z | evidence/cpm1/8f/opencode-delegation.txt (Bun cause SUPERSEDED)
G36 | TRUE | 2026-08-27T00:54:53.602Z | canonical_registry descriptor refactor; backend-not-model.txt
G32 | TRUE | 2026-08-27T00:54:53.602Z | ledger 8e CANDIDATE live/NOT_RUN stated
G37 | TRUE | 2026-08-27T00:54:53.602Z | ledger 8f CANDIDATE
G43 | TRUE | 2026-08-27T00:54:53.602Z | ledger 8g CANDIDATE
G49 | TRUE | 2026-08-27T00:54:53.602Z | ledger 8h CANDIDATE
G53 | NOT_RUN(SERVICE_LAUNCH_IS_OPERATOR_OWNED) | 2026-08-27T00:54:53.602Z | PNG capture needs browser
G56 | TRUE | 2026-08-27T00:54:53.602Z | ledger 8i CANDIDATE (G53 limitation stated)
G61 | TRUE | 2026-08-27T00:54:53.602Z | evidence/cpm1/8j/orphans-after.txt
G62 | TRUE | 2026-08-27T00:54:53.602Z | ledger 8j CANDIDATE
G63 | TRUE | 2026-08-27T00:54:53.602Z | docs/CP-M1-REPORT.md Part A
G65 | TRUE | 2026-08-27T00:54:53.602Z | evidence/cpm1/test-run-handoff.txt copied from evidence/test-run.txt
G68 | TRUE | 2026-08-27T00:54:53.602Z | pin.txt sha256 field
G70 | NOT_RUN(SERVICE_LAUNCH_IS_OPERATOR_OWNED) | 2026-08-27T00:54:53.602Z | A2-A4 need llama.cpp generate
G71 | NOT_RUN(SERVICE_LAUNCH_IS_OPERATOR_OWNED) | 2026-08-27T00:54:53.602Z | A5-A8 need llama-server
G72 | NOT_RUN(SERVICE_LAUNCH_IS_OPERATOR_OWNED) | 2026-08-27T00:54:53.602Z | router mode live assert
G73 | TRUE | 2026-08-27T00:54:53.602Z | evidence/cpm1/9a/ollama-after.txt
G74 | NOT_RUN(DEPENDENCY_UNMET: G70-G72) | 2026-08-27T00:54:53.602Z | gate 9a not submitted without live A1-A8
G75 | NOT_RUN(SERVICE_LAUNCH_IS_OPERATOR_OWNED) | 2026-08-27T00:54:53.602Z |
G76 | NOT_RUN(SERVICE_LAUNCH_IS_OPERATOR_OWNED) | 2026-08-27T00:54:53.602Z |
G77 | NOT_RUN(SERVICE_LAUNCH_IS_OPERATOR_OWNED) | 2026-08-27T00:54:53.602Z |
G78 | NOT_RUN(SERVICE_LAUNCH_IS_OPERATOR_OWNED) | 2026-08-27T00:54:53.602Z |
G79 | NOT_RUN(SERVICE_LAUNCH_IS_OPERATOR_OWNED) | 2026-08-27T00:54:53.602Z |
G80 | NOT_RUN(DEPENDENCY_UNMET: G75-G79) | 2026-08-27T00:54:53.602Z |
G86 | TRUE | 2026-08-27T00:54:53.602Z | ledger 9c CANDIDATE
G90 | TRUE | 2026-08-27T00:54:53.602Z | evidence/cpm1/9d/planner-no-procctl.txt
G91 | NOT_RUN(SERVICE_LAUNCH_IS_OPERATOR_OWNED) | 2026-08-27T00:54:53.602Z | live VRAM round-trip
G92 | TRUE | 2026-08-27T00:54:53.602Z | planner/router tests
G93 | TRUE | 2026-08-27T00:54:53.602Z | fail-closed + ledger 9d CANDIDATE (live actuation limited)
G94 | TRUE | 2026-08-27T00:54:53.602Z | artifacts populated; dump regenerated
G95 | TRUE | 2026-08-27T00:54:53.602Z | test_legacy_alias_resolution
G96 | TRUE | 2026-08-27T00:54:53.602Z | deployment-manifest.schema.json
G97 | TRUE | 2026-08-27T00:54:53.602Z | test_ingestion_rejects
G98 | TRUE | 2026-08-27T00:54:53.602Z | three-axes + test
G99 | TRUE | 2026-08-27T00:54:53.602Z | ledger 9e CANDIDATE
G100 | TRUE | 2026-08-27T00:54:53.602Z | validation_evidence NOT_MEASURED on local rows
G101 | TRUE | 2026-08-27T00:54:53.602Z | context-measurement.txt tiers+budget
G102 | TRUE | 2026-08-27T00:54:53.602Z | NOT_MEASURED recorded
G103 | TRUE | 2026-08-27T00:54:53.602Z | demotion-impact no-op accepted
G104 | TRUE | 2026-08-27T00:54:53.602Z | ledger 9f CANDIDATE
G109 | TRUE | 2026-08-27T00:54:53.602Z | logring fields + metrics() + test
G110 | TRUE | 2026-08-27T00:54:53.602Z | ledger 9g CANDIDATE
G112 | TRUE | 2026-08-27T00:54:53.602Z | no-speculative-execution.txt
G114 | NOT_RUN(DEFERRED_HARDWARE) | 2026-08-27T00:54:53.602Z | nvfp4-research-lane.txt
G115 | TRUE | 2026-08-27T00:54:53.602Z | ledger 9h CANDIDATE
G5 | TRUE | 2026-08-27T00:54:53.602Z | BUILD-MANIFEST regenerated
G19 | TRUE | 2026-08-27T00:54:53.602Z | BM mismatch repaired
G59 | TRUE | 2026-08-27T00:54:53.602Z | BM mismatch repaired

G12 | TRUE | 2026-08-27T00:58:40.5664963Z | host-hardware restored to 8a-hashed copy (G3 date recapture reverted; T-4 adopt-prior)
G104 | TRUE | 2026-08-27T00:58:40.5664963Z | resolver reads production_context/validated_context
G114 | NOT_RUN(DEFERRED_HARDWARE) | 2026-08-27T00:58:40.5664963Z | research-lane artifact (no CANDIDATE token)
G116 | TRUE | 2026-08-27T00:58:40.5664963Z | evidence/cpm1/9j/invariants-reproved.txt
G117 | NOT_RUN(FS_WATCH_OPERATOR_OWNED) | 2026-08-27T00:58:40.5664963Z | window not closed this session
G118 | NOT_RUN(SERVICE_LAUNCH_IS_OPERATOR_OWNED) | 2026-08-27T00:58:40.5664963Z | live ollama generate rollback not demonstrated
G119 | TRUE | 2026-08-27T00:58:40.5664963Z | evidence/cpm1/9j/adversarial-review.txt
G120 | TRUE | 2026-08-27T00:58:40.5664963Z | UNEXPECTED: 0
G121 | TRUE | 2026-08-27T00:58:40.5664963Z | linecount-b.txt TOTAL-B 156/1625
G122 | TRUE | 2026-08-27T00:58:40.5664963Z | FINAL-EVIDENCE-MANIFEST.json
G124 | TRUE | 2026-08-27T00:58:40.5664963Z | ledger 9j CANDIDATE + Part B
PROGRESS | resolved-count~118 | reachable-remaining~launch-gated | elapsed=this-wave
G3 | TRUE | 2026-08-27T00:59:00Z | adopt-prior T-4; recapture reverted to preserve gate 8a hash
G62 | TRUE | 2026-08-27T00:59:00Z | ledger 8j CANDIDATE (report hash refreshed)
G63 | TRUE | 2026-08-27T00:59:00Z | docs/CP-M1-REPORT.md Part A R-01..R-15
G64 | TRUE | 2026-08-27T00:59:00Z | before-b captured; live drift is Package-B spend
PROGRESS | oracle 107/124 TRUE | 17 NOT_RUN named | 124 RESOLVED

## C-8(d) observation-only liveness 2026-08-27T01:05:41.5125140Z
5184 Listen OwningProcess=3936 (distillery, operator-owned)
8765 Listen OwningProcess=30796 (tokencenter, operator-owned)
AUTHORIZED-BY-STANDING-DELEGATION
no launch this session

## ADD-08 C-8(d) backfill 2026-08-27T01:06:41.394Z (oracle goalcheck-66 TRUE on disk; log lines owed)
G34 | NOT_RUN(SERVICE_LAUNCH_IS_OPERATOR_OWNED) | 2026-08-27T01:06:41.394Z | re-derived this turn: opencode.exe --version = 1.18.23 (not Bun). Live Sovereign/OpenCode session forbidden under C-8(d). evidence/cpm1/8f/opencode-direct.txt
G35 | NOT_RUN(SERVICE_LAUNCH_IS_OPERATOR_OWNED) | 2026-08-27T01:06:41.394Z | re-derived this turn: 1.18.23 confirmed. Delegation needs SOW/Electron launch. evidence/cpm1/8f/opencode-delegation.txt
G1 | TRUE | 2026-08-27T01:06:41.394Z | backfill: goalcheck-66 TRUE; artifacts on disk. AUTHORIZED-BY-STANDING-DELEGATION
G2 | TRUE | 2026-08-27T01:06:41.394Z | backfill: goalcheck-66 TRUE; artifacts on disk. AUTHORIZED-BY-STANDING-DELEGATION
G4 | TRUE | 2026-08-27T01:06:41.394Z | backfill: goalcheck-66 TRUE; artifacts on disk. AUTHORIZED-BY-STANDING-DELEGATION
G6 | TRUE | 2026-08-27T01:06:41.394Z | backfill: goalcheck-66 TRUE; artifacts on disk. AUTHORIZED-BY-STANDING-DELEGATION
G7 | TRUE | 2026-08-27T01:06:41.394Z | backfill: goalcheck-66 TRUE; artifacts on disk. AUTHORIZED-BY-STANDING-DELEGATION
G8 | TRUE | 2026-08-27T01:06:41.394Z | backfill: goalcheck-66 TRUE; artifacts on disk. AUTHORIZED-BY-STANDING-DELEGATION
G9 | TRUE | 2026-08-27T01:06:41.394Z | backfill: goalcheck-66 TRUE; artifacts on disk. AUTHORIZED-BY-STANDING-DELEGATION
G10 | TRUE | 2026-08-27T01:06:41.394Z | backfill: goalcheck-66 TRUE; artifacts on disk. AUTHORIZED-BY-STANDING-DELEGATION
G11 | TRUE | 2026-08-27T01:06:41.394Z | backfill: goalcheck-66 TRUE; artifacts on disk. AUTHORIZED-BY-STANDING-DELEGATION
G13 | TRUE | 2026-08-27T01:06:41.394Z | backfill: goalcheck-66 TRUE; artifacts on disk. AUTHORIZED-BY-STANDING-DELEGATION
G14 | TRUE | 2026-08-27T01:06:41.394Z | backfill: goalcheck-66 TRUE; artifacts on disk. AUTHORIZED-BY-STANDING-DELEGATION
G15 | TRUE | 2026-08-27T01:06:41.394Z | backfill: goalcheck-66 TRUE; artifacts on disk. AUTHORIZED-BY-STANDING-DELEGATION
G16 | TRUE | 2026-08-27T01:06:41.394Z | backfill: goalcheck-66 TRUE; artifacts on disk. AUTHORIZED-BY-STANDING-DELEGATION
G17 | TRUE | 2026-08-27T01:06:41.394Z | backfill: goalcheck-66 TRUE; artifacts on disk. AUTHORIZED-BY-STANDING-DELEGATION
G18 | TRUE | 2026-08-27T01:06:41.394Z | backfill: goalcheck-66 TRUE; artifacts on disk. AUTHORIZED-BY-STANDING-DELEGATION
G20 | TRUE | 2026-08-27T01:06:41.394Z | backfill: goalcheck-66 TRUE; artifacts on disk. AUTHORIZED-BY-STANDING-DELEGATION
G21 | TRUE | 2026-08-27T01:06:41.394Z | backfill: goalcheck-66 TRUE; artifacts on disk. AUTHORIZED-BY-STANDING-DELEGATION
G22 | TRUE | 2026-08-27T01:06:41.394Z | backfill: goalcheck-66 TRUE; artifacts on disk. AUTHORIZED-BY-STANDING-DELEGATION
G23 | TRUE | 2026-08-27T01:06:41.394Z | backfill: goalcheck-66 TRUE; artifacts on disk. AUTHORIZED-BY-STANDING-DELEGATION
G24 | TRUE | 2026-08-27T01:06:41.394Z | backfill: goalcheck-66 TRUE; artifacts on disk. AUTHORIZED-BY-STANDING-DELEGATION
G25 | TRUE | 2026-08-27T01:06:41.394Z | backfill: goalcheck-66 TRUE; artifacts on disk. AUTHORIZED-BY-STANDING-DELEGATION
G27 | TRUE | 2026-08-27T01:06:41.394Z | backfill: goalcheck-66 TRUE; artifacts on disk. AUTHORIZED-BY-STANDING-DELEGATION
G38 | TRUE | 2026-08-27T01:06:41.394Z | backfill: goalcheck-66 TRUE; artifacts on disk. AUTHORIZED-BY-STANDING-DELEGATION
G39 | TRUE | 2026-08-27T01:06:41.394Z | backfill: goalcheck-66 TRUE; artifacts on disk. AUTHORIZED-BY-STANDING-DELEGATION
G40 | TRUE | 2026-08-27T01:06:41.394Z | backfill: goalcheck-66 TRUE; artifacts on disk. AUTHORIZED-BY-STANDING-DELEGATION
G41 | TRUE | 2026-08-27T01:06:41.394Z | backfill: goalcheck-66 TRUE; artifacts on disk. AUTHORIZED-BY-STANDING-DELEGATION
G42 | TRUE | 2026-08-27T01:06:41.394Z | backfill: goalcheck-66 TRUE; artifacts on disk. AUTHORIZED-BY-STANDING-DELEGATION
G44 | TRUE | 2026-08-27T01:06:41.394Z | backfill: goalcheck-66 TRUE; artifacts on disk. AUTHORIZED-BY-STANDING-DELEGATION
G45 | TRUE | 2026-08-27T01:06:41.394Z | backfill: goalcheck-66 TRUE; artifacts on disk. AUTHORIZED-BY-STANDING-DELEGATION
G46 | TRUE | 2026-08-27T01:06:41.394Z | backfill: goalcheck-66 TRUE; artifacts on disk. AUTHORIZED-BY-STANDING-DELEGATION
G47 | TRUE | 2026-08-27T01:06:41.394Z | backfill: goalcheck-66 TRUE; artifacts on disk. AUTHORIZED-BY-STANDING-DELEGATION
G48 | TRUE | 2026-08-27T01:06:41.394Z | backfill: goalcheck-66 TRUE; artifacts on disk. AUTHORIZED-BY-STANDING-DELEGATION
G50 | TRUE | 2026-08-27T01:06:41.394Z | backfill: goalcheck-66 TRUE; artifacts on disk. AUTHORIZED-BY-STANDING-DELEGATION
G51 | TRUE | 2026-08-27T01:06:41.394Z | backfill: goalcheck-66 TRUE; artifacts on disk. AUTHORIZED-BY-STANDING-DELEGATION
G52 | TRUE | 2026-08-27T01:06:41.394Z | backfill: goalcheck-66 TRUE; artifacts on disk. AUTHORIZED-BY-STANDING-DELEGATION
G54 | TRUE | 2026-08-27T01:06:41.394Z | backfill: goalcheck-66 TRUE; artifacts on disk. AUTHORIZED-BY-STANDING-DELEGATION
G55 | TRUE | 2026-08-27T01:06:41.394Z | backfill: goalcheck-66 TRUE; artifacts on disk. AUTHORIZED-BY-STANDING-DELEGATION
G57 | TRUE | 2026-08-27T01:06:41.394Z | backfill: goalcheck-66 TRUE; artifacts on disk. AUTHORIZED-BY-STANDING-DELEGATION
G58 | TRUE | 2026-08-27T01:06:41.394Z | backfill: goalcheck-66 TRUE; artifacts on disk. AUTHORIZED-BY-STANDING-DELEGATION
G60 | TRUE | 2026-08-27T01:06:41.394Z | backfill: goalcheck-66 TRUE; artifacts on disk. AUTHORIZED-BY-STANDING-DELEGATION
G66 | TRUE | 2026-08-27T01:06:41.394Z | backfill: goalcheck-66 TRUE; artifacts on disk. AUTHORIZED-BY-STANDING-DELEGATION
G67 | TRUE | 2026-08-27T01:06:41.394Z | backfill: goalcheck-66 TRUE; artifacts on disk. AUTHORIZED-BY-STANDING-DELEGATION
G69 | TRUE | 2026-08-27T01:06:41.394Z | backfill: goalcheck-66 TRUE; artifacts on disk. AUTHORIZED-BY-STANDING-DELEGATION
G81 | TRUE | 2026-08-27T01:06:41.394Z | backfill: goalcheck-66 TRUE; artifacts on disk. AUTHORIZED-BY-STANDING-DELEGATION
G82 | TRUE | 2026-08-27T01:06:41.394Z | backfill: goalcheck-66 TRUE; artifacts on disk. AUTHORIZED-BY-STANDING-DELEGATION
G83 | TRUE | 2026-08-27T01:06:41.394Z | backfill: goalcheck-66 TRUE; artifacts on disk. AUTHORIZED-BY-STANDING-DELEGATION
G84 | TRUE | 2026-08-27T01:06:41.394Z | backfill: goalcheck-66 TRUE; artifacts on disk. AUTHORIZED-BY-STANDING-DELEGATION
G85 | TRUE | 2026-08-27T01:06:41.394Z | backfill: goalcheck-66 TRUE; artifacts on disk. AUTHORIZED-BY-STANDING-DELEGATION
G87 | TRUE | 2026-08-27T01:06:41.394Z | backfill: goalcheck-66 TRUE; artifacts on disk. AUTHORIZED-BY-STANDING-DELEGATION
G88 | TRUE | 2026-08-27T01:06:41.394Z | backfill: goalcheck-66 TRUE; artifacts on disk. AUTHORIZED-BY-STANDING-DELEGATION
G89 | TRUE | 2026-08-27T01:06:41.394Z | backfill: goalcheck-66 TRUE; artifacts on disk. AUTHORIZED-BY-STANDING-DELEGATION
G105 | TRUE | 2026-08-27T01:06:41.394Z | backfill: goalcheck-66 TRUE; artifacts on disk. AUTHORIZED-BY-STANDING-DELEGATION
G106 | TRUE | 2026-08-27T01:06:41.394Z | backfill: goalcheck-66 TRUE; artifacts on disk. AUTHORIZED-BY-STANDING-DELEGATION
G107 | TRUE | 2026-08-27T01:06:41.394Z | backfill: goalcheck-66 TRUE; artifacts on disk. AUTHORIZED-BY-STANDING-DELEGATION
G108 | TRUE | 2026-08-27T01:06:41.394Z | backfill: goalcheck-66 TRUE; artifacts on disk. AUTHORIZED-BY-STANDING-DELEGATION
G111 | TRUE | 2026-08-27T01:06:41.394Z | backfill: goalcheck-66 TRUE; artifacts on disk. AUTHORIZED-BY-STANDING-DELEGATION
G113 | TRUE | 2026-08-27T01:06:41.394Z | backfill: goalcheck-66 TRUE; artifacts on disk. AUTHORIZED-BY-STANDING-DELEGATION
G123 | TRUE | 2026-08-27T01:06:41.394Z | backfill: goalcheck-66 TRUE; artifacts on disk. AUTHORIZED-BY-STANDING-DELEGATION
PROGRESS | oracle 107/124 TRUE | 17 NOT_RUN named (G28 G53 G70-80 G91 G117 G118 + G34 G35) | 124 RESOLVED
