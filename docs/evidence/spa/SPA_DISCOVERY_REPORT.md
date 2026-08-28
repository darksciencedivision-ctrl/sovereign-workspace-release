# utc: 2026-08-26T06:39:27.2273841Z
# producer: ox-alpha master-run-order-20260826 phase1-spa-discovery

# SPA DISCOVERY REPORT - Master Run Order 2026-08-26, Phase 1 (READ-ONLY)

Tree of record (Phase 0, case 3): D:\multi model terminal app\sovereign-orchestration-workspace
git HEAD e6fcb89984ba50f296a1f4debb6669bfef12f996. Evidence root (D-SPA-B): Production Workspace\docs\evidence\spa\.

## S-1 Preconditions P2-P9

**P2 - sovereign-production.skill v2.0: ABSENT.** No reporting session has ever held it; this one does not either.
Sweeps performed this session, all read-only, all returning nothing:
- D:\multi model terminal app\sovereign-orchestration-workspace: glob **/sovereign-production* -> none
- D:\Product Software\Production Workspace: glob **/*production.skill* -> none; .claude/** -> no .claude directory exists
- C:\Users\Sslaw\.claude: glob **/sovereign-production*/** and **/*.skill* -> none
- D:\Product Software: glob *.skill* and **/sovereign-production.skill/** -> none
Expected had it been present: sha256 prefix 3fffc06408a665af, 96,889 bytes, 23 files. IT WAS NOT RECONSTRUCTED
from PDFs or v1.1 - that reconstruction is a forbidden action, not a close call. CONSEQUENCE (master run order,
Phase 1->2 boundary): Phase 2 (Track A) is NOT_RUN(BUNDLE_ABSENT) in its entirety.

**P6 - safe harbor: NOT_RUN(HARBOR_EXCLUDED)** per the issuing instruction; no full suite run was executed under
the harbor, and none is planned tonight.

**P7 - F-LEAK re-derivation from LOOP_STATE.json** (json.load semantics, py -3.12, file
docs/loop/LOOP_STATE.json, sha256 5842... see Phase 0 artifact for the file hash):
- raw bytes: 611,654
- len(text after utf-8 decode): **610,707** vs expected 610,545 -> DELTA **+162 characters**
- len(notes): **158** vs expected 158 -> EXACT MATCH, delta 0
- regex count A: r"Phase" = **90** vs expected 90 -> EXACT MATCH
- regex count B: expected 382 -> **NOT REPRODUCED.** The SPA directive that defines the exact pattern is absent
  from disk (see Ambiguities). 35+ candidate patterns swept; closest were commit=404, \bs\d=438, (?i)validator=345,
  check=336, PASS|FAIL word-bounded=150, reviewer ci=88. None equals 382.
Reading: the file has grown 162 characters while the notes[] count stayed fixed - consistent with edits inside
existing note strings rather than appended notes. Whether the growth touches leak-relevant content CANNOT be
established without the directive's own pattern definitions; recorded as a delta, not adjudicated.

**P3-P5, P8-P9: UNDEFINED_ON_DISK.** The directive document SPA_EXECUTION_DIRECTIVE_20260821_v1.3 is cited by
docs/SPA-OPERATOR-MARKS-DELEGATED.md but the file itself exists in neither tree (glob *SPA*DIRECTIVE* over the mmt
workspace: none; PW docs: only the marks file). What P3-P5/P8-P9 require is therefore not stateable from disk
this session. Recorded as unknown; NOT invented.

## S-2 Reviewer-packet inventory (highest-value item)

Established BY READING (no spawn performed):

Packet members (mmt tree):
1. .claude/agents/gate-validator.md - tools Read/Grep/Glob/Bash. Reads: docs/canonical/Claude_Code_Buildout_Directive_20260716.md s5;
   Architecture Plan v1.0.1 ss7,15-17; CLAUDE.md condensed invariant list (30). Procedure: enumerate criteria as separate checks;
   no PASS without (a) inspecting the artifact itself or (b) running the test/command itself; builder claims are not evidence;
   scope-violation check incl. writes under docs/canonical/ and phases begun early; invariant-drift check against all 30;
   verdict vocabulary PASS / PASS_WITH_RESERVATIONS / FAIL with per-criterion evidence; "Never soften a FAIL."
2. .claude/agents/spec-auditor.md - tools Read/Grep/Glob only (read-only). Precedence list: Canonical Handoff v2.4 ->
   Architecture Plan v1.0.1 -> Buildout Directive 20260716 -> CLAUDE.md (30 invariants). Hunts: authorization logic in
   mcp_server/ (I-M2/I-07), silent last-write-wins (I-13), worker-set ACCEPTED (I-M6/I-10), hard-coded vendor names where
   descriptors belong (I-SC1), float arithmetic in pricing/policy, spawn bypassing supervisor (I-C1); prohibited drift
   (TTS, consensus forcing, extra approval layers, opaque-agent UI, scope expansion); certainty inflation; verdict
   CLEAN / FINDINGS(severity+location).
3. tools/loop/driver_prompt.txt - BUILDER-side driver. Mandates: gate-validator subagent confirmation mandatory for
   high-stakes gates incl. 14A; two-commit convention; tag passed gates; update LOOP_STATE.json; D-LOOP-2 print-mode facts
   (foreground reviews; dead in-flight claims re-run fresh; poll children to completion).

Effort cues living IN THE REVIEWER PACKET (distinct from builder context): isolated context by construction
("deliberately not primed with the builder's implementation reasoning"); evidence-or-FAIL rule; self-run commands;
per-criterion enumeration; the three-word verdict vocabulary with reservations owned; never-soften rule; the auditor's
closed hunt-list keyed to named invariant IDs; read-only tool restriction on the auditor.
Effort cues living only in BUILDER CONTEXT: foreground/synchronous execution duty, stall-guard interplay, one-work-unit
ceiling, two-commit convention, WIP-checkpoint splitting, child-process polling duty.

Still requiring a LIVE invocation to establish (recorded, not attempted tonight - no dry-run spawn was performed):
whether the packet's instructions survive contact with a real model (adherence rates), whether Bash-carrying
gate-validator actually executes commands or reasons about them, and actual verdict latency/character deltas vs the
leak hypothesis. These are exactly what Track B would measure after gate/phase-19 exists.

## S-3 Preservation matrix against the LIVE tree (SPA s16.3 claims re-checked on source, not archives)

| Claimed component | Live-tree status | Citation |
|---|---|---|
| control_plane/tasks/graph.py | PRESENT; deterministic task@1.0 state machine; GATED_FAIL blocks transitively; no conductor override | FACT[control_plane/tasks/graph.py:1-8,18-30] |
| scheduler/capability_registry/registry.py | PRESENT; capability-only scheduling docstring intact | FACT[scheduler/capability_registry/registry.py:1-6] |
| RegisteredNode.benchmark_score == 0.5 placeholder | **STILL TRUE - placeholder remains**: field default 0.5 "placeholder until Track E/R10 (Phase 6)" and register() default 0.5 | FACT[registry.py:22] FACT[registry.py:31] |
| scheduler/resolver/resolver.py vendor-blind | PRESERVED - grep for grok/claude/codex/qwen/deepseek/fable/ollama/llama across resolver.py: ZERO hits; ranking formula consumes benchmark_score/active_tasks/cost_class only | FACT[scheduler/resolver/resolver.py:69] |
| scheduler/scheduler.py | PRESENT; composes TaskGraph + CapabilityRegistry + CapabilityResolver; queues unresolvable work with visible reason | FACT[scheduler/scheduler.py:1-15] |
| control_plane/orchestration/operator_surface.py | PRESENT (420 lines); governed pause; plan pauses BEFORE assignment; gate-failed plan not approvable | FACT[control_plane/orchestration/operator_surface.py:1-30] |
| debate_service/service.py | PRESENT (132 lines); invariant-18 no-self-judging refusal stated and enforced | FACT[debate_service/service.py:9-10] |
| live_debate.py | PRESENT BUT AT A DIFFERENT PATH than the S-3 shorthand: lives at control_plane/orchestration/live_debate.py (855 lines), NOT debate_service/. BackendDebater + fail-closed statement parse + leg vocabulary imported from live_flow | FACT[control_plane/orchestration/live_debate.py:1-25] |

LOUD FINDING (changes Track B bookkeeping, not its existence): the pair "debate_service/service.py + live_debate.py"
is split across TWO directories in the live tree. Any Track B scope line that assumes debate_service/live_debat.py
must be corrected to control_plane/orchestration/live_debate.py. No refuted preservation claim otherwise: every
checked component exists with its claimed character, and the 0.5 benchmark placeholder is confirmed still in place.

## S-4 SOVEREIGN publication seam (read-only)

modules/sovereign/INSTALL-PROVENANCE.json carries: module; source zip path; source_kind; source_sha256
(620e8459...be96); source_revision SOVEREIGN_ENTERPRISE_PRODUCTION_20260813_142520; source_content_manifest_sha256
(d2fa7633...05da) + path (modules/sovereign/PACKAGE_MANIFEST.txt); lockfiles[] with hash;
dependency_lock_status WORKSPACE_OWNED_RESOLVED; operator_authorized=null plus an operator_authorization_note;
installed_utc; install_commands_evidence; install_commands[]; integrity_verified=true; producer; updated_utc.
It does NOT carry: any sovereign-production.skill reference or version/hash (no bundle lineage at all); any
SPA/gate/phase lineage field; any review-verdict reference; per-file evidence hashes beyond the package-manifest
pointer. The publication seam therefore proves archive->install integrity, and proves NOTHING about skill-lineage
or review lineage - those would be new fields if SPA Track A ever requires them (R-3 forbids a second persistence).

## S-5 Track A readiness table (as gated by the Phase 1->2 boundary)

| Unit | Would write | Preconditions now | Unknowns |
|---|---|---|---|
| A-U1 reviewer amnesia | split docs/loop/LOOP_STATE.json moving notes[] to LOOP_NARRATIVE.md (move, never delete); content-addressed evidence filenames; new allowlist compiler tools/loop/check_review_packet.py; errata E1+E2 | **BUNDLE ABSENT -> NOT_RUN(BUNDLE_ABSENT)**; tree-writability question mooted tonight | E1/E2 errata bodies (defined only in the absent directive) |
| A-U5 finding dispositions | three disposition records incl. CONTRACT_GAP holding promotion (R-5 confirmed); preamble edit; CLAUDE.md edit separately | **NOT_RUN(BUNDLE_ABSENT)**; CLAUDE.md edit additionally NOT_RUN(Q8_UNRULED) forever-until-ruled | whether preamble edit text survives without directive context |
| B1 MCP stdio UTF-8 | 7-correct-bytes round-trip proof + negative control by revert | **NOT_RUN(BUNDLE_ABSENT)** | target file(s) for the fix (mcp_server/** side vs terminal/ side) |
| A-U6 position documents | position docs only; explicitly does NOT touch CLAUDE.md | **NOT_RUN(BUNDLE_ABSENT)** | document set defined by absent directive |

Ordering rule R-2 stands recorded but unexecuted: A-U1+A-U5 before any fresh Phase 19 gate review; B1 and A-U6 in
the same window; all four tagged first. gate/phase-19 was NOT earned tonight (its earning depends on A-U1/A-U5).

## Ambiguities flagged loudly (master run order reporting duty)

1. BOTH trees hold a Phase-19 runner pair; case-3 rule applied, mmt tree chosen for SPA/MT (Phase 0 artifact cites it).
2. The SPA directive document itself is absent from disk; every s-numbered requirement above was executed from the
   master run order text + delegated marks alone. Where the directive would have narrowed an answer (regex B, P3-P5,
   E1/E2 bodies), the gap is recorded instead of bridged.
3. The F-LEAK length delta is +162 chars at unchanged notes-count; leak-relevance undetermined.

## Verdict

Phase 1 DONE. Phase 2 NOT_RUN(BUNDLE_ABSENT) in its entirety - skip propagates to gate/phase-19 and everything
downstream of it. Proceed to Phase 3 (MT-P1).